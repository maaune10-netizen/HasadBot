"""
payment.py - shop, invoicing, and payment-flow handlers.

Contains the LATER definitions of duplicated payment handlers (per
the original bot_handlers.py LATER-wins rule):

* ``webapp_data_handler``      (L1481)
* ``pre_checkout_handler``     (L1472)
* ``successful_payment_handler`` (L1421)
* ``open_shop``                (L5117)
* ``shop_plan_callback``       (L5170)
* ``shop_pay_callback``        (L5233)
* ``send_stars_invoice``       (L5278)
* ``show_bank_instructions``   (L5323)
* ``show_stc_instructions``    (L5356)
* ``shop_back_callback``       (L5383)
* ``handle_pay_stars_callback``
"""
from __future__ import annotations

import json
import time

from loguru import logger
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from hasad_bot.config import MAIN_MENU
from hasad_bot.database import (
    update_user_last_active,
    db_get_user,
    db_set_user,
    db_log,
    create_user_subscription,
    is_admin,
    is_subscribed,
    get_user_remaining_homeworks,
    get_user_subscription,
)
from hasad_bot.logger import log_button_click
from hasad_bot.utils import gregorian_to_hijri
from hasad_bot.datetime_utils import datetime, now_timestamp
from hasad_bot.handlers.constants import PAYMENT_SETTINGS, PLANS
from hasad_bot.utils import admin_trace


# ==============================================================================
# create_stars_invoice_link (NOT duplicated - kept here for shop workflow)
# ==============================================================================

async def create_stars_invoice_link(plan_id: str, user_id: int, context) -> str:
    """
    إنشاء رابط فاتورة دفع بالنجوم
    """
    from telegram import LabeledPrice

    plans = {
        "weekly": {
            "title": "⭐ اشتراك اسبوعي - HASAD",
            "description": "الباقة الاسبوعية: 7 أيام - 25 واجب",
            "stars": PAYMENT_SETTINGS.get("stars_weekly", 150),
            "payload": f"plan_weekly_user_{user_id}"
        },
        "monthly": {
            "title": "⭐ اشتراك شهري - HASAD",
            "description": "الباقة الشهرية: 30 يوم - 100 واجب",
            "stars": PAYMENT_SETTINGS.get("stars_monthly", 350),
            "payload": f"plan_monthly_user_{user_id}"
        },
        "semester": {
            "title": "⭐ اشتراك ترم - HASAD",
            "description": "باقة الترم: 120 يوم - 200 واجب",
            "stars": PAYMENT_SETTINGS.get("stars_semester", 1000),
            "payload": f"plan_semester_user_{user_id}"
        }
    }

    plan = plans.get(plan_id)
    if not plan:
        print(f"❌ Invalid plan_id: {plan_id}")
        return None

    try:
        # ✅ استخدام create_invoice_link
        invoice_link = await context.bot.create_invoice_link(
            title=plan["title"],
            description=plan["description"],
            payload=plan["payload"],
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(plan["title"], plan["stars"])]
        )

        print(f"✅ Invoice link created: {invoice_link}")
        return invoice_link

    except Exception as e:
        print(f"❌ Error creating invoice link: {e}")
        return None


# ==============================================================================
# LATER definitions (L1481 etc.)
# ==============================================================================

async def webapp_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج بيانات الويب أب"""
    uid = update.effective_user.id

    try:
        data_str = update.message.web_app_data.data
        data = json.loads(data_str)
    except Exception as e:
        await update.message.reply_text("❌ حدث خطأ في قراءة البيانات")
        return

    action = data.get("action")

    if action == "create_invoice":
        plan_id = data.get("plan_id", "monthly")
        plan = PLANS.get(plan_id, PLANS["monthly"])

        payload = f"stars_{plan_id}_{uid}_{int(now_timestamp())}"

        await context.bot.send_invoice(
            chat_id=uid,
            title=f"⭐ اشتراك {plan['name']} - HASAD",
            description=f"المدة: {plan['days']} يوم\nالواجبات: {plan['hw']} واجب",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(f"اشتراك {plan['name']}", plan['stars'])],
            start_parameter=f"sub_{plan_id}_{uid}"
        )


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج ما قبل الدفع"""
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الدفع الناجح - تفعيل الاشتراك"""
    uid = update.effective_user.id
    name = update.effective_user.first_name or "مستخدم"

    payment = update.message.successful_payment
    payload = payment.invoice_payload
    stars_amount = payment.total_amount

    # تحديد الخطة من الـ payload
    try:
        parts = payload.split("_")
        plan_id = parts[1] if len(parts) > 1 else "monthly"
    except:
        plan_id = "monthly"

    plan = PLANS.get(plan_id, PLANS["monthly"])
    days = plan["days"]

    # حساب تاريخ الانتهاء
    u = await db_get_user(uid)
    cur_exp = (u or {}).get("expiry_ts", 0) or 0
    if cur_exp < now_timestamp():
        cur_exp = now_timestamp()

    new_exp = cur_exp + days * 86400
    exp_hijri = gregorian_to_hijri(datetime.fromtimestamp(new_exp))

    # تحديث بيانات المستخدم
    await db_set_user(uid, name=name, expiry_ts=new_exp, expiry_hijri=exp_hijri, vip_status=1)

    # إنشاء اشتراك
    await create_user_subscription(uid, plan_id, cur_exp, new_exp)

    # تسجيل العملية
    await db_log(uid, "STARS_PAYMENT", detail=f"Plan: {plan_id}, Stars: {stars_amount}")

    # إرسال رسالة نجاح
    await update.message.reply_text(
        f"🎉 **تم الدفع بنجاح!**\n\n"
        f"📦 الباقة: {plan['name']}\n"
        f"⭐ النجوم: {stars_amount}\n"
        f"📅 الانتهاء: {exp_hijri}\n\n"
        f"🚀 مبروك! يمكنك الآن استخدام البوت",
        parse_mode=ParseMode.HTML
    )


# ==============================================================================
# Shop flow (LATER definitions)
# ==============================================================================

async def open_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فتح متجر الاشتراكات - أزرار Inline"""

    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "⭐ متجر الاشتراكات", "main")

    # أزرار الباقات
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 اسبوعي | 10 ريال | 150 نجمة⭐️", callback_data="shop_plan:weekly"),
        ],
        [
            InlineKeyboardButton("📆 شهري | 25 ريال | 350 نجمة⭐️", callback_data="shop_plan:monthly"),
        ],
        [
            InlineKeyboardButton("🎓 ترم كامل | 60 ريال | 1000 نجمة⭐️", callback_data="shop_plan:semester"),
        ],
    ])

    await update.message.reply_text(
    "⭐️ <b>متجر HASAD</b> ⭐️\n\n"
    "متجر الاشتراكات الرسمي\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "✨ <b>اختر الباقة المناسبة لك</b>\n\n"
    "📦 <b>الباقات المتاحة:</b>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "📅 <b>اسبوعي</b>\n"
    "🕐 المدة: 7 أيام\n"
    "📚 الواجبات: 25 واجب\n"
    "💰 السعر: 10 ريال | 150 نجمة\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "📆 <b>شهري</b> ⭐️ الأكثر طلباً\n"
    "🕐 المدة: 30 يوم\n"
    "📚 الواجبات: 100 واجب\n"
    "💰 السعر: 25 ريال | 350 نجمة\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "🎓 <b>ترم كامل</b> (الأوفر)\n"
    "🕐 المدة: 120 يوم\n"
    "📚 الواجبات: 200 واجب\n"
    "💰 السعر: 60 ريال | 1000 نجمة\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "💳 <b>طرق الدفع المتاحة:</b>\n"
    "⭐ الدفع بالنجوم (فوري وتلقائي)\n"
    "🏦 تحويل بنكي (الراجحي / الأهلي)\n"
    "📱 STC Pay (محفظة إلكترونية)\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "👇 <b>اضغط على الزر أدناه لاختيار الباقة</b>",
    parse_mode=ParseMode.HTML,
    reply_markup=keyboard
)


async def shop_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج اختيار الباقة - عرض طرق الدفع"""

    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    plan_id = query.data.split(":")[1]  # shop_plan:weekly

    # خطط الاشتراك
    plans = {
        "weekly": {
            "name": "📅 اسبوعي", "days": 7, "hw": 25,
            "price": 10, "stars": 150
        },
        "monthly": {
            "name": "📆 شهري", "days": 30, "hw": 100,
            "price": 25, "stars": 350
        },
        "semester": {
            "name": "🎓 ترم كامل", "days": 120, "hw": 200,
            "price": 60, "stars": 1000
        }
    }

    plan = plans.get(plan_id)
    if not plan:
        await query.edit_message_text("❌ الباقة غير موجودة")
        return

    # حفظ الباقة المختارة
    context.user_data['selected_plan'] = plan_id
    context.user_data['plan_info'] = plan

    # أزرار طرق الدفع
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"⭐ النجوم ({plan['stars']} نجمة)", callback_data=f"shop_pay:stars:{plan_id}"),
        ],
        [
            InlineKeyboardButton("🏦 تحويل بنكي", callback_data=f"shop_pay:bank:{plan_id}"),
        ],
        [
            InlineKeyboardButton("📱 STC Pay", callback_data=f"shop_pay:stc:{plan_id}"),
        ],
        [
            InlineKeyboardButton("🔙 رجوع للباقات", callback_data="shop_back"),
        ],
    ])

    await query.edit_message_text(
        f"✅ <b>تم اختيار: {plan['name']}</b>\n\n"
        f"📦 <b>تفاصيل الباقة:</b>\n"
        f"• المدة: {plan['days']} يوم\n"
        f"• الواجبات: {plan['hw']} واجب\n"
        f"• السعر: {plan['price']} ريال\n"
        f"• النجوم: {plan['stars']} ⭐\n\n"
        f"💳 <b>اختر طريقة الدفع:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def shop_pay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج اختيار طريقة الدفع"""

    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    parts = query.data.split(":")  # shop_pay:stars:weekly
    method = parts[1]
    plan_id = parts[2]

    # خطط الاشتراك
    plans = {
        "weekly": {
            "name": "اسبوعي", "days": 7, "hw": 25,
            "price": 10, "stars": 150
        },
        "monthly": {
            "name": "شهري", "days": 30, "hw": 100,
            "price": 25, "stars": 350
        },
        "semester": {
            "name": "ترم كامل", "days": 120, "hw": 200,
            "price": 60, "stars": 1000
        }
    }

    plan = plans.get(plan_id)
    if not plan:
        await query.edit_message_text("❌ الباقة غير موجودة")
        return

    if method == "stars":
        # إرسال فاتورة النجوم
        await send_stars_invoice(query, uid, plan_id, plan, context)

    elif method == "bank":
        # عرض تعليمات التحويل البنكي
        await show_bank_instructions(query, plan)

    elif method == "stc":
        # عرض تعليمات STC Pay
        await show_stc_instructions(query, plan)


async def send_stars_invoice(query, uid, plan_id, plan, context):
    """إرسال فاتورة الدفع بالنجوم"""
    from telegram import LabeledPrice

    # إنشاء payload فريد
    timestamp = int(now_timestamp())
    payload = f"stars_{plan_id}_{uid}_{timestamp}"

    try:
        await context.bot.send_invoice(
            chat_id=uid,
            title=f"⭐ اشتراك {plan['name']} - HASAD",
            description=f"الباقة: {plan['name']}\nالمدة: {plan['days']} يوم\nالواجبات: {plan['hw']} واجب",
            payload=payload,
            provider_token="",  # فارغ للنجوم
            currency="XTR",     # عملة النجوم
            prices=[LabeledPrice(f"اشتراك {plan['name']}", plan['stars'])],
        )

        # تحديث الرسالة

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع للمتجر", callback_data="shop_back")],
        ])

        await query.edit_message_text(
            f"⭐ <b>تم إرسال فاتورة الدفع!</b>\n\n"
            f"📦 <b>الباقة:</b> {plan['name']}\n"
            f"⭐ <b>النجوم:</b> {plan['stars']}\n\n"
            f"📌 <b>اضغط على الفاتورة  لإتمام الدفع</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

        logger.info(f"✅ Stars invoice sent to user {uid} for plan {plan_id}")

    except Exception as e:
        logger.error(f"❌ Error sending invoice: {e}")
        await query.edit_message_text(
            f"❌ <b>حدث خطأ في إرسال الفاتورة</b>\n\n"
            f"يرجى المحاولة مرة أخرى أو التواصل مع الدعم.",
            parse_mode=ParseMode.HTML
        )


async def show_bank_instructions(query, plan):
    """عرض تعليمات التحويل البنكي مع أزرار نسخ بجانب كل معلومة"""

    bank_info = PAYMENT_SETTINGS

    bank_name = bank_info.get('bank_name', 'الراجحي')
    account_name = bank_info.get('bank_account_name', 'HASAD STORE')
    account_number = bank_info.get('bank_account_number', '')
    iban = bank_info.get('bank_iban', '')

    # أزرار نسخ لكل معلومة على حدة
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 رجوع للمتجر", callback_data="shop_back")
        ]
    ])

    await query.edit_message_text(
        f"🏦 <b>تعليمات التحويل البنكي</b>\n\n"
        f"📦 <b>الباقة:</b> {plan['name']}\n"
        f"💰 <b>المبلغ:</b> {plan['price']} ريال\n\n"
        f"📋 <b>معلومات الحساب:</b>\n"
        f"• البنك: <code>{bank_name}</code>\n"
        f"• اسم المستفيد: <code>{account_name}</code>\n"
        f"• رقم الحساب: <code>{account_number}</code> \n"
        f"• الآيبان: <code>{iban}</code> \n\n"
        f"📸 <b>بعد التحويل:</b>\n"
        f"أرسل صورة الإيصال للدعم الفني",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def show_stc_instructions(query, plan):
    """عرض تعليمات STC Pay مع زر نسخ"""

    stc_phone = PAYMENT_SETTINGS.get('stc_phone', '05xxxxxxxx')


    await query.edit_message_text(
        f"📱 <b>تعليمات الدفع عبر STC Pay</b>\n\n"
        f"📦 <b>الباقة:</b> {plan['name']}\n"
        f"💰 <b>المبلغ:</b> {plan['price']} ريال\n\n"
        f"📱 <b>رقم الجوال:</b> <code>{stc_phone}</code> \n\n"
        f"📌 <b>خطوات الدفع:</b>\n"
        f"1. افتح تطبيق STC Pay\n"
        f"2. اختر تحويل\n"
        f"3. أدخل رقم الجوال أعلاه\n"
        f"4. أدخل المبلغ: {plan['price']} ريال\n"
        f"5. أرسل صورة الإيصال للدعم الفني\n\n"
        f"📸 <b>بعد الدفع:</b>\n"
        f"أرسل صورة الإيصال للدعم الفني",
        parse_mode=ParseMode.HTML,
    )


async def shop_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الرجوع لقائمة الباقات"""

    query = update.callback_query
    await query.answer()

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 اسبوعي | 10 ريال | 150 نجمة⭐️", callback_data="shop_plan:weekly"),
        ],
        [
            InlineKeyboardButton("📆 شهري | 25 ريال | 350 نجمة⭐️", callback_data="shop_plan:monthly"),
        ],
        [
            InlineKeyboardButton("🎓 ترم كامل | 60 ريال | 1000 نجمة⭐️", callback_data="shop_plan:semester"),
        ],
    ])

    await query.edit_message_text(
        "⭐️ <b>متجر HASAD</b> ⭐️\n\n"
        "متجر الاشتراكات الرسمي\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✨ <b>اختر الباقة المناسبة لك</b>\n\n"
        "📦 <b>الباقات المتاحة:</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📅 <b>اسبوعي</b>\n"
        "🕐 المدة: 7 أيام\n"
        "📚 الواجبات: 25 واجب\n"
        "💰 السعر: 10 ريال | 140 نجمة\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📆 <b>شهري</b> ⭐️ الأكثر طلباً\n"
        "🕐 المدة: 30 يوم\n"
        "📚 الواجبات: 100 واجب\n"
        "💰 السعر: 25 ريال | 350 نجمة\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎓 <b>ترم كامل</b> (الأوفر)\n"
        "🕐 المدة: 120 يوم\n"
        "📚 الواجبات: 200 واجب\n"
        "💰 السعر: 60 ريال | 850 نجمة\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💳 <b>طرق الدفع المتاحة:</b>\n"
        "⭐ الدفع بالنجوم (فوري وتلقائي)\n"
        "🏦 تحويل بنكي (الراجحي / الأهلي)\n"
        "📱 STC Pay (محفظة إلكترونية)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 <b>اضغط على الزر أدناه لاختيار الباقة</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def handle_pay_stars_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اختيار الدفع بالنجوم من قائمة الدفع"""

    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    plan_id = query.data.split(":")[1]  # pay_stars:weekly

    # خطط الاشتراك
    plans = {
        "weekly": {"name": "اسبوعي", "days": 7, "hw": 25, "price": 10, "stars": 150},
        "monthly": {"name": "شهري", "days": 30, "hw": 100, "price": 25, "stars": 350},
        "semester": {"name": "ترم", "days": 120, "hw": 200, "price": 60, "stars": 1000}
    }

    plan = plans.get(plan_id)
    if not plan:
        await query.edit_message_text("❌ الباقة غير موجودة")
        return

    # إرسال الفاتورة
    from telegram import LabeledPrice

    await context.bot.send_invoice(
        chat_id=uid,
        title=f"⭐ اشتراك {plan['name']}",
        description=f"الباقة: {plan['name']}\nالمدة: {plan['days']} يوم\nالواجبات: {plan['hw']} واجب",
        payload=f"plan_{plan_id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(plan['name'], plan['stars'])],
        start_parameter="hasad_subscription",
        need_name=False,
        need_phone_number=False,
        need_email=False
    )

    # تحديث رسالة الكيبورد
    await query.edit_message_text(
        f"⭐ **تم إرسال فاتورة الدفع**\n\n"
        f"📦 **الباقة:** {plan['name']}\n"
        f"💰 **السعر:** {plan['price']} ريال\n"
        f"⭐ **النجوم:** {plan['stars']} نجمة\n\n"
        f"📌 اضغط على الفاتورة أعلاه لإتمام الدفع",
        parse_mode="Markdown"
    )

    admin_trace("STARS_CALLBACK", f"User {uid} requested stars payment via callback: {plan_id}", uid)
