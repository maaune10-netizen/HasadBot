"""
exam.py - exam solving flow and approval callbacks.

Contains:

* ``solve_exam``              - kicks off the exam engine
* ``exam_approve_callback``   - admin/user approval to start exam engine
* ``exam_reject_callback``    - explicit reject
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
    get_user_subscription,
    get_user_free_attempts,
    get_user_homeworks_stats,
    db_get_user,
    update_user_last_active,
    deduct_homework_attempt,
    db_log,
    is_teacher,
    is_subscribed,
    get_remaining_exams,
)
from hasad_bot.utils import decrypt_password, admin_trace
from hasad_bot.logger import log_button_click
from hasad_bot.ai_engine import (
    active_sessions,
    get_engine_keyboard,
    solve_exam_logic_async,
)
from hasad_bot.models import UserSession
from hasad_bot.playwright_engine import _browser_pool


async def exam_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    معالج الموافقة على حل الاختبارات
    """
    query = update.callback_query
    await query.answer()

    # ✅ فقط أغلق الأزرار ولا ترسل رسالة جديدة
    try:
        # إزالة الأزرار من الرسالة القديمة
        await query.edit_message_reply_markup(reply_markup=None)
    except:
        pass

    # ✅ استدعاء solve_exam مباشرة (هي سترسل رسائلها الخاصة)
    await solve_exam(update, context)


async def exam_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    معالج الرفض - رسالة مختلفة تماماً
    """
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    from hasad_bot.database import is_admin, is_subscribed
    from hasad_bot.utils import now_hijri
    from hasad_bot.utils import kb_main

    adm = await is_admin(uid)
    sub = await is_subscribed(uid)

    # ✅ رسالة رفض واضحة مع خيارات بديلة
    await query.edit_message_text(
        "❌ <b>تم رفض تشغيل محرك الاختبارات</b> ❌\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>ماذا يمكنك أن تفعل بدلاً من ذلك؟</b>\n\n"
        "📚 <b>حل الواجبات</b>\n"
        "   • مناسب للمذاكرة اليومية\n"
        "   • يستهلك واجب واحد فقط\n\n"
        "⭐ <b>الاشتراك المميز</b>\n"
        "   • محاولات غير محدودة للاختبارات\n"
        "   • أولوية في الحل\n"
        "   • دعم فني مخصص\n\n"
        "🎁 <b>شارك واربح</b>\n"
        "   • احصل على واجبات مجانية إضافية\n"
        "   • كل صديق يسجل يمنحك مكافأة\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 {now_hijri()}",
        parse_mode="HTML",
        reply_markup=kb_main(uid, admin=adm, is_subscribed=sub)
    )


async def solve_exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بدء حل الاختبارات - نسخة رسمية (بدون رسائل تجريبية)
    """

    # ✅ استيرادات
    from hasad_bot.database import (
        get_user_remaining_homeworks,
        is_bot_frozen,
        is_admin,
        get_user_subscription,
        get_user_free_attempts,
        get_user_homeworks_stats,
        db_get_user,
        update_user_last_active,
        deduct_homework_attempt,
        db_log,
        is_teacher,
        is_subscribed,
        get_remaining_exams      # دالة مساعدة لحساب عدد الاختبارات المتبقية
    )
    from hasad_bot.utils import decrypt_password
    from hasad_bot.logger import log_button_click
    from hasad_bot.config import config
    from telegram.constants import ParseMode
    from hasad_bot.ai_engine import solve_exam_logic_async, active_sessions
    from hasad_bot.models import UserSession
    from hasad_bot.playwright_engine import _browser_pool
    from hasad_bot.utils import admin_trace
    import asyncio
    import time

    uid = update.effective_user.id
    name = update.effective_user.first_name or "مستخدم"

    # ✅ منع المستخدمين العاديين إذا كان البوت مجمد
    if await is_bot_frozen() and not await is_admin(uid):
        return

    await update_user_last_active(uid)
    await log_button_click(uid, "🧪 حل الاختبارات", "main")

    u = await db_get_user(uid) or {}
    is_sub = await is_subscribed(uid)
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
            parse_mode=ParseMode.HTML,
            reply_markup=build_link_nudge_keyboard(include_help=True)
        )
        return MAIN_MENU

    # التحقق من أن المستخدم ليس معلم
    if await is_teacher(uid):
        await update.message.reply_text(
            "🚫 <b>عذراً، هذه الميزة غير متاحة للحسابات التعليمية.</b>",
            parse_mode=ParseMode.HTML
        )
        return MAIN_MENU

    # عرض حالة المستخدم (مع إضافة عدد الاختبارات المتبقية)
    display_name = u.get('real_name') or name
    remaining_exams = await get_remaining_exams(uid)   # يجب تعريفها في database.py

    if sub:
        msg = f"""
👋 أهلاً {display_name}!
🌟 مستواك: {u.get('rank_title', '🥉 مبتدئ')}

━━━━━━━━━━━━━━━━━━
📊 اشتراكك الحالي:
📦 خطة: {sub['plan_name']}
🎟️ متبقي: {remaining} واجب
🧪 اختبارات متبقية: {remaining_exams} اختبار
📅 ينتهي: {u.get('expiry_hijri', '—')}
━━━━━━━━━━━━━━━━━━
"""
    elif trials > 0:
        # للمستخدم المجاني، نعرض عدد محاولات الاختبارات المجانية
        free_exam_remaining = await get_remaining_exams(uid)
        msg = f"""
👋 أهلاً {display_name}!
🌟 مستواك: {u.get('rank_title', '🥉 مبتدئ')}

━━━━━━━━━━━━━━━━━━
🎁 رصيدك:
🎟️ واجبات مجانية: {trials}
🧪 محاولات اختبارات مجانية: {free_exam_remaining}
━━━━━━━━━━━━━━━━━━
"""
    else:
        msg = f"""
👋 أهلاً {display_name}!

━━━━━━━━━━━━━━━━━━
❌ <b>لا توجد محاولات متبقية</b>
❌ <b>رصيدك منتهي!</b>

💡 <b>الفرص المتاحة:</b>
1️⃣ <b>اشتراك</b> (لزيادة حد الواجبات والاختبارات)
2️⃣ <b>شارك واربح</b> (اكسب واجبات مجانية)

👇 اضغط على <b>"⭐ المتجر"</b> للاشتراك
━━━━━━━━━━━━━━━━━━
"""
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return MAIN_MENU

    # ==============================================================
    # ✅ تنظيف الجلسة السابقة بالكامل قبل إنشاء جلسة جديدة
    # ==============================================================
    if uid in active_sessions:
        old_session = active_sessions[uid]

        if old_session.is_running:
            await update.message.reply_text(
                "⚠️ المحرك يعمل بالفعل!",
                reply_markup=get_engine_keyboard(old_session),
                parse_mode="HTML"
            )
            return MAIN_MENU

        admin_trace("SOLVE_EXAM", f"Cleaning old session for user {uid}", uid)
        old_session.is_running = False

        try:
            if hasattr(old_session, 'context') and old_session.context:
                for page in old_session.context.pages:
                    if not page.is_closed():
                        await page.close()
                await old_session.context.close()
                old_session.context = None
        except Exception as e:
            admin_trace("SOLVE_EXAM_CLEANUP", f"Close error: {e}", uid)

        try:
            if hasattr(_browser_pool, 'contexts') and uid in _browser_pool.contexts:
                del _browser_pool.contexts[uid]
        except Exception as e:
            admin_trace("SOLVE_EXAM_POOL", f"Pool cleanup error: {e}", uid)

        del active_sessions[uid]
        await asyncio.sleep(1)

    # ==============================================================
    # ✅ إنشاء جلسة جديدة
    # ==============================================================
    dars_pass_plain = decrypt_password(dars_pass_enc)

    wait_msg = await update.message.reply_text(msg, parse_mode="HTML")

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
        session.remaining = remaining
        session.is_subscribed = True
        session.max_allowed = sub.get('max_homeworks', 0)
        admin_trace("STATE", f"Subscriber: {session.remaining} homeworks remaining", uid)
    else:
        session.trials = trials
        session.is_subscribed = False
        admin_trace("STATE", f"Free user: {session.trials} attempts remaining", uid)

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

    # بناء القالب الأساسي (مع إضافة عدد الاختبارات المتبقية)
    if session.is_subscribed:
        session.base_template = (
            f"👋 أهلاً {display_name}!\n"
            f"🌟 مستواك: {session.rank_title}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>اشتراكك الحالي:</b>\n"
            f"📦 الخطة: {session.plan_name}\n"
            f"✅ تم حل: {{total_solved}} واجب\n"
            f"🎟️ متبقي: {{remaining}} واجب\n"
            f"🧪 اختبارات متبقية: {{remaining_exams}}\n"
            f"📅 ينتهي: {session.expiry_hijri}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        session.base_message = session.base_template.format(
            total_solved=session.total_solved,
            remaining=session.remaining,
            remaining_exams=remaining_exams
        )
    else:
        session.base_template = (
            f"👋 أهلاً {display_name}!\n"
            f"🌟 مستواك: {session.rank_title}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎁 <b>رصيدك:</b>\n"
            f"✅ تم حل: {{total_solved}} واجب\n"
            f"🎟️ واجبات مجانية: {{trials}}\n"
            f"🧪 اختبارات مجانية: {{free_exams}}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        session.base_message = session.base_template.format(
            total_solved=session.total_solved,
            trials=session.trials,
            free_exams=remaining_exams
        )

    session.stats = {"total_hw": 0, "mistakes": 0, "solved_q": 0}
    session.session_stats = {
        'exams': 0,
        'questions': 0,
        'correct': 0,
        'wrong': 0,
        'start': time.time(),
        'completed_exams': [],
        'sources': {}
    }

    active_sessions[uid] = session

    async def run_exam_engine():
        try:
            await solve_exam_logic_async(session)
        except Exception as e:
            admin_trace("EXAM_ENGINE_ERR", f"Engine failed: {e}", uid)
            await session.update_ui(f"❌ <b>خطأ في المحرك:</b> {str(e)[:100]}", get_engine_keyboard(None))

    asyncio.create_task(run_exam_engine())
    await db_log(uid, "EXAM_ENGINE_STARTED", detail=f"User: {dars_user}")

    return MAIN_MENU
