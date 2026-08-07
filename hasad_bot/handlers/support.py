"""
support.py - support ticket flow (user side) and admin reply flow.

Contains:

* ``enter_support_room``  - user enters support room
* ``exit_support_room``   - user exits support room
* ``support_msg_handler`` - relay user messages to admin
* ``cb_view_support_history`` - admin views chat history
* ``cb_reply_support``    - admin starts reply
* ``admin_send_reply_done`` - admin sends reply
"""
from __future__ import annotations

import time

from loguru import logger
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from hasad_bot.config import config, MAIN_MENU
from hasad_bot.database import (
    is_bot_frozen,
    is_admin,
    update_user_last_active,
    db_log,
    log_user_message,
    db_get_user,
    is_subscribed,
    get_user_remaining_homeworks,
)
from hasad_bot.logger import log_button_click
from hasad_bot.utils import kb_main, now_hijri
from hasad_bot.handlers.constants import AWAIT_SUPPORT_MSG, AWAIT_ADMIN_REPLY
from hasad_bot.handlers.subscriptions import save_payment_request


async def enter_support_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enter support chat room"""
    uid = update.effective_user.id
    from hasad_bot.database import is_bot_frozen
    if await is_bot_frozen() and not await is_admin(uid):
        return  # لا يرد نهائياً

    await update_user_last_active(uid)
    await log_button_click(uid, "🆘 الدعم الفني", "main")

    reply_markup = ReplyKeyboardMarkup([["🔙 إنهاء المحادثة"]], resize_keyboard=True)

    await update.message.reply_text(
        "🎧 <b>أنت الآن في غرفة الدعم المباشر</b>\n\n"
        "يمكنك إرسال مشكلتك في عدة رسائل.\n"
        "يمكنك إرسال صور لتوضيح المشكلة.\n\n"
        "<i>(للخروج اضغط على 'إنهاء المحادثة')</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    return AWAIT_SUPPORT_MSG


async def exit_support_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exit support room"""
    uid = update.effective_user.id
    adm = await is_admin(uid)
    await update_user_last_active(uid)

    await update.message.reply_text(
        "✅ <b>تم إنهاء المحادثة.</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_main(uid, admin=adm)
    )
    return MAIN_MENU


async def support_msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle support messages - مع تخزين جميع أنواع الملفات"""

    # ✅ للتصحيح العميق
    print("=" * 60)
    print(f"📨 update: {update}")
    print(f"Has message: {update.message is not None}")
    if update.message:
        print(f"Message type: {type(update.message)}")
        print(f"Has document: {update.message.document is not None}")
        print(f"Has photo: {update.message.photo is not None}")
        print(f"Has text: {update.message.text is not None}")
    print("=" * 60)

    # ... باقي الكود
    uid = update.effective_user.id
    name = update.effective_user.full_name
    await update_user_last_active(uid)

    # ... باقي الكود
    # ✅ دعم جميع أنواع الملفات
    has_photo = bool(update.message.photo)
    has_document = bool(update.message.document)
    has_voice = bool(update.message.voice)
    has_video = bool(update.message.video)
    has_audio = bool(update.message.audio)

    msg_text = update.message.caption if (has_photo or has_document) else update.message.text
    msg_text = msg_text or "[رسالة بدون نص]"

    # تحديد نوع الملف للإدارة
    file_type = "text"
    file_id = None
    file_name = None

    if has_photo:
        file_type = "photo"
        file_id = update.message.photo[-1].file_id
        file_name = f"photo_{uid}_{int(time.time())}.jpg"
    elif has_document:
        file_type = "document"
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name or f"document_{uid}_{int(time.time())}"
    elif has_voice:
        file_type = "voice"
        file_id = update.message.voice.file_id
        file_name = f"voice_{uid}_{int(time.time())}.ogg"
    elif has_video:
        file_type = "video"
        file_id = update.message.video.file_id
        file_name = update.message.video.file_name or f"video_{uid}_{int(time.time())}.mp4"
    elif has_audio:
        file_type = "audio"
        file_id = update.message.audio.file_id
        file_name = update.message.audio.file_name or f"audio_{uid}_{int(time.time())}.mp3"

    # تسجيل الرسالة

    # ========== بناء أزرار الإدارة ==========
    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"💬 الرد على {name}", callback_data=f"reply_support:{uid}"),
            InlineKeyboardButton("✅ تفعيل الاشتراك", callback_data=f"activate_request:{uid}")
        ],
        [
            InlineKeyboardButton("❌ رفض الطلب", callback_data=f"reject_request:{uid}"),
            InlineKeyboardButton("📜 عرض جميع الطلبات", callback_data="show_all_requests")
        ],
        [InlineKeyboardButton("📜 عرض السجل", callback_data=f"view_history:{uid}")]
    ])

    try:
        # حفظ الطلب في قاعدة البيانات
        request_id = None
        local_file_path = None

        if has_photo or has_document or has_voice or has_video or has_audio:
            # تحميل وحفظ الملف
            from hasad_bot.database import download_and_save_file, save_file_reference

            local_file_path = await download_and_save_file(
                bot=context.bot,
                file_id=file_id,
                file_type=file_type,
                file_name=file_name,
                chat_id=update.message.chat_id,
                message_id=update.message.message_id,
                user_id=uid
            )

            if local_file_path:
                await save_file_reference(
                    file_path=local_file_path,
                    file_id=file_id,
                    file_type=file_type,
                    file_name=file_name,
                    user_id=uid,
                    chat_id=update.message.chat_id,
                    message_id=update.message.message_id
                )

            # حفظ طلب الدفع
            request_id = await save_payment_request(
                uid, name, "manual", "طلب اشتراك",
                float(0), "manual", "طلب يدوي", msg_text
            )

        # إرسال للإدارة
        caption_text = (
            f"📨 <b>طلب دعم جديد</b>\n\n"
            f"👤 المستخدم: <b>{name}</b>\n"
            f"🆔 المعرف: <code>{uid}</code>\n"
            f"📝 ملاحظة: {msg_text}\n"
            f"📅 الوقت: {now_hijri()}\n"
            f"📁 نوع الملف: <b>{file_type}</b>"
        )

        if has_photo:
            await context.bot.send_photo(
                chat_id=config.admin_id,
                photo=file_id,
                caption=caption_text,
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard
            )
        elif has_document:
            await context.bot.send_document(
                chat_id=config.admin_id,
                document=file_id,
                caption=caption_text,
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard
            )
        elif has_voice:
            await context.bot.send_voice(
                chat_id=config.admin_id,
                voice=file_id,
                caption=caption_text,
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard
            )
        elif has_video:
            await context.bot.send_video(
                chat_id=config.admin_id,
                video=file_id,
                caption=caption_text,
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard
            )
        elif has_audio:
            await context.bot.send_audio(
                chat_id=config.admin_id,
                audio=file_id,
                caption=caption_text,
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard
            )
        else:
            await context.bot.send_message(
                chat_id=config.admin_id,
                text=caption_text,
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard
            )

        # رد للمستخدم
        await update.message.reply_text(
            "📩 <i>تم إرسال رسالتك للإدارة... سيردون عليك قريباً</i>\n\n"
            "يمكنك الاستمرار في إرسال رسائل أخرى أو الضغط على '🔙 إنهاء المحادثة' للخروج.",
            parse_mode=ParseMode.HTML
        )

        await db_log(uid, "SUPPORT_MSG", detail=f"{file_type}: {msg_text}")

    except Exception as e:
        logger.error(f"Support Dispatch Error: {e}")
        await update.message.reply_text("❌ حدث خطأ داخلي. حاول مرة أخرى.")

    return AWAIT_SUPPORT_MSG


async def cb_view_support_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View support history"""
    q = update.callback_query
    await q.answer()

    if not await is_admin(q.from_user.id):
        return

    target_uid = int(q.data.split(":")[1])
    user_data = await db_get_user(target_uid)
    user_name = user_data.get('name', 'طالب') if user_data else str(target_uid)

    import aiosqlite
    async with aiosqlite.connect(config.db_file) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT action, detail, created_at FROM logs WHERE telegram_id=? AND action IN ('SUPPORT_MSG', 'SUPPORT_REPLY') ORDER BY created_at DESC LIMIT 15",
            (target_uid,)
        ) as c:
            rows = await c.fetchall()

    if not rows:
        await q.message.reply_text(f"📭 لا يوجد سجل لـ <b>{user_name}</b>.", parse_mode=ParseMode.HTML)
        return

    history_text = f"📜 <b>سجل محادثات {user_name} ({target_uid}):</b>\n\n"

    for r in reversed(rows):
        dt = datetime.fromtimestamp(r["created_at"]).strftime('%Y-%m-%d %H:%M')
        if r["action"] == "SUPPORT_MSG":
            sender = f"👤 {user_name}"
        else:
            sender = "🛡️ الإدارة"
        history_text += f"<b>{sender}</b> <i>({dt})</i>:\n{r['detail']}\n〰️〰️〰️\n"

    await q.message.reply_text(history_text, parse_mode=ParseMode.HTML)


async def cb_reply_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start admin reply"""
    q = update.callback_query
    await q.answer()
    target_uid = q.data.split(":")[1]
    context.user_data["reply_to_uid"] = target_uid

    # ✅ تسجيل الضغطة
    from hasad_bot.database import log_user_message

    await log_user_message(
        user_id=q.from_user.id,
        user_name=q.from_user.full_name,
        message_text=f"بدأ الرد على المستخدم {target_uid}",
        message_type="callback",
        is_response=False
    )

    await q.message.reply_text(
        f"✍️ <b>أنت ترد على:</b> <code>{target_uid}</code>.\n\n"
        f"أرسل نص أو صورة مع نص.\n"
        f"/cancel للإلغاء.",
        parse_mode=ParseMode.HTML
    )
    return AWAIT_ADMIN_REPLY


async def admin_send_reply_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send admin reply to user"""
    target_uid = context.user_data.get("reply_to_uid")
    if not target_uid:
        await update.message.reply_text("❌ فقدت عنوان المستخدم.")
        return MAIN_MENU

    has_photo = bool(update.message.photo)
    reply_text = update.message.caption if has_photo else update.message.text
    reply_text = reply_text or "[صورة بدون نص]"

    # ✅ تسجيل رد الأدمن
    from hasad_bot.database import log_user_message

    await log_user_message(
        user_id=update.effective_user.id,
        user_name=update.effective_user.full_name,
        message_text=reply_text,
        message_type="admin_reply",
        chat_id=update.message.chat_id,
        message_id=update.message.message_id,
        is_response=True,
        response_to=str(target_uid)
    )

    # باقي الكود...
    try:
        if has_photo:
            photo_id = update.message.photo[-1].file_id
            await context.bot.send_photo(
                int(target_uid),
                photo=photo_id,
                caption=f"🛡️ <b>رد من الدعم:</b>\n\n{reply_text}",
                parse_mode=ParseMode.HTML
            )
            await db_log(int(target_uid), "SUPPORT_REPLY", detail=reply_text, source="ADMIN")
        else:
            # النص فقط: تفويض الإرسال + التسجيل + التدقيق للخدمة المشتركة (admin_ops)
            from hasad_bot.admin_ops import send_support_reply
            ok, msg = await send_support_reply(
                context.bot,
                int(target_uid),
                reply_text,
                actor="telegram",
                admin_id=update.effective_user.id,
                admin_name=update.effective_user.full_name or "telegram",
            )
            if not ok:
                await update.message.reply_text(f"❌ تعذر الإرسال: {msg}", parse_mode=ParseMode.HTML)
                context.user_data["reply_to_uid"] = None
                return MAIN_MENU

        await update.message.reply_text(f"✅ تم إرسال الرد إلى <code>{target_uid}</code>", parse_mode=ParseMode.HTML)

    except Exception as e:
        await update.message.reply_text(f"❌ تعذر الإرسال: {e}")

    context.user_data["reply_to_uid"] = None
    return MAIN_MENU


# Local alias since support_msg_handler uses datetime.fromtimestamp directly.
from hasad_bot.datetime_utils import datetime  # noqa: E402
