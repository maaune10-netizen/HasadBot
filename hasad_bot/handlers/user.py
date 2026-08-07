"""
user.py - end-user facing handlers that don't fit a specific feature module.

Contains:

* ``start``                  - ``/start`` command (welcome + onboarding)
* ``help_command``           - ``/help`` command
* ``my_account``             - account info screen
* ``share_and_earn``         - referral / share link
* ``handle_text``            - main menu text router
* ``cmd_show_archived``      - admin-only view of archived credentials
* ``cmd_restore_archive``    - admin-only restore from archive
"""
from __future__ import annotations

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CopyTextButton,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from hasad_bot.config import config, MAIN_MENU, ADMIN_PANEL, AWAIT_ADMIN_PASSWORD
from hasad_bot.database import (
    is_bot_frozen,
    is_admin,
    is_subscribed,
    update_user_last_active,
    db_get_user,
    db_set_user,
    db_log,
    _db_pool,
    get_user_remaining_homeworks,
)
from hasad_bot.utils import kb_main, now_hijri
from hasad_bot.logger import log_button_click
from hasad_bot.handlers.infrastructure import rate_limit
from hasad_bot.handlers.constants import (
    BTN_SOLVE_HOMEWORK,
    BTN_SOLVE_EXAM,
    BTN_SHARE_AND_EARN,
    BTN_MY_ACCOUNT,
    BTN_LOGIN,
    BTN_SHOP,
    BTN_SUPPORT,
    BTN_ADMIN_PANEL,
    BTN_BACK_MAIN,
    BTN_END_SUPPORT,
    BTN_CANCEL,
    BTN_ACTIVATE_KEY,
    ADMIN_BTN_STATS,
    ADMIN_BTN_EXTRACT,
    ADMIN_BTN_BROADCAST,
    ADMIN_BTN_RENEW,
    ADMIN_BTN_REVOKE,
    ADMIN_BTN_GENKEYS,
    ADMIN_BTN_TOGGLE_MODE,
    ADMIN_BTN_LIST_USERS,
    ADMIN_BTN_ADD_ADMIN,
    ADMIN_BTN_FILES,
    ADMIN_BTN_FULL_RESET,
    BTN_RESELLER_PANEL,
    BTN_RESELLER_CUSTOMERS,
    BTN_RESELLER_ACTIVATE,
    BTN_RESELLER_STATS,
    BTN_RESELLER_LINK,
    BTN_RESELLER_TX_LOG,
    ADMIN_BTN_RESELLERS,
    ADMIN_BTN_ADD_RESELLER,
    ADMIN_BTN_RESELLER_CREDIT,
    ADMIN_BTN_RESELLER_LIST,
    ADMIN_BTN_RESELLER_PRICES,
    ADMIN_BTN_RESELLER_STATS,
    ADMIN_BTN_HIDDEN_PANEL,
    ADMIN_BTN_CHARGE_ADMIN,
    ADMIN_BTN_LIST_ADMINS,
)
import time


@rate_limit
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler - نسخة محسنة بالكامل"""

    uid = update.effective_user.id
    name = update.effective_user.first_name or "مستخدم"
    args = context.args

    # منع المستخدمين العاديين إذا كان البوت مجمد
    from hasad_bot.database import is_bot_frozen
    if await is_bot_frozen() and not await is_admin(uid):
        return

    await update_user_last_active(uid)
    await log_button_click(uid, "/start", "command")

    u = await db_get_user(uid)
    is_new = u is None

    # ======================== المستخدم الجديد ========================
    if is_new:
        referred_by = None
        ref_name = None
        ref_count = 0
        reseller_id = None

        if args and args[0].startswith("ref_"):
            try:
                ref_id = int(args[0].split("_")[1])
                if ref_id != uid:
                    referred_by = ref_id
                    ref_user = await db_get_user(ref_id)
                    if ref_user:
                        ref_name = ref_user.get('name', 'صديقك')
                    ref_count = 0
                    if ref_count >= 3:
                        referred_by = None
                        ref_name = None
            except:
                pass

        # Reseller link: ?start=res_{reseller_id}
        elif args and args[0].startswith("res_"):
            try:
                res_id = int(args[0].split("_")[1])
                if res_id != uid:
                    res_user = await db_get_user(res_id)
                    if res_user and (res_user.get('role') in ('reseller', 'admin') or res_user.get('is_admin', 0) >= 1):
                        reseller_id = ref_id = res_id
                        referred_by = res_id
                        ref_user = res_user
                        ref_name = res_user.get('name', 'الموزع')
                        ref_count = 0

                        # Log reseller link click
                        try:
                            await db_log(uid, "RESELLER_LINK_CLICK", detail=f"Reseller: {res_id}, New user: {name}")
                        except Exception:
                            pass
            except:
                pass

        free_attempts = config.free_attempts
        if referred_by and ref_count < 3:
            free_attempts += config.referral_bonus
            ref_count += 1

        await db_set_user(
            uid,
            name=name,
            tg_username=update.effective_user.username or "",
            joined_hijri=now_hijri(),
            free_attempts=free_attempts,
            referred_by=referred_by,
            referral_used_count=ref_count
        )

        # Mark user as reseller's customer + notify reseller
        if reseller_id:
            try:
                conn = await _db_pool.get_connection()
                await conn.execute(
                    "UPDATE users SET referred_by_reseller = ? WHERE telegram_id = ?",
                    (reseller_id, uid)
                )
                await conn.commit()
            except Exception:
                pass

            # Notify reseller about new customer
            try:
                await context.bot.send_message(
                    chat_id=reseller_id,
                    text=f"📩 <b>عميل جديد دخل عن طريق رابطك!</b>\n\n"
                         f"👤 <b>العميل:</b> {name}\n"
                         f"🆔 <b>المعرّف:</b> <code>{uid}</code>\n\n"
                         f"💡 يمكنك تفعيل اشتراكه من لوحة الموزع.",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        if referred_by and ref_name and ref_count <= 3:
            ref_u = await db_get_user(referred_by)
            if ref_u:
                new_attempts = ref_u.get('free_attempts', 0) + config.referral_bonus
                new_count = ref_u.get('referral_count', 0) + 1
                await db_set_user(
                    referred_by,
                    free_attempts=new_attempts,
                    referral_count=new_count
                )
                try:
                    await context.bot.send_message(
                        referred_by,
                        f"🎉 <b>مبروك!</b> 🎉\n\n"
                        f"قام <b>{name}</b> بالدخول عبر رابطك الخاص.\n\n"
                        f"🎁 <b>مكافأتك:</b> +{config.referral_bonus} واجبات مجانية\n"
                        f"📊 <b>إجمالي الإحالات:</b> {new_count}\n"
                        f"🎟️ <b>رصيدك الحالي:</b> {new_attempts} محاولة\n\n"
                        f"💪 استمر في المشاركة واكسب المزيد!",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    print(f"❌ فشل إرسال رسالة للمستخدم {referred_by}: {e}")

        # رسالة ترحيب جديدة للمستخدم الجديد (مختصرة وواضحة)
        welcome_text = (
            f"🌾 <b>أهلاً بك في حصاد، {name}!</b> 🌾\n\n"
            f"🚀 أنا هنا لأحل لك واجبات منصة درس 360 تلقائياً.\n"
            f"وفر وقتك وركز على المذاكرة.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>📌 خلاصة الأزرار:</b>\n\n"
            f"🔗 <b>ربط المنصة</b> → ابدأ هنا (مرة واحدة)\n"
            f"🤖 <b>حل الواجبات</b> → بعد الربط، اضغط واترك الباقي عليَّ\n"
            f"🎁 <b>شارك واربح</b> → كل صديق يسجل يمنحك +{config.referral_bonus} واجبات\n"
            f"👤 <b>حسابي</b> → رصيدك، رتبتك، اشتراكك\n"
            f"⭐ <b>المتجر</b> → اشتراك أسبوعي، شهري، ترم\n"
            f"🆘 <b>الدعم الفني</b> → تواصل مع الإدارة\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎁 <b>هديتك المجانية:</b> {free_attempts} واجب\n"
            f"💡 للمساعدة: /help\n\n"
            f"⚡ <b>يلا نبدأ 👇</b>"
        )

        await update.message.reply_text(
            welcome_text,
            parse_mode="HTML",
            reply_markup=kb_main(uid, admin=False, is_reseller=bool(reseller_id))
        )

        # ✅ للمستخدم الجديد: وجّهه لربط المنصة مباشرة
        from hasad_bot.handlers.onboarding import build_link_nudge_message, build_link_nudge_keyboard
        nudge_text = build_link_nudge_message(
            user_name=name,
            free_attempts=free_attempts,
            is_subscribed=False,
            context="first_time"
        )
        await update.message.reply_text(
            nudge_text,
            parse_mode="HTML",
            reply_markup=build_link_nudge_keyboard(include_help=True)
        )

        if referred_by and ref_name:
            remaining_links = 3 - ref_count
            reward_text = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎉 <b>تهانينا!</b> 🎉\n\n"
                f"لقد انضممت عن طريق رابط <b>{ref_name}</b> 🤝\n\n"
                f"🎁 <b>مكافأتك:</b> +{config.referral_bonus} واجبات مجانية\n"
                f"🎟️ <b>رصيدك الحالي:</b> {free_attempts} محاولة\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"(كل رابط يمنحك +{config.referral_bonus} محاولات إضافية)\n\n"
                f"🔗 شارك رابطك مع أصدقائك واكسب المزيد!"
            )
            await update.message.reply_text(
                reward_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )

        return MAIN_MENU

    # ======================== المستخدم القديم ========================
    adm = await is_admin(uid)
    sub = await is_subscribed(uid)
    from hasad_bot.database import is_reseller as _is_reseller
    reseller = await _is_reseller(uid)
    u = await db_get_user(uid) or {}

    # ربط المستخدم القديم بموزع عند دخوله عبر رابط res_
    if args and args[0].startswith("res_"):
        try:
            res_id = int(args[0].split("_")[1])
            if res_id != uid:
                existing_reseller = u.get('referred_by_reseller')
                if not existing_reseller:
                    res_user = await db_get_user(res_id)
                    if res_user and (res_user.get('role') in ('reseller', 'admin') or res_user.get('is_admin', 0) >= 1):
                        try:
                            conn = await _db_pool.get_connection()
                            await conn.execute(
                                "UPDATE users SET referred_by_reseller = ? WHERE telegram_id = ?",
                                (res_id, uid)
                            )
                            await conn.commit()
                            u['referred_by_reseller'] = res_id

                            # Log reseller link click (existing user)
                            try:
                                await db_log(uid, "RESELLER_LINK_CLICK", detail=f"Reseller: {res_id}, Existing user: {name}")
                            except Exception:
                                pass

                            # Notify reseller about existing user clicking their link
                            try:
                                await context.bot.send_message(
                                    chat_id=res_id,
                                    text=f"📩 <b>مستخدم موجود دخل عن طريق رابطك!</b>\n\n"
                                         f"👤 <b>المستخدم:</b> {name}\n"
                                         f"🆔 <b>المعرّف:</b> <code>{uid}</code>\n\n"
                                         f"💡 يمكنك تفعيل اشتراكه من لوحة الموزع.",
                                    parse_mode="HTML"
                                )
                            except Exception:
                                pass
                        except Exception:
                            pass
                        except Exception:
                            pass
        except Exception:
            pass

    # بيانات أساسية
    total_solved = u.get('total_hw_solved', 0)
    rank_title = u.get('rank_title', '🥉 طالب جديد')
    referral_count = u.get('referral_count', 0)
    expiry_hijri = u.get('expiry_hijri', '—')
    free_attempts = u.get('free_attempts', 0)

    # رصيد الاشتراك (إذا كان مشتركاً)
    remaining_subscription = 0
    subscription_plan_name = ""
    days_left = 0

    if sub:
        from hasad_bot.database import get_user_remaining_homeworks, get_user_subscription
        remaining_subscription = await get_user_remaining_homeworks(uid)
        sub_obj = await get_user_subscription(uid)
        if sub_obj:
            subscription_plan_name = sub_obj.get('plan_name', 'اشتراك')
            days_left = sub_obj.get('days_left', 0)

    # بناء نص الرصيد (يعرض الاشتراك والمجاني معًا إذا كانا موجودين)
    remaining_parts = []
    if sub and remaining_subscription > 0:
        remaining_parts.append(f"📦 <b>رصيد الاشتراك:</b> {remaining_subscription} واجب")
    if free_attempts > 0:
        remaining_parts.append(f"🎁 <b>رصيد المجاني:</b> {free_attempts} واجب")

    if remaining_parts:
        remaining_text = "\n".join(remaining_parts)
    else:
        remaining_text = "⚠️ <b>لا يوجد رصيد متبقي</b>"

    # تحديد حالة الاشتراك مع تنبيه إذا كان على وشك الانتهاء
    if adm:
        subscription_status = "👑 أدمن (دائم)"
        expiry_display = "♾️ دائم"
    elif sub:
        if days_left <= 3:
            expiry_display = f"⚠️ {expiry_hijri} (ينتهي بعد {days_left} أيام!)"
        else:
            expiry_display = expiry_hijri
        subscription_status = f"✅ نشط ({subscription_plan_name})"
    else:
        subscription_status = "❌ غير نشط"
        expiry_display = "—"

    # رسالة الترحيب الجديدة للمستخدم القديم
    await update.message.reply_text(
        f"🌾 <b>حصاد في خدمتك يا {name}!</b> 🌾\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {now_hijri()}\n\n"
        f"🏆 <b>رتبتك:</b> {rank_title}\n"
        f"🎯 <b>الواجبات المحلولة:</b> {total_solved}\n"
        f"{remaining_text}\n"
        f"👥 <b>الأصدقاء عن طريقك:</b> {referral_count}\n\n"
        f"💎 <b>الاشتراك:</b> {subscription_status}\n"
        f"📆 <b>ينتهي:</b> {expiry_display}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🚀 اختر ما تريد من القائمة 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_main(uid, admin=adm, is_reseller=reseller)
    )

    # ✅ للمستخدم القديم الذي ما ربط: وجّهه للربط (لو عنده رصيد)
    dars_user = u.get("dars360_user") or ""
    dars_pass = u.get("dars360_pass") or ""
    if not dars_user.strip() or not dars_pass.strip():
        if free_attempts > 0 or sub:
            from hasad_bot.handlers.onboarding import build_link_nudge_message, build_link_nudge_keyboard
            nudge_text = build_link_nudge_message(
                user_name=name,
                free_attempts=free_attempts,
                is_subscribed=sub,
                context="general"
            )
            await update.message.reply_text(
                nudge_text,
                parse_mode="HTML",
                reply_markup=build_link_nudge_keyboard(include_help=True, include_skip=True)
            )

    return MAIN_MENU


async def share_and_earn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Share and earn handler - نسخة الأبطال"""
    uid = update.effective_user.id
    from hasad_bot.config import MAIN_MENU, config   # أضف , config
    from hasad_bot.utils import now_hijri
    from hasad_bot.database import (
        is_bot_frozen, is_admin, update_user_last_active,
        db_get_user
    )

    current_date = now_hijri()

    if await is_bot_frozen() and not await is_admin(uid):
        return MAIN_MENU

    await update_user_last_active(uid)
    await log_button_click(uid, "🎁 شارك واربح", "main")

    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"

    u = await db_get_user(uid) or {}
    trials = u.get("free_attempts", 0)
    refs = u.get("referral_count", 0)

    # ✅ نص عادي للنسخ (بدون أي تنسيق - Plain Text)
    copy_text_content = f"""🤖 حصاد AI - أول ذكاء اصطناعي يحل واجبات منصة درس 360 تلقائياً!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎁 رابط التسجيل (احصل على واجبات مجانية):
{ref_link}

✅ انضم الآن واختبر حَصاد⚡️ بنفسك!

"""

    # نظام المستويات (نفسه)
    if refs >= 20:
        level = "🏆 أسطورة الإحالة"
        next_milestone = "✨ مبروك! وصلت لأعلى مستوى"
    elif refs >= 10:
        level = "💎 محترف"
        next_needed = 20 - refs
        next_milestone = f"تحتاج {next_needed} أصدقاء عشان توصل لمستوى الأسطورة"
    elif refs >= 5:
        level = "🌟 نجم"
        next_needed = 10 - refs
        next_milestone = f"تحتاج {next_needed} أصدقاء عشان توصل لمستوى محترف"
    else:
        level = "🌱 مبتدئ"
        next_needed = 5 - refs
        next_milestone = f"تحتاج {next_needed} أصدقاء عشان توصل للنجمة الأولى"

    text = f"""
<b>🎁 نظام الإحالات - اكسب واجبات مجانية</b>

━━━━━━━━━━━━━━━━━━
<b>كيف يعمل؟</b>

1️⃣ انسخ رابطك الخاص بالأسفل
2️⃣ أرسله لأصدقائك في المدرسة أو القروبات
3️⃣ كل صديق يسجل عن طريقك، تربح <b>{config.referral_bonus} واجبات مجانية</b> فورًا

━━━━━━━━━━━━━━━━━━
<b>📊 إحصائياتك:</b>
👥 عدد من سجل عن طريقك: <b>{refs}</b>
🎟️ الواجبات المتبقية لديك: <b>{trials}</b>

━━━━━━━━━━━━━━━━━━
<i>كلما زاد عدد أصدقائك، زادت واجباتك المجانية! 🚀</i>
"""

    # أزرار المشاركة
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📱 مشاركة", url=f"https://t.me/share/url?url={ref_link}"),
            InlineKeyboardButton(
                text="📋 نسخ الرابط",
                copy_text=CopyTextButton(text=copy_text_content)
            )
        ]
    ])

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

    return MAIN_MENU


@rate_limit
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دليل سريع مع شرح الأزرار"""

    uid = update.effective_user.id

    # ✅ منع المستخدمين العاديين إذا كان البوت مجمد
    from hasad_bot.database import is_bot_frozen
    if await is_bot_frozen() and not await is_admin(uid):
        return  # لا يرد نهائياً


    help_text = (
        f"📋 <b>شرح الأزرار يا {update.effective_user.first_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"<b>🔗 ربط المنصة</b>\n"
        f" أول خطوة: تربط حساب منصة درس\n"
        f" مرة واحدة وبعدها أنا أشتغل\n\n"

        f"<b>🤖 حل الواجبات</b>\n"
        f" يبدأ البوت يحل واجباتك عنك\n\n"

        f"<b>🎁 شارك واربح</b>\n"
        f" ترسل الرابط لأصحابك\n"
        f" كل ما يدخل واحد، تزيد واجباتك\n\n"

        f"<b>👤 حسابي</b>\n"
        f" تشوف معلومات حسابك كاملة:\n"
        f"   • عدد الواجبات اللي حليتها\n"
        f"   • كم محاولة مجانية باقي لك\n"

        f"<b>⭐ المتجر</b>\n"
        f" تشتري اشتراك (أسبوعي، شهري، ترم)\n"
        f" طرق دفع: نجوم تليجرام، تحويل بنكي، STC Pay\n"
        f" <b>⚠️ ملاحظة:</b> بعد الشراء يصير عندك <b>حد واجبات أعلى</b>\n"
        f"   • اسبوعي: 25 واجب\n"
        f"   • شهري: 100 واجب\n"
        f"   • ترم: 200 واجب\n\n"

        f"<b>🆘 الدعم الفني</b>\n"
        f" تكلم الإدارة لو صار شي\n\n"

        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>بالتوفيق!</b>"
    )

    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=kb_main(update.effective_user.id, admin=await is_admin(update.effective_user.id), is_reseller=await _is_reseller(update.effective_user.id))
    )


@rate_limit
async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """My account handler - عرض معلومات المستخدم وإحصائيات البوت"""
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "👤 حسابي", "main")

    u = await db_get_user(uid) or {}
    sub = await is_subscribed(uid)

    total_solved_by_bot = u.get('total_hw_solved', 0)  # الواجبات اللي حلها البوت

    # ✅ جلب عدد الأسئلة المحلولة للمستخدم
    from hasad_bot.database import _db_pool
    conn = await _db_pool.get_connection()
    async with conn.execute("""
        SELECT COUNT(*) FROM solved_questions WHERE user_id = ?
    """, (uid,)) as c:
        total_questions = (await c.fetchone())[0] or 0

    rank_title = u.get('rank_title', '🥉 طالب جديد')
    platform_user = u.get('dars360_user', '')

    from hasad_bot.database import get_user_remaining_homeworks
    remaining_hw = await get_user_remaining_homeworks(uid)

    if platform_user:
        platform_display = f"<code>{platform_user}</code>"
    else:
        platform_display = "🔗 اضغط لربط المنصة"

    if sub:
        subscription_status = "✅ نشط"
        subscription_end = u.get('expiry_hijri', '—')
        attempts_text = f"🎟️ <b>الرصيد المتبقي:</b> {remaining_hw} واجب"
    else:
        subscription_status = "❌ منتهي"
        subscription_end = "—"
        attempts_text = f"🎁 <b>الواجبات المجانية:</b> {u.get('free_attempts', 0)}"

    # ✅ التنسيق الجديد مع عدد الأسئلة
    text = f"""
<b>👤 معلومات حسابك</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📛 <b>الاسم:</b> {u.get('name', '—')}
🏅 <b>الرتبة:</b> {rank_title}
🆔 <b>ID:</b> <code>{uid}</code>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🤖 إحصائيات البوت:</b>
✅ <b>الواجبات التي حلها البوت لك:</b> {total_solved_by_bot}
❓ <b>الأسئلة التي حلها البوت لك:</b> {total_questions}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🎓 منصة درس 360:</b>
🔗 <b>الحساب المرتبط:</b> {platform_display}

<b>💎 الاشتراك:</b> {subscription_status}
📆 <b>ينتهي:</b> {subscription_end}
{attempts_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📅 <b>التاريخ:</b> {now_hijri()}
"""

    keyboard = None

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    return MAIN_MENU


@rate_limit
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text or ""
    uid = update.effective_user.id
    print(f"🔥 handle_text called with: {update.message.text}")

    # ✅ التحقق من أن المستخدم أدمن ويوجد طلب بث معلق
    if await is_admin(uid) and context.user_data.get("awaiting_broadcast_text"):
        target = context.user_data.get("broadcast_target")
        if target:
            # ✅ استدعاء دالة البث
            from hasad_bot.handlers.admin import admin_broadcast_send
            await admin_broadcast_send(update, context)
            return

    # باقي الكود الموجود...
    # باقي الكود الموجود...    # ✅ التحقق من وجود message (لتجنب NoneType error)
    if not update.message:
        return MAIN_MENU

    text = update.message.text or ""
    uid = update.effective_user.id
    name = update.effective_user.full_name or update.effective_user.first_name
    adm = await is_admin(uid)

    # ✅ ✅ ✅ FROZEN - منع المستخدمين العاديين إذا كان البوت مجمد ✅ ✅ ✅
    from hasad_bot.database import is_bot_frozen
    if await is_bot_frozen() and not await is_admin(uid):
        return  # لا يرد نهائياً

    await update_user_last_active(uid)

    # ✅ ✅ ✅ الأزرار العامة (تعمل دائماً) ✅ ✅ ✅
    # bot_handlers.py - داخل دالة handle_text

    # Lazy imports to avoid circular import at module load time.
    from hasad_bot.handlers.homework import solve_homework
    from hasad_bot.handlers.exam import solve_exam
    from hasad_bot.handlers.login import cmd_login, login_got_username
    from hasad_bot.handlers.payment import open_shop
    from hasad_bot.handlers.support import enter_support_room, exit_support_room
    from hasad_bot.handlers.admin import (
        admin_panel,
        admin_system_stats,
        admin_extract_credentials,
        admin_broadcast_ask,
        admin_renew_ask,
        admin_revoke_ask,
        admin_genkeys_ask,
        admin_toggle_mode,
        admin_list_users,
        admin_add_admin_ask,
        admin_files,
        admin_full_reset,
    )
    from hasad_bot.handlers.subscriptions import activate_subscription
    from hasad_bot.handlers.infrastructure import _cancel_handler
    from hasad_bot.handlers.reseller import (
        reseller_panel, reseller_customers, reseller_activate,
        reseller_stats, reseller_link, reseller_tx_log,
    )
    from hasad_bot.handlers.admin_reseller import admin_reseller_panel
    from hasad_bot.handlers.user import cmd_admin_panel, handle_admin_password
    from hasad_bot.handlers.constants import ADMIN_BTN_RESELLERS

    main_routing = {
        BTN_SOLVE_HOMEWORK: solve_homework,
        BTN_SOLVE_EXAM: solve_exam,
        BTN_SHARE_AND_EARN: share_and_earn,
        BTN_MY_ACCOUNT: my_account,
        BTN_LOGIN: cmd_login,
        BTN_SHOP: open_shop,
        BTN_SUPPORT: enter_support_room,
        BTN_ADMIN_PANEL: admin_panel,
        BTN_BACK_MAIN: start,
        BTN_RESELLER_PANEL: reseller_panel,
        BTN_RESELLER_CUSTOMERS: reseller_customers,
        BTN_RESELLER_ACTIVATE: reseller_activate,
        BTN_RESELLER_STATS: reseller_stats,
        BTN_RESELLER_LINK: reseller_link,
        BTN_RESELLER_TX_LOG: reseller_tx_log,
        ADMIN_BTN_RESELLERS: admin_reseller_panel,
    }
    # ✅ أزرار الدعم الفني (تعمل حتى لو كان في حالة support)
    support_buttons = {
        BTN_END_SUPPORT: exit_support_room,
    }

    # ✅ أزرار الإلغاء (تعمل دائماً)
    cancel_buttons = {
        BTN_CANCEL: _cancel_handler,
    }

    # ✅ أولاً: تحقق من أزرار الدعم الفني
    if text in support_buttons:
        return await support_buttons[text](update, context)

    # ✅ ثانياً: تحقق من أزرار الإلغاء
    if text in cancel_buttons:
        return await cancel_buttons[text](update, context)

    # ✅ ثالثاً: تحقق من الأزرار الرئيسية
    if text in main_routing:
        return await main_routing[text](update, context)

    # ✅ إذا كان المستخدم في عملية ربط (اختار مدرسة ويرسل اسم المستخدم)
    if context.user_data.get("selected_school_id"):
        if text not in main_routing and text not in cancel_buttons:
            return await login_got_username(update, context)

    # ✅ باقي الكود القديم...
    if text == BTN_ACTIVATE_KEY:
        return await activate_subscription(update, context)

    if context.user_data.get('waiting_for_key'):
        context.user_data['waiting_for_key'] = False
        context.args = [text]
        return await activate_subscription(update, context)

    if adm:
        from hasad_bot.handlers.admin_reseller import (
            admin_reseller_panel, admin_add_reseller, admin_reseller_credit,
            admin_reseller_list, admin_reseller_prices, admin_reseller_stats_panel,
            admin_delete_reseller, admin_ban_reseller_customer,
            admin_list_admins, admin_charge_admin, admin_delete_admin,
        )
        admin_map = {
        ADMIN_BTN_STATS: admin_system_stats,
        ADMIN_BTN_EXTRACT: admin_extract_credentials,
        ADMIN_BTN_BROADCAST: admin_broadcast_ask,
        ADMIN_BTN_RENEW: admin_renew_ask,
        ADMIN_BTN_REVOKE: admin_revoke_ask,
        ADMIN_BTN_GENKEYS: admin_genkeys_ask,
        ADMIN_BTN_TOGGLE_MODE: admin_toggle_mode,
        ADMIN_BTN_LIST_USERS: admin_list_users,
        ADMIN_BTN_ADD_ADMIN: admin_add_admin_ask,
        ADMIN_BTN_FILES: admin_files,
        BTN_SOLVE_EXAM: solve_exam,
        ADMIN_BTN_FULL_RESET: admin_full_reset,
        ADMIN_BTN_RESELLERS: admin_reseller_panel,
        ADMIN_BTN_ADD_RESELLER: admin_add_reseller,
        ADMIN_BTN_RESELLER_CREDIT: admin_reseller_credit,
        ADMIN_BTN_RESELLER_LIST: admin_reseller_list,
        ADMIN_BTN_RESELLER_PRICES: admin_reseller_prices,
        ADMIN_BTN_RESELLER_STATS: admin_reseller_stats_panel,
        "🗑️ حذف موزع": admin_delete_reseller,
        "🗑️ حذف أدمن": admin_delete_admin,
        "🚫 حظر عميل الموزع": admin_ban_reseller_customer,
        ADMIN_BTN_CHARGE_ADMIN: admin_charge_admin,
        ADMIN_BTN_LIST_ADMINS: admin_list_admins,
    }
        if text in admin_map:
            result = await admin_map[text](update, context)
            # Ensure admin keyboard stays visible after any admin action
            if uid == config.admin_id and result == ADMIN_PANEL:
                from hasad_bot.utils import kb_admin
                await update.message.reply_text(
                    "👑 اختر الإجراء:", parse_mode="HTML",
                    reply_markup=kb_admin()
                )
            return result

    return MAIN_MENU


# ==============================================================================
# /admin — Hidden admin panel with password auth
# ==============================================================================

async def cmd_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /admin — Hidden command for admin panel access.
    If already authenticated in this session, show panel directly.
    Otherwise, ask for password.
    """
    uid = update.effective_user.id

    # Check if user is an admin (is_admin>=1 or owner)
    user = await db_get_user(uid)
    is_owner = (uid == config.admin_id)
    is_adm = user and (user.get('is_admin', 0) >= 1 or user.get('role') in ('admin', 'reseller'))

    if not is_owner and not is_adm:
        await update.message.reply_text("⛔ هذا الأمر غير متاح لك.")
        return MAIN_MENU

    # If already authenticated this session, show admin panel directly
    if context.user_data.get('admin_authenticated'):
        from hasad_bot.handlers.admin import admin_panel
        return await admin_panel(update, context)

    # Ask for password
    await update.message.reply_text(
        "🔐 <b>أدخل كلمة مرور الإدارة:</b>",
        parse_mode="HTML"
    )
    return AWAIT_ADMIN_PASSWORD


async def handle_admin_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin password input"""
    uid = update.effective_user.id
    text = update.message.text.strip()

    if text == config.admin_password:
        context.user_data['admin_authenticated'] = True
        # Clear password from memory
        context.user_data.pop('admin_password', None)
        await update.message.reply_text(
            "✅ <b>تم التحقق بنجاح!</b>\n\n"
            "👋 أهلاً بك في لوحة الإدارة.",
            parse_mode="HTML"
        )
        # Show the full admin panel
        from hasad_bot.handlers.admin import admin_panel
        return await admin_panel(update, context)
    else:
        await update.message.reply_text(
            "❌ <b>كلمة المرور خاطئة!</b>\n\n"
            "🔄 أعد إدخال كلمة المرور أو أرسل /start للخروج.",
            parse_mode="HTML"
        )
        return AWAIT_ADMIN_PASSWORD


async def cmd_show_archived(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع البيانات المؤرشفة"""
    uid = update.effective_user.id

    if not await is_admin(uid):
        await update.message.reply_text("⛔ غير مصرح")
        return

    from hasad_bot.database import get_all_archived_credentials

    archives = await get_all_archived_credentials(20)

    if not archives:
        await update.message.reply_text("📭 لا توجد بيانات مؤرشفة")
        return

    text = "📦 **البيانات المؤرشفة (للإدارة فقط)**\n\n"
    for a in archives:
        date = time.strftime('%Y-%m-%d %H:%M', time.localtime(a['archived_at']))
        restored = "✅ تمت الاستعادة" if a['restored_at'] else "❌ لم تستعاد"

        text += f"👤 المستخدم: <code>{a['user_id']}</code> ({a['user_name']})\n"
        text += f"🔑 يوزر المنصة: <code>{a['platform_user']}</code>\n"
        text += f"📅 تاريخ الأرشفة: {date}\n"
        text += f"👨‍💼 بواسطة: {a['archived_by_name']}\n"
        text += f"📌 الحالة: {restored}\n"
        text += f"━━━━━━━━━━━━━━━━━━━━\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_restore_archive(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """استعادة بيانات مستخدم من الأرشيف"""
    uid = update.effective_user.id

    if not await is_admin(uid):
        await update.message.reply_text("⛔ غير مصرح")
        return

    admin_name = update.effective_user.full_name or update.effective_user.first_name or str(uid)

    from hasad_bot.database import restore_archived_credentials

    success, msg = await restore_archived_credentials(user_id, uid, admin_name)

    await update.message.reply_text(
        f"{'✅' if success else '❌'} {msg}",
        parse_mode=ParseMode.HTML
    )
