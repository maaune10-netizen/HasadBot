"""
subscriptions.py - subscription activation, key-based activation, and
payment-request approval/rejection flow.

Contains the persistence helpers plus admin-side approval/rejection
callbacks and user-side key activation.
"""
from __future__ import annotations

import aiosqlite
import time
from typing import List, Dict

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from hasad_bot.config import MAIN_MENU
from hasad_bot.admin_ops import approve_payment_request, reject_payment_request
from hasad_bot.database import (
    _db_pool,
    db_get_user,
    db_set_user,
    db_log,
    db_activate_key,
    create_user_subscription,
    update_user_last_active,
    is_admin,
    is_subscribed,
    get_user_remaining_homeworks,
    get_user_subscription,
)
from hasad_bot.logger import log_button_click
from hasad_bot.utils import kb_main, now_hijri, gregorian_to_hijri
from hasad_bot.datetime_utils import datetime, now_timestamp
from hasad_bot.handlers.constants import AWAIT_CUSTOM_REASON, AWAIT_CUSTOM_DAYS


# ==============================================================================
# Persistence helpers
# ==============================================================================

async def save_payment_request(uid: int, name: str, plan_id: str, plan_name: str,
                                price: float, method: str, method_name: str, note: str) -> int:
    """حفظ طلب الدفع في قاعدة البيانات وإرجاع رقم الطلب"""

    try:
        from hasad_bot.database import _db_pool
        import time

        print(f"💾 Saving payment request: user={uid}, name={name}")

        conn = await _db_pool.get_connection()

        # إنشاء جدول الطلبات إذا لم يكن موجوداً
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                plan_id TEXT,
                plan_name TEXT,
                price REAL,
                payment_method TEXT,
                payment_method_name TEXT,
                note TEXT,
                status TEXT DEFAULT 'pending',
                created_at REAL,
                processed_at REAL,
                processed_by INTEGER
            )
        """)
        await conn.commit()

        # إدخال الطلب
        await conn.execute("""
            INSERT INTO payment_requests
            (user_id, user_name, plan_id, plan_name, price, payment_method, payment_method_name, note, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (uid, name, plan_id, plan_name, price, method, method_name, note, 'pending', time.time()))

        # الحصول على آخر ID
        cursor = await conn.execute("SELECT last_insert_rowid()")
        row = await cursor.fetchone()
        request_id = row[0] if row else 0

        await conn.commit()

        print(f"✅ Payment request saved with ID: {request_id}")
        return request_id

    except Exception as e:
        print(f"❌ Error saving payment request: {e}")
        import traceback
        traceback.print_exc()
        return 0


async def get_all_payment_requests() -> List[Dict]:
    """جلب جميع طلبات الدفع"""

    try:
        conn = await _db_pool.get_connection()

        requests = []
        async with conn.execute("""
            SELECT * FROM payment_requests
            ORDER BY created_at DESC
            LIMIT 50
        """) as cursor:
            async for row in cursor:
                requests.append({
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "user_name": row["user_name"],
                    "plan_name": row["plan_name"],
                    "price": row["price"],
                    "payment_method": row["payment_method_name"],
                    "note": row["note"],
                    "status": row["status"],
                    "created_at": datetime.fromtimestamp(row["created_at"]).strftime('%Y-%m-%d %H:%M') if row["created_at"] else "—",
                    "processed_at": datetime.fromtimestamp(row["processed_at"]).strftime('%Y-%m-%d %H:%M') if row["processed_at"] else "—"
                })

        return requests
    except Exception as e:
        print(f"❌ Error getting payment requests: {e}")
        return []


# ==============================================================================
# Admin: list / view / approve / reject
# ==============================================================================

async def _get_pending_request_id(target_uid: int) -> int:
    """جلب أحدث معرّف طلب دفع pending لمستخدم (0 إذا لا يوجد)"""
    try:
        conn = await _db_pool.get_connection()
        async with conn.execute("""
            SELECT id FROM payment_requests
            WHERE user_id = ? AND status = 'pending'
            ORDER BY created_at DESC LIMIT 1
        """, (target_uid,)) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0
    except Exception as e:
        print(f"❌ Error getting pending request id: {e}")
        return 0


async def show_all_requests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع طلبات الدفع - الأزرار لا تختفي"""
    query = update.callback_query
    await query.answer("📋 جاري تحميل الطلبات...")

    if not await is_admin(query.from_user.id):
        await query.answer("⛔ غير مصرح", show_alert=True)
        return

    requests = await get_all_payment_requests()

    if not requests:
        # ✅ إرسال رسالة جديدة بدلاً من تعديل القديمة
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="📭 لا توجد طلبات دفع",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 تحديث", callback_data="show_all_requests")]
            ])
        )
        return

    # ✅ تجهيز النص والأزرار
    text = "📋 **قائمة طلبات الدفع**\n\n"
    buttons = []

    for req in requests:
        status_emoji = "🟡" if req["status"] == "pending" else ("✅" if req["status"] == "approved" else "❌")
        text += f"{status_emoji} **#{req['id']}** - {req['user_name']} ({req['user_id']})\n"
        text += f"   📦 {req['plan_name']} | 💰 {req['price']} ريال\n"
        text += f"   📅 {req['created_at']}\n\n"

        if req["status"] == "pending":
            buttons.append([
                InlineKeyboardButton(
                    f"📨 {req['user_name']}",
                    callback_data=f"view_request:{req['user_id']}"
                )
            ])

    # ✅ أزرار التحكم الثابتة (ما تختفي)
    control_buttons = [
        [InlineKeyboardButton("🔄 تحديث", callback_data="show_all_requests")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
    ]

    all_buttons = buttons + control_buttons if buttons else control_buttons

    # ✅ إرسال رسالة جديدة بدلاً من تعديل القديمة
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(all_buttons)
    )

    # ✅ إزالة الأزرار من الرسالة القديمة (اختياري)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except:
        pass


async def activate_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل طلب الاشتراك - الأزرار لا تختفي"""
    query = update.callback_query
    await query.answer("✅ جاري تجهيز التفعيل...")

    if not await is_admin(query.from_user.id):
        await query.answer("⛔ غير مصرح", show_alert=True)
        return

    target_uid = int(query.data.split(":")[1])
    context.user_data["activate_user_id"] = target_uid

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 7 أيام", callback_data=f"set_days:7:{target_uid}")],
        [InlineKeyboardButton("📆 30 يوم", callback_data=f"set_days:30:{target_uid}")],
        [InlineKeyboardButton("🎓 90 يوم", callback_data=f"set_days:90:{target_uid}")],
        [InlineKeyboardButton("✍️ أيام مخصصة", callback_data=f"custom_days:{target_uid}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"view_request:{target_uid}")]
    ])

    # ✅ استخدم send_message بدلاً من edit_message_text إذا كانت الرسالة بدون نص
    try:
        await query.edit_message_text(
            f"✅ **تفعيل اشتراك للمستخدم `{target_uid}`**\n\nاختر عدد الأيام:",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except Exception as e:
        if "There is no text in the message to edit" in str(e):
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=f"✅ **تفعيل اشتراك للمستخدم `{target_uid}`**\n\nاختر عدد الأيام:",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except:
                pass
        else:
            raise


async def set_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج اختيار عدد الأيام - مع إنشاء اشتراك في user_subscriptions"""
    query = update.callback_query
    await query.answer()

    if not await is_admin(query.from_user.id):
        await query.answer("⛔ غير مصرح", show_alert=True)
        return

    parts = query.data.split(":")
    days = int(parts[1])
    target_uid = int(parts[2])

    request_id = await _get_pending_request_id(target_uid)
    if not request_id:
        await query.edit_message_text("❌ لا يوجد طلب دفع pending لهذا المستخدم.")
        return

    ok, msg = await approve_payment_request(context.bot, request_id, days, actor="telegram")

    # أزرار ثابتة بعد التفعيل
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 العودة للطلبات", callback_data="show_all_requests")],
        [InlineKeyboardButton("📜 عرض السجل", callback_data=f"view_history:{target_uid}")]
    ])

    await query.edit_message_text(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def custom_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب عدد أيام مخصصة"""
    query = update.callback_query
    await query.answer()

    if not await is_admin(query.from_user.id):
        await query.answer("⛔ غير مصرح", show_alert=True)
        return

    target_uid = int(query.data.split(":")[1])
    context.user_data["custom_days_uid"] = target_uid

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 إلغاء", callback_data=f"back_to_request:{target_uid}")]
    ])

    await query.edit_message_text(
        f"✍️ **أيام مخصصة للمستخدم `{target_uid}`**\n\n"
        f"أرسل عدد الأيام (رقم فقط):\n"
        f"مثال: `30`",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

    return AWAIT_CUSTOM_DAYS  # 👈 الرجوع للحالة الجديدة


async def handle_custom_days_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأيام المخصصة - مع إنشاء اشتراك في user_subscriptions"""

    uid = update.effective_user.id
    target_uid = context.user_data.get("custom_days_uid")

    if not await is_admin(uid):
        await update.message.reply_text("⛔ غير مصرح")
        return ConversationHandler.END

    if not target_uid:
        await update.message.reply_text("❌ حدث خطأ، حاول مرة أخرى")
        return ConversationHandler.END

    try:
        days = int(update.message.text.strip())

        if days <= 0:
            await update.message.reply_text("❌ عدد الأيام يجب أن يكون أكبر من 0")
            return AWAIT_CUSTOM_DAYS

        request_id = await _get_pending_request_id(target_uid)
        if not request_id:
            await update.message.reply_text("❌ لا يوجد طلب دفع pending لهذا المستخدم.")
            return ConversationHandler.END

        ok, msg = await approve_payment_request(context.bot, request_id, days, actor="telegram")

        await update.message.reply_text(
            msg,
            parse_mode=ParseMode.HTML
        )

        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح")
        return AWAIT_CUSTOM_DAYS


async def reject_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رفض طلب الاشتراك - الأزرار لا تختفي"""
    query = update.callback_query
    await query.answer()

    if not await is_admin(query.from_user.id):
        await query.answer("⛔ غير مصرح", show_alert=True)
        return

    target_uid = int(query.data.split(":")[1])

    # ✅ أزرار ثابتة مع زر رجوع
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📷 صورة غير واضحة", callback_data=f"reject_reason:{target_uid}:unclear")],
        [InlineKeyboardButton("💰 مبلغ غير صحيح", callback_data=f"reject_reason:{target_uid}:wrong")],
        [InlineKeyboardButton("👤 مستخدم غير موجود", callback_data=f"reject_reason:{target_uid}:notfound")],
        [InlineKeyboardButton("✍️ سبب آخر", callback_data=f"reject_custom:{target_uid}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"view_request:{target_uid}")]
    ])

    # ✅ استخدم send_message بدلاً من edit_message_text
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=f"❌ <b>رفض طلب المستخدم</b> <code>{target_uid}</code>\n\nاختر سبب الرفض:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

    # ✅ إزالة الأزرار من الرسالة القديمة
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except:
        pass


async def reject_custom_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب سبب مخصص للرفض"""
    query = update.callback_query
    await query.answer()

    if not await is_admin(query.from_user.id):
        await query.answer("⛔ غير مصرح", show_alert=True)
        return

    target_uid = int(query.data.split(":")[1])
    context.user_data["custom_reject_uid"] = target_uid

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 إلغاء", callback_data=f"back_to_request:{target_uid}")]
    ])

    # ✅ استخدم send_message لأن الرسالة الأصلية يمكن أن تكون صورة
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=f"✍️ <b>سبب رفض مخصص للمستخدم</b> <code>{target_uid}</code>\n\n"
             f"📝 أرسل سبب الرفض الآن:\n"
             f"(سيتم إرساله للمستخدم كما هو)\n\n"
             f"<i>لإلغاء العملية اضغط على الزر أدناه</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

    # ✅ إزالة الأزرار من الرسالة القديمة
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except:
        pass

    # ✅ إرجاع الحالة لانتظار النص
    return AWAIT_CUSTOM_REASON


async def reject_reason_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج اختيار سبب الرفض - مع أزرار ثابتة"""
    query = update.callback_query
    await query.answer()

    if not await is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    target_uid = int(parts[1])
    reason_key = parts[2]

    # ✅ أسباب جاهزة بالعربية
    reasons = {
        "unclear": "صورة الإيصال غير واضحة، يرجى إرسال صورة واضحة",
        "wrong": "المبلغ غير صحيح، المطلوب هو 25 ريال للباقة الشهرية",
        "notfound": "لم نتمكن من العثور على حسابك في النظام"
    }
    reason_text = reasons.get(reason_key, "تم رفض طلب الاشتراك من قبل الإدارة")

    request_id = await _get_pending_request_id(target_uid)
    if not request_id:
        await query.edit_message_text("❌ لا يوجد طلب دفع pending لهذا المستخدم.")
        return

    ok, msg = await reject_payment_request(context.bot, request_id, reason_text, actor="telegram")

    # ✅ أزرار ثابتة بعد الرفض
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 العودة للطلبات", callback_data="show_all_requests")],
        [InlineKeyboardButton("📜 عرض السجل", callback_data=f"view_history:{target_uid}")]
    ])

    # ✅ تعديل الرسالة الحالية
    await query.edit_message_text(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def handle_custom_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج السبب المخصص للرفض"""

    uid = update.effective_user.id
    target_uid = context.user_data.get("custom_reject_uid")

    # ✅ تأكد أن المستخدم أدمن
    if not await is_admin(uid):
        await update.message.reply_text("⛔ غير مصرح")
        return ConversationHandler.END

    if not target_uid:
        await update.message.reply_text("❌ حدث خطأ، حاول مرة أخرى")
        return ConversationHandler.END

    reason_text = update.message.text.strip()

    if not reason_text:
        await update.message.reply_text("❌ الرجاء كتابة سبب الرفض\nأرسل السبب:")
        return AWAIT_CUSTOM_REASON

    request_id = await _get_pending_request_id(target_uid)
    if not request_id:
        await update.message.reply_text("❌ لا يوجد طلب دفع pending لهذا المستخدم.")
        return ConversationHandler.END

    ok, msg = await reject_payment_request(context.bot, request_id, reason_text, actor="telegram")

    # ✅ رسالة تأكيد للإدارة
    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML
    )

    # ✅ تنظيف
    context.user_data.pop("custom_reject_uid", None)

    return ConversationHandler.END


async def view_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تفاصيل طلب محدد - مع أزرار ثابتة"""
    query = update.callback_query
    await query.answer()

    target_uid = int(query.data.split(":")[1])

    requests = await get_all_payment_requests()
    target = None
    for req in requests:
        if req['user_id'] == target_uid and req['status'] == 'pending':
            target = req
            break

    if not target:
        await query.edit_message_text(
            f"❌ لا يوجد طلب pending للمستخدم {target_uid}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="show_all_requests")]
            ])
        )
        return

    # ✅ أزرار ثابتة ما تختفي
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تفعيل", callback_data=f"activate_request:{target_uid}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject_request:{target_uid}")
        ],
        [
            InlineKeyboardButton("🔙 العودة للطلبات", callback_data="show_all_requests"),
            InlineKeyboardButton("📜 عرض السجل", callback_data=f"view_history:{target_uid}")
        ]
    ])

    await query.edit_message_text(
        f"📨 **طلب اشتراك من {target['user_name']}**\n\n"
        f"🆔 المعرف: `{target_uid}`\n"
        f"📦 الباقة: {target['plan_name']}\n"
        f"💰 المبلغ: {target['price']} ريال\n"
        f"💳 طريقة الدفع: {target['payment_method']}\n"
        f"📝 ملاحظة: {target['note']}\n"
        f"📅 التاريخ: {target['created_at']}",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def back_to_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الرجوع لعرض طلب المستخدم"""
    query = update.callback_query
    await query.answer()

    target_uid = int(query.data.split(":")[1])
    await view_request_callback(update, context)


async def handle_custom_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأيام المخصصة"""
    uid = update.effective_user.id
    target_uid = context.user_data.get("activate_user_id")

    if not await is_admin(uid):
        return

    if not target_uid:
        await update.message.reply_text("❌ حدث خطأ")
        return

    try:
        days = int(update.message.text.strip())
        if days <= 0:
            await update.message.reply_text("❌ عدد الأيام يجب أن يكون أكبر من 0")
            return

        u = await db_get_user(target_uid)
        cur_exp = u.get("expiry_ts", 0) or 0
        if cur_exp < now_timestamp():
            cur_exp = now_timestamp()

        new_exp = cur_exp + days * 86400
        exp_h = gregorian_to_hijri(datetime.fromtimestamp(new_exp))
        await db_set_user(target_uid, expiry_ts=new_exp, expiry_hijri=exp_h)

        await update.message.reply_text(
            f"✅ **تم التفعيل!**\n\n👤 المستخدم: `{target_uid}`\n📅 المدة: {days} يوم",
            parse_mode=ParseMode.HTML
        )

        try:
            await context.bot.send_message(
                target_uid,
                f"🎉 **تم تفعيل اشتراكك!**\n\n📅 +{days} يوم",
                parse_mode=ParseMode.HTML
            )
        except:
            pass

    except ValueError:
        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح")

    finally:
        context.user_data.pop("activate_user_id", None)


# ==============================================================================
# Key-based subscription activation
# ==============================================================================

async def activate_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activate subscription with key - رسالة احترافية للطلاب"""
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "🔑 تفعيل اشتراك", "main")

    name = update.effective_user.first_name or "مستخدم"
    text = update.message.text.strip()
    args = context.args

    # ========== رسالة تفعيل الاشتراك الرئيسية ==========
    if text == "🔑 تفعيل اشتراك":
        context.user_data["waiting_for_key"] = True

        # نجيب معلومات المستخدم الحالية
        u = await db_get_user(uid) or {}
        is_sub = await is_subscribed(uid)
        trials = u.get("free_attempts", 0)

        # نحدد حالة المستخدم
        if is_sub:
            expiry = u.get("expiry_hijri", "—")
            status_msg = f"✅ أنت مشترك حالياً حتى {expiry}"
        else:
            status_msg = f"🎟️ عندك {trials} واجبات مجانية متبقية"

        # الرسالة الجديدة بعد التعديل
        welcome_text = f"""
<b>🎁 تفعيل الاشتراك في HASAD</b> 🎁

━━━━━━━━━━━━━━━━━━
👋 أهلاً {name}!

{status_msg}

━━━━━━━━━━━━━━━━━━
<b>💎 باقات حصاد:</b>
⚡ اسبوعي • 10 ريال
👑 شهري • 25 ريال
🚀 ترم • 60 ريال (3 شهور)

📋 <b>يرجى قراءة التفاصيل:</b>
اكتب <code>/plans</code> للمزيد من المعلومات

━━━━━━━━━━━━━━━━━━
<b>🔑 عندك كود تفعيل؟</b>
أرسل الكود الآن وسيتم تفعيله فوراً

📌 مثال: <code>HASAD-XXXX-XXXX-XXXX</code>

💳 <b>ما عندك كود؟</b>
تواصل مع الدعم الفني عشان تحصل واحد

━━━━━━━━━━━━━━━━━━
اضغط على "🆘 الدعم الفني" في القائمة الرئيسية
"""

        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.HTML
        )
        return MAIN_MENU

    # ========== باقي الكود لمعالجة الكود ==========
    key = args[0].strip() if args else text
    if not args and not context.user_data.get("waiting_for_key"):
        return MAIN_MENU

    # رسالة انتظار
    wait_msg = await update.message.reply_text(
        "⏳ <b>جاري التحقق من الكود...</b>\nالرجاء الانتظار قليلاً",
        parse_mode=ParseMode.HTML
    )

    res = await db_activate_key(uid, key, name)

    # نحذف رسالة الانتظار
    try:
        await wait_msg.delete()
    except:
        pass

    # رسالة نجاح أو فشل
    if res["success"]:
        success_text = f"""
<b>✅ تم التفعيل بنجاح!</b> 🎉

━━━━━━━━━━━━━━━━━━
{res['msg']}

<b>🚀 مبروك!</b> الآن يمكنك:
• حل واجبات غير محدودة
• استخدام جميع الميزات
• الاستمتاع بتجربة كاملة

━━━━━━━━━━━━━━━━━━
اضغط <b>"🤖 حل الواجبات"</b> وابدأ فوراً!
        """
        await update.message.reply_text(success_text, parse_mode=ParseMode.HTML)
    else:
        fail_text = f"""
<b>❌ فشل التفعيل</b>

━━━━━━━━━━━━━━━━━━
{res['msg']}

<b>💡 الأسباب المحتملة:</b>
• الكود غير صحيح
• الكود مستخدم مسبقاً
• خطأ في الكتابة

━━━━━━━━━━━━━━━━━━
حاول مرة أخرى أو اضغط على <b>"🆘 الدعم الفني"</b> للمساعدة
        """
        await update.message.reply_text(fail_text, parse_mode=ParseMode.HTML)

    await db_log(uid, "ACTIVATE_KEY", detail=key)

    context.user_data["waiting_for_key"] = False
    return MAIN_MENU
