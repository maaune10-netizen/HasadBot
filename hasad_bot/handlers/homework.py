"""
homework.py - homework solving flow and engine controls.

Contains:

* ``solve_homework``        - kicks off the homework engine for a user
* ``engine_callback_handler`` - handles engine control callbacks
  (PDF report, stop, back, start)
"""
from __future__ import annotations

import asyncio
import time

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from hasad_bot.config import config, MAIN_MENU
from hasad_bot.database import (
    get_user_remaining_homeworks,
    is_bot_frozen,
    is_admin,
    is_subscribed,
    get_user_subscription,
    get_user_free_attempts,
    get_user_homeworks_stats,
    db_get_user,
    update_user_last_active,
    deduct_homework_attempt,
    db_log,
    is_teacher,
)
from hasad_bot.utils import decrypt_password, admin_trace
from hasad_bot.logger import log_button_click
from hasad_bot.ai_engine import (
    active_sessions,
    get_engine_keyboard,
    solve_homework_logic_async,
)
from hasad_bot.models import UserSession
from hasad_bot.playwright_engine import _browser_pool


async def solve_homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء حل الواجبات - واجهة واحدة متطورة"""

    uid = update.effective_user.id
    name = update.effective_user.first_name or "مستخدم"

    # ✅ منع المستخدمين العاديين إذا كان البوت مجمد
    if await is_bot_frozen() and not await is_admin(uid):
        return  # لا يرد نهائياً

    await update_user_last_active(uid)
    await log_button_click(uid, "🤖 حل الواجبات", "main")

    u = await db_get_user(uid) or {}
    is_sub = await is_subscribed(uid)
    # احسب total_solved
    total_solved = u.get('total_hw_solved', 0)

    # احصل على ref_link
    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"
    trials = u.get("free_attempts", 0)
    remaining = await get_user_remaining_homeworks(uid)
    sub = await get_user_subscription(uid)

    dars_user = u.get("dars360_user")
    dars_pass_enc = u.get("dars360_pass")

    # التحقق من ربط المنصة
    if not dars_user or not dars_pass_enc:
        from hasad_bot.handlers.onboarding import build_link_nudge_message, build_link_nudge_keyboard
        nudge_text = build_link_nudge_message(
            user_name=name,
            free_attempts=trials,
            is_subscribed=bool(sub),
            context="solving"
        )
        await update.message.reply_text(
            nudge_text,
            parse_mode="HTML",
            reply_markup=build_link_nudge_keyboard(include_help=True)
        )
        return MAIN_MENU

    # التحقق من أن المستخدم ليس معلم
    if await is_teacher(uid):
        await update.message.reply_text(
            "🚫 <b>عذراً، هذا الزر تحت الصيانة</b> 🚫\n\n",
            parse_mode=ParseMode.HTML
        )
        return MAIN_MENU

    # ... باقي الكود (نفسه)
    # عرض حالة المستخدم
    # عرض حالة المستخدم
    display_name = u.get('real_name') or name

    # ✅ تعريف المتغيرات المطلوبة للرسائل
    total_solved = u.get('total_hw_solved', 0)
    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"

    if sub:
        msg = f"""
👋 أهلاً {display_name}!
🌟 مستواك: {u.get('rank_title', '🥉 مبتدئ')}

━━━━━━━━━━━━━━━━━━
📊 اشتراكك الحالي:
📦 خطة: {sub['plan_name']}
🎟️ متبقي: {remaining} واجب
📅 ينتهي: {u.get('expiry_hijri', '—')}
━━━━━━━━━━━━━━━━━━
"""
    elif trials > 0:
        msg = f"""
👋 أهلاً {display_name}!
🌟 مستواك: {u.get('rank_title', '🥉 مبتدئ')}

━━━━━━━━━━━━━━━━━━
🎁 رصيدك:
🎟️ واجبات مجانية: {trials}
━━━━━━━━━━━━━━━━━━
"""
    else:
        msg = f"""
⚠️ <b>لقد استنفذت رصيدك المجاني</b> ⚠️

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 <b>إنجازك حتى الآن:</b>
✅ حللت <b>{total_solved}</b> واجب بنجاح!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💎 <b>ماذا بعد؟</b>

<b>⭐ اشتراك مميز</b>
• اسبوعي: 25 واجب | 10 ريال
• شهري: 100 واجب | 25 ريال
• ترم: 200 واجب | 60 ريال

<b>🎁 شارك واربح</b>
• كل صديق يسجل عبر رابطك يمنحك <b>{config.referral_bonus} واجبات مجانية</b>
• رابطك الخاص: <code>{ref_link}</code>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return MAIN_MENU

    # ==============================================================
    # ✅ تنظيف الجلسة السابقة بالكامل قبل إنشاء جلسة جديدة
    # ==============================================================
    if uid in active_sessions:
        old_session = active_sessions[uid]

        # إذا كانت الجلسة لا تزال قيد التشغيل
        if old_session.is_running:
            await update.message.reply_text(
                "⚠️ المحرك يعمل بالفعل!",
                reply_markup=get_engine_keyboard(old_session),
                parse_mode="HTML"
            )
            return MAIN_MENU

        # ✅ تنظيف الجلسة القديمة المتوقفة
        admin_trace("SOLVE_HW", f"Cleaning old session for user {uid}", uid)

        # إيقاف الجلسة
        old_session.is_running = False

        # إغلاق المتصفح بالكامل
        try:
            if hasattr(old_session, 'context') and old_session.context:
                # إغلاق كل الصفحات
                for page in old_session.context.pages:
                    try:
                        if not page.is_closed():
                            await page.close()
                    except:
                        pass
                # إغلاق السياق
                try:
                    await old_session.context.close()
                except:
                    pass
                old_session.context = None
        except Exception as e:
            admin_trace("SOLVE_HW_CLEANUP", f"Close error: {e}", uid)

        # ✅ تنظيف من Browser Pool أيضاً
        try:
            from hasad_bot.playwright_engine import _browser_pool
            if hasattr(_browser_pool, 'contexts') and uid in _browser_pool.contexts:
                # حذف السياق من الـ pool
                del _browser_pool.contexts[uid]
                admin_trace("SOLVE_HW", f"Removed context from pool for user {uid}", uid)
        except Exception as e:
            admin_trace("SOLVE_HW_POOL", f"Pool cleanup error: {e}", uid)

        # حذف الجلسة القديمة
        del active_sessions[uid]
        admin_trace("SOLVE_HW", f"Old session deleted for user {uid}", uid)

        # انتظار لحظي للتأكد من الإغلاق
        await asyncio.sleep(1)

    # ==============================================================
    # ✅ إنشاء جلسة جديدة
    # ==============================================================

    dars_pass_plain = decrypt_password(dars_pass_enc)

    # إرسال الرسالة الأولى
    wait_msg = await update.message.reply_text(msg, parse_mode="HTML")

    # إنشاء الجلسة
    loop = asyncio.get_running_loop()
    session = UserSession(
        user_id=uid,
        loop=loop,
        bot=context.bot,
        chat_id=wait_msg.chat_id,
        message_id=wait_msg.message_id,
        platform_user=dars_user,
        platform_pass=dars_pass_plain
    )

    # ==========================================================
    # ✅ استرجاع القيم الحقيقية من قاعدة البيانات
    # ==========================================================

    session.total_solved = u.get('total_hw_solved', 0)

    if sub:
        session.remaining = await get_user_remaining_homeworks(uid)
        session.is_subscribed = True
        session.max_allowed = sub.get('max_homeworks', 0)
        admin_trace("STATE", f"Subscriber: {session.remaining} homeworks remaining", uid)
    else:
        session.trials = await get_user_free_attempts(uid)
        session.is_subscribed = False
        admin_trace("STATE", f"Free user: {session.trials} attempts remaining", uid)


    # ========== تعيين متغيرات الجلسة للواجهة الثابتة ==========
    from hasad_bot.database import get_user_homeworks_stats

    # الحصول على إحصائيات الواجبات
    hw_stats = await get_user_homeworks_stats(uid)

    session.name = display_name
    session.rank_title = u.get('rank_title', '🥉 طالب جديد')
    session.plan_name = sub['plan_name'] if sub else ("واجبات مجانية" if trials > 0 else "لا يوجد")
    session.expiry_hijri = u.get('expiry_hijri', '—')
    session.total_solved = hw_stats['total_solved']
    session.remaining = hw_stats['remaining']
    session.trials = trials
    session.is_subscribed = sub is not None
    session.max_allowed = hw_stats['max_allowed']

    # بناء القالب الأساسي حسب نوع المستخدم
    if session.is_subscribed:
        session.base_template = (
            f"👋 أهلاً {display_name}!\n"
            f"🌟 مستواك: {session.rank_title}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>اشتراكك الحالي:</b>\n"
            f"📦 الخطة: {session.plan_name}\n"
            f"✅ تم حل: {{total_solved}} واجب\n"
            f"🎟️ متبقي: {{remaining}} واجب\n"
            f"📅 ينتهي: {session.expiry_hijri}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        session.base_message = session.base_template.format(
            total_solved=session.total_solved,
            remaining=session.remaining
        )
    else:
        session.base_template = (
            f"👋 أهلاً {display_name}!\n"
            f"🌟 مستواك: {session.rank_title}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎁 <b>رصيدك:</b>\n"
            f"✅ تم حل: {{total_solved}} واجب\n"
            f"🎟️ واجبات مجانية متبقية: {{trials}}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        session.base_message = session.base_template.format(
            total_solved=session.total_solved,
            trials=session.trials
        )

    session.stats = {"total_hw": 0, "mistakes": 0, "solved_q": 0}
    session.session_stats = {
        'homeworks': 0,
        'questions': 0,
        'correct': 0,
        'wrong': 0,
        'start': time.time(),
        'completed_homeworks': [],
        'sources': {}
    }

    active_sessions[uid] = session

    async def run_engine():
        try:
            await solve_homework_logic_async(session)
        except Exception as e:
            admin_trace("ENGINE_ERR", f"Engine failed: {e}", uid)
            await session.update_ui(f"❌ <b>خطأ في المحرك:</b> {str(e)[:100]}", get_engine_keyboard(None))

    asyncio.create_task(run_engine())
    await db_log(uid, "HW_ENGINE_STARTED", detail=f"User: {dars_user}")

    return MAIN_MENU


# Callback handlers
async def engine_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أزرار المحرك (بدون pause/resume)"""
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    from hasad_bot.ai_engine import active_sessions
    from hasad_bot.utils import friendly_error_message
    import time
    import asyncio

    try:
        if q.data == 'engine_pdf_report':
            if uid in active_sessions:
                session = active_sessions[uid]
                from hasad_bot.ai_engine import send_detailed_report
                try:
                    await send_detailed_report(session)
                except Exception as e:
                    admin_trace("REPORT_ERR", str(e), uid)
                    friendly_msg = friendly_error_message(e)
                    await q.edit_message_text(
                        f"❌ {friendly_msg}\n\n"
                        "يمكنك متابعة الحل دون التقرير المفصل.",
                        parse_mode='HTML'
                    )
            else:
                await q.edit_message_text("⚠️ لا توجد جلسة نشطة", parse_mode='HTML')
            return

        elif q.data == 'engine_stop':
            if uid in active_sessions:
                session = active_sessions[uid]
                session.is_running = False  # فقط أوقف الجلسة
                admin_trace("ENGINE_STOP", f"Session paused for user {uid}", uid)

                # ==============================================================
                # 1. أولاً: إيقاف الجلسة (يمنع أي تحديثات جديدة)
                # ==============================================================
                session.is_running = False
                admin_trace("ENGINE_STOP", f"Session stopped for user {uid}", uid)

                # ==============================================================
                # 2. ثانياً: عرض رسالة الإيقاف للمستخدم
                # ==============================================================
                try:
                    if hasattr(session, 'session_stats') and session.session_stats.get('homeworks', 0) > 0:
                        from hasad_bot.database import get_user_remaining_homeworks
                        elapsed = int(time.time() - session.session_stats.get('start', time.time()))
                        minutes = elapsed // 60
                        seconds = elapsed % 60

                        # ✅ إحصائيات هذه الجلسة فقط (بدون التراكمي)
                        _init = session.session_stats.get('_initial_snapshot', {})
                        total_questions = session.session_stats.get('questions', 0) - _init.get('questions', 0)
                        total_correct = session.session_stats.get('correct', 0) - _init.get('correct', 0)
                        total_wrong = session.session_stats.get('wrong', 0) - _init.get('wrong', 0)

                        if total_questions > 0:
                            percentage = (total_correct / total_questions) * 100
                        else:
                            percentage = 0

                        report = (
                            f"🛑 <b>تم إيقاف المحرك</b>\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"<b>📊 نتائج الجلسة:</b>\n\n"
                            f"✅ <b>الواجبات:</b> {session.session_stats.get('homeworks', 0) - _init.get('homeworks', 0)}\n"
                            f"✅ <b>الأسئلة:</b> {total_questions}\n"
                            f"✅ <b>الصحيح:</b> {total_correct}\n"
                            f"❌ <b>الخاطئ:</b> {total_wrong}\n"
                            f"📈 <b>النسبة:</b> {percentage:.1f}%\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"<b>📦 رصيدك المتبقي:</b>\n"
                        )

                        if session.is_subscribed:
                            report += f"🎟️ {session.remaining} واجب\n"
                        else:
                            report += f"🎟️ {session.trials} محاولة مجانية\n"

                        report += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        report += f"<b>⏱️ وقت الجلسة:</b> {minutes} دقيقة {seconds} ثانية\n\n"
                        report += f"يمكنك استكمال الباقي لاحقاً 👋"

                        await q.edit_message_text(report, parse_mode='HTML')
                    else:
                        await q.edit_message_text("🛑 <b>تم إيقاف المحرك</b>", parse_mode='HTML')
                except Exception as e:
                    admin_trace("ENGINE_STOP_MSG_ERR", str(e), uid)
                    try:
                        await q.edit_message_text("🛑 <b>تم إيقاف المحرك</b>", parse_mode='HTML')
                    except:
                        pass

                # ==============================================================
                # 3. ثالثاً: انتظار لحظي للتأكد من توقف المحرك
                # ==============================================================
                await asyncio.sleep(1.5)  # زيادة وقت الانتظار

                # ==============================================================
                # 4. رابعاً: إغلاق السياق فقط (وليس المتصفح!)
                # ==============================================================
                try:
                    if hasattr(session, 'context') and session.context:
                        # إغلاق كل الصفحات في السياق
                        for page in session.context.pages:
                            try:
                                if not page.is_closed():
                                    await page.close()
                            except:
                                pass

                        # إغلاق السياق نفسه
                        try:
                            await session.context.close()
                        except:
                            pass

                        session.context = None
                        admin_trace("ENGINE_STOP", f"Context closed for user {uid}", uid)
                except Exception as e:
                    admin_trace("ENGINE_STOP_CLOSE_ERR", str(e), uid)

                # ==============================================================
                # 5. خامساً: إزالة السياق من Browser Pool بالكامل
                # ==============================================================
                try:
                    from hasad_bot.playwright_engine import _browser_pool

                    # إزالة السياق من قاموس contexts
                    context_key = f"user_{uid}"
                    if hasattr(_browser_pool, 'contexts') and context_key in _browser_pool.contexts:
                        del _browser_pool.contexts[context_key]
                        admin_trace("ENGINE_STOP", f"Removed context from pool for user {uid}", uid)

                    # أيضاً تأكد من إزالة أي مرجع في session
                    if hasattr(session, 'context_id'):
                        session.context_id = None

                except Exception as e:
                    admin_trace("ENGINE_STOP_POOL_ERR", str(e), uid)

                # ==============================================================
                # 6. سادساً: حذف الجلسة من active_sessions
                # ==============================================================
                if uid in active_sessions:
                    session = active_sessions[uid]
                    session.is_running = False  # فقط أوقف الجلسة

                    admin_trace("ENGINE_STOP", f"Session deleted for user {uid}", uid)

                # ==============================================================
                # 7. سابعاً: رسالة تأكيد للمستخدم
                # ==============================================================
                try:
                    if q.message is not None:
                        await q.message.reply_text(
                            "✅ <b>تم إيقاف المحرك وتنظيف الجلسة بالكامل</b>\n\n"
                            "يمكنك الآن بدء جلسة جديدة بالضغط على 🤖 حل الواجبات",
                            parse_mode='HTML'
                        )
                    else:
                        await q.answer(
                            "✅ تم إيقاف المحرك وتنظيف الجلسة بالكامل",
                            show_alert=True
                        )
                except Exception:
                    pass

            else:
                try:
                    await q.edit_message_text("⚠️ <b>لا توجد جلسة نشطة</b>", parse_mode='HTML')
                except:
                    pass

        elif q.data == 'engine_back':
            if uid in active_sessions:
                session = active_sessions[uid]
                session.is_running = False

                # انتظار لحظي
                await asyncio.sleep(1.5)

                # إغلاق السياق
                if hasattr(session, 'context') and session.context:
                    try:
                        for page in session.context.pages:
                            if not page.is_closed():
                                await page.close()
                        await session.context.close()
                    except:
                        pass

                # إزالة من Browser Pool
                try:
                    from hasad_bot.playwright_engine import _browser_pool
                    context_key = f"user_{uid}"
                    if hasattr(_browser_pool, 'contexts') and context_key in _browser_pool.contexts:
                        del _browser_pool.contexts[context_key]
                except:
                    pass

                if uid in active_sessions:
                    del active_sessions[uid]

                await q.edit_message_text(
                    "🔙 <b>تم العودة للقائمة الرئيسية</b>\n\n"
                    "يمكنك البدء من جديد بالضغط على 🤖 حل الواجبات",
                    parse_mode='HTML',
                    reply_markup=None
                )
            else:
                await q.edit_message_text("🔙 <b>تم العودة</b>", parse_mode='HTML')

        elif q.data == 'engine_start':
            # ``solve_homework`` is defined in the same module - call directly.
            await solve_homework(update, context)

    except Exception as e:
        admin_trace("ENGINE_CALLBACK_ERR", str(e), uid)
        friendly_msg = friendly_error_message(e)
        try:
            await q.edit_message_text(
                f"❌ {friendly_msg}",
                parse_mode='HTML'
            )
        except:
            pass
