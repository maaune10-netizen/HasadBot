"""
unlock.py - account unlock / lock request flow.

Contains the user-initiated unlock request, admin approve/reject with
predefined or custom reasons, plus the simple ``back`` callback handler.
"""
from __future__ import annotations

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from hasad_bot.config import config, MAIN_MENU
from hasad_bot.database import (
    is_admin,
    db_get_user,
    db_set_user,
)
from hasad_bot.utils import now_hijri
from hasad_bot.handlers.constants import AWAIT_CUSTOM_REASON


async def cb_request_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unlock request - نسخة محسنة"""
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    user_data = await db_get_user(uid)

    if not user_data:
        await q.edit_message_text("❌ المستخدم غير موجود.")
        return

    await db_set_user(uid, lock_request=1)

    # أزرار للإدارة (موافق / رفض)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ موافق - فك القفل", callback_data=f"unlock_approve:{uid}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"unlock_reject:{uid}")
        ]
    ])

    await context.bot.send_message(
        config.admin_id,
        f"🔓 <b>طلب فك قفل جديد</b> 🔓\n\n"
        f"👤 <b>المستخدم:</b> {user_data.get('name', 'غير معروف')}\n"
        f"🆔 <b>المعرف:</b> <code>{uid}</code>\n"
        f"🎓 <b>حساب المنصة:</b> <code>{user_data.get('dars360_user', '—')}</code>\n"
        f"📅 <b>التاريخ:</b> {now_hijri()}\n\n"
        f"📌 اختر الإجراء المناسب:",

        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

    await q.edit_message_text(
        "✅ <b>تم إرسال طلب فك القفل للإدارة</b>\n\n"

        "سيتم الرد عليك في أقرب وقت ممكن.",
        parse_mode=ParseMode.HTML,
    )


async def cb_unlock_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """موافقة على فك القفل - مع أرشفة البيانات"""
    q = update.callback_query
    await q.answer()

    if not await is_admin(q.from_user.id):
        await q.answer("⛔ غير مصرح", show_alert=True)
        return

    uid_i = int(q.data.split(":")[1])
    admin_id = q.from_user.id
    admin_name = q.from_user.full_name or q.from_user.first_name or str(admin_id)

    # ✅ أرشفة بيانات المستخدم قبل فك القفل
    from hasad_bot.database import archive_user_credentials
    success, msg = await archive_user_credentials(uid_i, admin_id, admin_name, "فك القفل بواسطة الإدارة")

    if not success:
        await q.edit_message_text(f"❌ فشل فك القفل: {msg}")
        return

    # إشعار للمستخدم
    try:
        await context.bot.send_message(
            uid_i,
            "🔓 <b>تم فك قفل حسابك بنجاح!</b>\n\n"
            "✅ يمكنك الآن ربط حساب منصة جديد.\n"
            "✅ اضغط على 🔗 ربط المنصة",
            parse_mode=ParseMode.HTML
        )
    except:
        pass

    # تحديث رسالة الإدارة
    await q.edit_message_text(
        f"✅ <b>تم فك القفل والأرشفة</b>\n"
        f"👤 المستخدم: <code>{uid_i}</code>\n"
        f"👨‍💼 بواسطة: {admin_name}\n"
        f"📦 تم أرشفة البيانات بنجاح\n"
        f"📅 {now_hijri()}",
        parse_mode=ParseMode.HTML
    )


async def cb_unlock_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رفض طلب فك القفل مع سبب"""
    q = update.callback_query
    await q.answer()

    if not await is_admin(q.from_user.id):
        await q.answer("⛔ غير مصرح", show_alert=True)
        return

    uid_i = int(q.data.split(":")[1])

    # أزرار الأسباب الجاهزة
    reasons_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📌 الحساب مرتبط بمستخدم آخر", callback_data=f"unlock_reason:{uid_i}:مستخدم_آخر")],
        [InlineKeyboardButton("📌 طلب مكرر (تم الرفض سابقاً)", callback_data=f"unlock_reason:{uid_i}:طلب_مكرر")],
        [InlineKeyboardButton("📌 انتهاء الاشتراك", callback_data=f"unlock_reason:{uid_i}:انتهاء_الاشتراك")],
        [InlineKeyboardButton("📌 مخالفة سياسة الاستخدام", callback_data=f"unlock_reason:{uid_i}:مخالفة")],
        [InlineKeyboardButton("✍️ سبب آخر (اكتبه)", callback_data=f"unlock_custom_reason:{uid_i}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"unlock_back:{uid_i}")]
    ])

    await q.edit_message_text(
        f"❌ <b>رفض طلب فك القفل</b>\n\n"
        f"المستخدم: <code>{uid_i}</code>\n\n"
        f"📌 اختر سبب الرفض:",
        parse_mode=ParseMode.HTML,
        reply_markup=reasons_keyboard
    )


async def cb_unlock_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة سبب الرفض وإرسال الرد للمستخدم"""
    q = update.callback_query
    await q.answer()

    if not await is_admin(q.from_user.id):
        return

    parts = q.data.split(":")
    uid_i = int(parts[1])
    reason_key = parts[2]

    # أسباب جاهزة بالعربية
    reasons = {
        "مستخدم_آخر": "هذا الحساب مرتبط بمستخدم آخر في النظام. لا يمكن فك القفل.",
        "طلب_مكرر": "تم رفض طلبك سابقاً. يرجى التواصل مع الدعم الفني.",
        "انتهاء_الاشتراك": "لا يمكن فك القفل لأن اشتراكك منتهي. يرجى تجديد الاشتراك أولاً.",
        "مخالفة": "تم رفض الطلب بسبب مخالفة سياسة الاستخدام.",
        "سبب_آخر": "تم رفض طلب فك القفل من قبل الإدارة. يرجى التواصل مع الدعم الفني لمزيد من المعلومات."
    }

    reason_text = reasons.get(reason_key, "تم رفض طلب فك القفل من قبل الإدارة.")

    # تحديث حالة المستخدم
    await db_set_user(uid_i, lock_request=0)

    # إرسال الرفض للمستخدم مع السبب
    try:
        await context.bot.send_message(
            uid_i,
            f"❌ <b>تم رفض طلب فك القفل</b>\n\n"
            f"📌 <b>السبب:</b> {reason_text}\n\n"
            f"💡 إذا كان لديك استفسار، تواصل مع الدعم الفني.",
            parse_mode=ParseMode.HTML
        )
    except:
        pass

    # تحديث رسالة الإدارة
    await q.edit_message_text(
        f"❌ <b>تم رفض الطلب</b>\n"
        f"المستخدم: <code>{uid_i}</code>\n"
        f"السبب: {reason_text}\n"
        f"التاريخ: {now_hijri()}",
        parse_mode=ParseMode.HTML
    )


async def cb_unlock_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رجوع إلى خيارات الرفض"""
    q = update.callback_query
    await q.answer()

    if not await is_admin(q.from_user.id):
        return

    uid_i = int(q.data.split(":")[1])

    # إعادة عرض خيارات الرفض
    reasons_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📌 الحساب مرتبط بمستخدم آخر", callback_data=f"unlock_reason:{uid_i}:مستخدم_آخر")],
        [InlineKeyboardButton("📌 طلب مكرر (تم الرفض سابقاً)", callback_data=f"unlock_reason:{uid_i}:طلب_مكرر")],
        [InlineKeyboardButton("📌 انتهاء الاشتراك", callback_data=f"unlock_reason:{uid_i}:انتهاء_الاشتراك")],
        [InlineKeyboardButton("📌 مخالفة سياسة الاستخدام", callback_data=f"unlock_reason:{uid_i}:مخالفة")],
        [InlineKeyboardButton("✍️ سبب آخر (اكتبه)", callback_data=f"unlock_custom_reason:{uid_i}")],
        [InlineKeyboardButton("🔙 إلغاء", callback_data=f"unlock_cancel:{uid_i}")]
    ])

    await q.edit_message_text(
        f"❌ <b>رفض طلب فك القفل</b>\n\n"
        f"المستخدم: <code>{uid_i}</code>\n\n"
        f"📌 اختر سبب الرفض:",
        parse_mode=ParseMode.HTML,
        reply_markup=reasons_keyboard
    )


async def cb_unlock_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء عملية الرفض"""
    q = update.callback_query
    await q.answer()

    if not await is_admin(q.from_user.id):
        return

    uid_i = int(q.data.split(":")[1])

    # العودة للرسالة الأصلية
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ موافق - فك القفل", callback_data=f"unlock_approve:{uid_i}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"unlock_reject:{uid_i}")
        ]
    ])

    await q.edit_message_text(
        f"🔓 <b>طلب فك قفل</b> 🔓\n\n"
        f"المستخدم: <code>{uid_i}</code>\n\n"
        f"📌 اختر الإجراء المناسب:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def cb_unlock_custom_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب سبب مخصص من الإدارة"""
    q = update.callback_query
    await q.answer()

    if not await is_admin(q.from_user.id):
        return ConversationHandler.END  # ✅ إذا مو أدمن، ننهي

    uid_i = int(q.data.split(":")[1])

    # حفظ معرف المستخدم في context
    context.user_data["custom_reason_uid"] = uid_i

    # طلب كتابة السبب
    await q.edit_message_text(
        f"✍️ <b>سبب الرفض المخصص</b>\n\n"
        f"المستخدم: <code>{uid_i}</code>\n\n"
        f"📝 <b>أرسل سبب الرفض الآن:</b>\n"
        f"(سيتم إرساله للمستخدم كما هو)\n\n"
        f"<i>لإلغاء العملية أرسل /cancel</i>",
        parse_mode=ParseMode.HTML
    )

    # ✅ إرجاع الحالة لانتظار النص
    return AWAIT_CUSTOM_REASON


async def handle_custom_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة السبب المخصص الذي كتبه الأدمن"""

    # ✅ أضف هذه الأسطر في أول الدالة
    print("="*60)
    print("🔥🔥🔥 handle_custom_reason CALLED! 🔥🔥🔥")
    print(f"User ID: {update.effective_user.id}")
    print(f"Message: {update.message.text}")
    print("="*60)

    uid = update.effective_user.id
    # ... باقي الكود
    if not await is_admin(uid):
        await update.message.reply_text("⛔ غير مصرح")
        return ConversationHandler.END

    reason_text = update.message.text.strip()
    target_uid = context.user_data.get("custom_reason_uid")

    if not target_uid:
        await update.message.reply_text("❌ حدث خطأ، حاول مرة أخرى.")
        return ConversationHandler.END

    if not reason_text:
        await update.message.reply_text("❌ الرجاء كتابة سبب الرفض.")
        return AWAIT_CUSTOM_REASON  # ✅ يبقى في نفس الحالة

    # تحديث حالة المستخدم
    await db_set_user(target_uid, lock_request=0)

    # إرسال الرفض للمستخدم مع السبب المخصص
    try:
        await context.bot.send_message(
            target_uid,
            f"❌ <b>تم رفض طلب فك القفل</b>\n\n"
            f"📌 <b>السبب:</b> {reason_text}\n\n"
            f"💡 إذا كان لديك استفسار، تواصل مع الدعم الفني.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(f"❌ فشل الإرسال: {e}")

    # تأكيد للإدارة
    await update.message.reply_text(
        f"✅ <b>تم رفض الطلب</b>\n"
        f"المستخدم: <code>{target_uid}</code>\n"
        f"السبب: {reason_text}\n"
        f"التاريخ: {now_hijri()}",
        parse_mode=ParseMode.HTML
    )

    # تنظيف
    context.user_data.pop("custom_reason_uid", None)

    return ConversationHandler.END  # ✅ ننهي المحادثة


async def cb_back(update: Update, context):
    """Back button"""
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("🔙 عد إلى قائمة المستخدمين.")
