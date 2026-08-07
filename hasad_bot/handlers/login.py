"""
login.py - dars360 platform linking flow.

Contains the conversation-handler steps for selecting a school, entering
the platform username and password, plus the ``/login`` command and
school-selection callbacks.
"""
from __future__ import annotations

import asyncio

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from loguru import logger

from hasad_bot.config import (
    MAIN_MENU,
    AWAIT_LOGIN_USERNAME,
    AWAIT_LOGIN_PASSWORD,
)
from hasad_bot.database import (
    is_bot_frozen,
    is_admin,
    update_user_last_active,
    db_get_user,
    is_subscribed,
    get_user_remaining_homeworks,
)
from hasad_bot.logger import log_button_click
from hasad_bot.utils import kb_main, now_hijri
from hasad_bot.login_manager import unified_login
from hasad_bot.handlers.infrastructure import rate_limit


async def cancel_school_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء اختيار المدرسة والعودة للقائمة الرئيسية (نفس رسالة /start)"""
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    adm = await is_admin(uid)

    # الحصول على اسم المستخدم
    user = update.effective_user
    name = user.first_name or "مستخدم" if user else "مستخدم"

    # جلب بيانات المستخدم
    u = await db_get_user(uid) or {}
    sub = await is_subscribed(uid)

    # تنظيف context
    context.user_data.pop("selected_school_id", None)
    context.user_data.pop("pending_user", None)

    # إزالة الأزرار من الرسالة القديمة
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except:
        pass

    # حساب الرصيد
    from hasad_bot.database import get_user_remaining_homeworks
    remaining_hw = await get_user_remaining_homeworks(uid)

    if adm:
        badge = "👑 أدمن"
    elif sub:
        badge = "✅ مشترك"
    else:
        badge = "❌ غير مشترك"

    if adm:
        subscription_text = "♾️ دائم"
    elif sub:
        subscription_text = f"📆 {u.get('expiry_hijri', '—')}"
    else:
        subscription_text = "🔑 /shop للاشتراك"

    if sub:
        trials_text = f"🎟️ <b>رصيدك المتبقي: {remaining_hw} واجب</b>"
    else:
        trials_text = f"🎁 واجبات مجانية: <b>{u.get('free_attempts', 0)}</b>"

    # ✅ رسالة الترحيب الرسمية (نفس رسالة /start)
    welcome_msg = (
        "🌾 <b>أهلاً بك في حصاد</b> 🌾\n\n"
        f"👋 مرحباً {name}،\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>اليوم:</b> {now_hijri()}\n"
        f"👑 <b>رتبتك:</b> {badge}\n"
        f"📆 <b>الاشتراك:</b> {subscription_text}\n"
        f"{trials_text}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚜 <b>حصاد</b> في خدمتك!\n"
        "اختر من القائمة ما يناسبك 👇"
    )

    await query.message.reply_text(
        welcome_msg,
        parse_mode=ParseMode.HTML,
        reply_markup=kb_main(uid, admin=adm, is_subscribed=sub)
    )


async def select_school_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج اختيار المدرسة"""
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    school_id = query.data.split(":")[1]

    # حفظ المدرسة المختارة في context
    context.user_data["selected_school_id"] = school_id

    # الحصول على اسم المدرسة
    from hasad_bot.login_manager import get_school_info
    school_info = get_school_info(school_id)
    school_name = school_info["name"] if school_info else school_id

    # ✅ إزالة الأزرار من الرسالة القديمة أولاً
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except:
        pass

    # ✅ ثم إرسال رسالة جديدة بدلاً من تعديل القديمة
    msg = (
        f"<b>🔐 ربط حساب منصة درس 360</b>\n\n"
        f"🏫 <b>المدرسة المختارة:</b> {school_name}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>📌 الخطوة 1 من 2</b>\n\n"
        "<b>👤 أرسل اسم المستخدم</b>\n"
        "• الأرقام فقط (مثال: <code>123321158</code>)\n"
        "• تأكد من إدخال الرقم الصحيح\n\n"
        "<b>🔒 ملاحظة أمان:</b>\n"
        "• جميع البيانات مشفرة بأعلى معايير الأمان\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>❌ للإلغاء:</b> /cancel"
    )

    # ✅ إرسال رسالة جديدة (بدلاً من edit)
    await query.message.reply_text(
        msg,
        parse_mode='HTML',
        reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True)
    )

    # ✅ لا ترجع أي شيء، دع الـ ConversationHandler يتولى الأمر
    # return AWAIT_LOGIN_USERNAME  # ❌ أزل هذا السطر


@rate_limit
async def cmd_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Login command handler - مع اختيار المدرسة"""

    uid = update.effective_user.id
    from hasad_bot.database import is_bot_frozen
    if await is_bot_frozen() and not await is_admin(uid):
        return

    await update_user_last_active(uid)
    await log_button_click(uid, "🔗 ربط المنصة", "main")

    u = await db_get_user(uid) or {}

    # إذا كان عنده حساب مرتبط مسبقاً
    if u.get("dars360_user"):
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("📨 طلب فك القفل", callback_data=f"request_unlock:{uid}")
        ]])
        await update.message.reply_text(
            f"<b>⚠️ تنبيه</b>\n\n"
            f"<b>حساب التيليجرام هذا مرتبط مسبقاً بحساب منصة درس 360:</b>\n"
            f"<code>{u['dars360_user']}</code>\n\n"
            f"🔒 <b>لماذا؟</b>\n"
            f"نظام الأمان يربط كل حساب تيليجرام بحساب منصة واحد فقط.\n\n"
            f"❌ <b>لا يمكنك الربط بحساب آخر</b>\n"
            f"إذا كنت تريد تغيير الحساب، اضغط على الزر أدناه لإرسال طلب فك القفل للإدارة.",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return MAIN_MENU

    # ✅ عرض قائمة المدارس
    from hasad_bot.login_manager import get_schools_list

    schools = get_schools_list()

    # إنشاء أزرار للمدارس (صفين في كل صف)
    school_buttons = []
    for i in range(0, len(schools), 2):
        row = []
        for school in schools[i:i+2]:
            row.append(InlineKeyboardButton(
                school["name"],
                callback_data=f"select_school:{school['id']}"
            ))
        school_buttons.append(row)

    # إضافة زر إلغاء
    school_buttons.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel")])

    await update.message.reply_text(
        "<b>🏫 اختر مدرستك:</b>\n\n"
        "اختر المدرسة التي تدرس فيها من القائمة أدناه:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(school_buttons)
    )
    return MAIN_MENU


async def login_got_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle username input - احترافية"""
    text = update.message.text.strip()
    uid = update.effective_user.id
    adm = await is_admin(uid)

    await update_user_last_active(uid)

    # التحقق من أنه في العملية الصحيحة
    if text == "🔗 ربط المنصة":
        await update.message.reply_text(
            "<b>⚠️ أنت بالفعل في عملية الربط</b>\n\n"
            "الرجاء إدخال <b>اسم المستخدم</b>:\n"
            "مثال: <code>1234567890</code> أو <code></code>",
            parse_mode='HTML'
        )
        return AWAIT_LOGIN_USERNAME

    # إلغاء العملية
    if text in ["❌ إلغاء", "/cancel"]:
        await update.message.reply_text(
            "✅ تم إلغاء عملية الربط.",
            reply_markup=kb_main(uid, admin=adm)
        )
        return MAIN_MENU

    # حفظ اسم المستخدم (أياً كان)
    context.user_data["pending_user"] = text

    # طلب كلمة المرور
    msg = (
        "<b>✅ تم استلام اسم المستخدم</b>\n\n"
        f"<b>👤 اليوزرنيم:</b> <code>{text}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>📌 الخطوة 2 من 2</b>\n\n"
        "<b>🔑 أرسل كلمة المرور</b>\n"
        "• سيتم تشفيرها فور استلامها\n"
        "• التشفير يضمن عدم إمكانية قراءتها\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>❌ للإلغاء:</b> /cancel"
    )

    await update.message.reply_text(
        msg,
        parse_mode='HTML',
        reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True)
    )
    return AWAIT_LOGIN_PASSWORD


async def login_got_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle password input - مع دعم المدرسة"""
    text = update.message.text.strip()
    uid = update.effective_user.id
    name = update.effective_user.first_name or "مستخدم"
    tg_user = update.effective_user.username or ""
    adm = await is_admin(uid)

    await update_user_last_active(uid)

    # إلغاء العملية
    if text in ["❌ إلغاء", "/cancel"]:
        context.user_data.pop("pending_user", None)
        context.user_data.pop("selected_school_id", None)  # ✅ تنظيف المدرسة أيضاً
        await update.message.reply_text(
            "✅ تم إلغاء عملية الربط.",
            reply_markup=kb_main(uid, admin=adm)
        )
        return MAIN_MENU

    # ✅ استرجاع اسم المستخدم (من context.user_data)
    username = context.user_data.pop("pending_user", "")
    if not username:
        await update.message.reply_text(
            "<b>❌ خطأ في العملية</b>\n\n"
            "الرجاء البدء من جديد: /start",
            parse_mode='HTML',
            reply_markup=kb_main(uid, admin=adm)
        )
        return MAIN_MENU

    # ✅ استرجاع المدرسة المختارة
    school_id = context.user_data.pop("selected_school_id", "alamjad1")

    # حذف كلمة المرور من الشات (للأمان)
    try:
        await update.message.delete()
    except:
        pass

    # رسالة الانتظار
    wait_msg = await context.bot.send_message(
        uid,
        "<b>⏳ جاري ربط الحساب...</b>\n"
        f"🏫 المدرسة: {school_id}\n"
        "• التحقق من البيانات\n"
        "• تشفير المعلومات\n"
        "• الرجاء الانتظار قليلاً",
        parse_mode='HTML'
    )

    from hasad_bot.login_manager import unified_login

    async def login_task():
        try:
            # ✅ استدعاء unified_login مع school_id
            success, msg = await unified_login(
                username=username,
                password=text,
                uid=uid,
                name=name,
                tg_user=tg_user,
                bot=context.bot,
                school_id=school_id  # 👈 المدرسة المختارة
            )

            # حذف رسالة الانتظار
            try:
                await context.bot.delete_message(uid, wait_msg.message_id)
            except:
                pass

            if success:
                await context.bot.send_message(
                    uid,
                    f"<b>✅ تم ربط الحساب بنجاح!</b>\n\n"
                    f"🏫 المدرسة: {school_id}\n\n"
                    "🚀 الآن يمكنك استخدام البوت:\n"
                    "• حل الواجبات\n"
                    "• متابعة حسابك\n"
                    "• والمزيد...",
                    parse_mode='HTML',
                    reply_markup=kb_main(uid, admin=adm)
                )
            else:
                await context.bot.send_message(
                    uid,
                    f"<b>❌ فشل الربط</b>\n\n"
                    f"{msg}\n\n"
                    f"💡 حاول مرة أخرى أو تواصل مع الدعم الفني.",
                    parse_mode='HTML',
                    reply_markup=kb_main(uid, admin=adm)
                )

        except Exception as e:
            logger.error(f"Login task error: {e}")
            try:
                await context.bot.delete_message(uid, wait_msg.message_id)
            except:
                pass
            await context.bot.send_message(
                uid,
                "<b>❌ حدث خطأ غير متوقع</b>\n\n"
                "الرجاء المحاولة مرة أخرى لاحقاً.",
                parse_mode='HTML',
                reply_markup=kb_main(uid, admin=adm)
            )

    asyncio.create_task(login_task())

    return MAIN_MENU
