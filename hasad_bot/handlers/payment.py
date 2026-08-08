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
from hasad_bot.utils import admin_trace


async def _load_payment_config() -> dict:
    """Shared payment-config read (lazy import avoids import cycles)."""
    from hasad_bot.database.payment_settings import get_payment_config
    return await get_payment_config()


# إيموجيات الباقات كما كانت في الأسماء القديمة المثبتة (أسبوعي/شهري/ترم).
_PLAN_EMOJI = {"weekly": "📅", "monthly": "📆", "semester": "🎓"}


def _plan_label(plan_id, name):
    """اسم الباقة مع إيموجي المتجر — يعيد الاسم كما هو إذا كان مسبوقًا بالفعل."""
    prefix = _PLAN_EMOJI.get(plan_id)
    if prefix and name and not str(name).startswith(prefix):
        return f"{prefix} {name}"
    return name


# ==============================================================================
# create_stars_invoice_link (NOT duplicated - kept here for shop workflow)
# ==============================================================================

async def create_stars_invoice_link(plan_id: str, user_id: int, context) -> str:
    """
    إنشاء رابط فاتورة دفع بالنجوم
    """
    from telegram import LabeledPrice

    config_plans = (await _load_payment_config()).get("plans", {}) or {}
    config_plans = {pid: p for pid, p in config_plans.items() if p.get("is_active") == 1}
    weekly = config_plans.get("weekly") or {}
    monthly = config_plans.get("monthly") or {}
    semester = config_plans.get("semester") or {}

    plans = {
        "weekly": {
            "title": "⭐ اشتراك اسبوعي - HASAD",
            "description": f"الباقة الاسبوعية: {weekly.get('days', 7)} أيام - {weekly.get('max_homeworks', 25)} واجب",
            "stars": weekly.get("stars") or 150,
            "payload": f"plan_weekly_user_{user_id}"
        },
        "monthly": {
            "title": "⭐ اشتراك شهري - HASAD",
            "description": f"الباقة الشهرية: {monthly.get('days', 30)} يوم - {monthly.get('max_homeworks', 100)} واجب",
            "stars": monthly.get("stars") or 350,
            "payload": f"plan_monthly_user_{user_id}"
        },
        "semester": {
            "title": "⭐ اشتراك ترم - HASAD",
            "description": f"باقة الترم: {semester.get('days', 120)} يوم - {semester.get('max_homeworks', 200)} واجب",
            "stars": semester.get("stars") or 1000,
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
        config_plans = (await _load_payment_config()).get("plans", {}) or {}
        plan = config_plans.get(plan_id) or config_plans.get("monthly")
        if not plan or plan.get("is_active") != 1:
            await update.message.reply_text("❌ الباقة غير متاحة حالياً")
            return

        payload = f"stars_{plan_id}_{uid}_{int(now_timestamp())}"

        await context.bot.send_invoice(
            chat_id=uid,
            title=f"⭐ اشتراك {plan['name']} - HASAD",
            description=f"المدة: {plan['days']} يوم\nالواجبات: {plan['max_homeworks']} واجب",
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

    config_plans = (await _load_payment_config()).get("plans", {}) or {}
    plan = config_plans.get(plan_id) or config_plans.get("monthly") or {}
    if not plan or plan.get("is_active") != 1:
        await update.message.reply_text("❌ الباقة غير متاحة حالياً")
        return
    days = plan.get("days") or 30

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
        f"📦 الباقة: {plan.get('name', 'شهري')}\n"
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

    config_plans = (await _load_payment_config()).get("plans", {}) or {}
    config_plans = {pid: p for pid, p in config_plans.items() if p.get("is_active") == 1}
    weekly = config_plans.get("weekly") or {}
    monthly = config_plans.get("monthly") or {}
    semester = config_plans.get("semester") or {}

    # أزرار الباقات
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"📅 {weekly.get('name', 'اسبوعي')} | {weekly.get('price', 10)} ريال | {weekly.get('stars', 150)} نجمة⭐️",
                callback_data="shop_plan:weekly",
            ),
        ],
        [
            InlineKeyboardButton(
                f"📆 {monthly.get('name', 'شهري')} | {monthly.get('price', 25)} ريال | {monthly.get('stars', 350)} نجمة⭐️",
                callback_data="shop_plan:monthly",
            ),
        ],
        [
            InlineKeyboardButton(
                f"🎓 {semester.get('name', 'ترم كامل')} | {semester.get('price', 60)} ريال | {semester.get('stars', 1000)} نجمة⭐️",
                callback_data="shop_plan:semester",
            ),
        ],
    ])

    await update.message.reply_text(
    f"⭐️ <b>متجر HASAD</b> ⭐️\n\n"
    "متجر الاشتراكات الرسمي\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "✨ <b>اختر الباقة المناسبة لك</b>\n\n"
    "📦 <b>الباقات المتاحة:</b>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    f"📅 <b>{weekly.get('name', 'اسبوعي')}</b>\n"
    f"🕐 المدة: {weekly.get('days', 7)} أيام\n"
    f"📚 الواجبات: {weekly.get('max_homeworks', 25)} واجب\n"
    f"💰 السعر: {weekly.get('price', 10)} ريال | {weekly.get('stars', 150)} نجمة\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    f"📆 <b>{monthly.get('name', 'شهري')}</b> ⭐️ الأكثر طلباً\n"
    f"🕐 المدة: {monthly.get('days', 30)} يوم\n"
    f"📚 الواجبات: {monthly.get('max_homeworks', 100)} واجب\n"
    f"💰 السعر: {monthly.get('price', 25)} ريال | {monthly.get('stars', 350)} نجمة\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    f"🎓 <b>{semester.get('name', 'ترم كامل')}</b> (الأوفر)\n"
    f"🕐 المدة: {semester.get('days', 120)} يوم\n"
    f"📚 الواجبات: {semester.get('max_homeworks', 200)} واجب\n"
    f"💰 السعر: {semester.get('price', 60)} ريال | {semester.get('stars', 1000)} نجمة\n\n"
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
    config_plans = (await _load_payment_config()).get("plans", {}) or {}
    plan = config_plans.get(plan_id)
    if not plan or plan.get("is_active") != 1:
        await query.edit_message_text("❌ الباقة غير متاحة حالياً")
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
        f"✅ <b>تم اختيار: {_plan_label(plan_id, plan['name'])}</b>\n\n"
        f"📦 <b>تفاصيل الباقة:</b>\n"
        f"• المدة: {plan['days']} يوم\n"
        f"• الواجبات: {plan['max_homeworks']} واجب\n"
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
    config_data = await _load_payment_config()
    config_plans = config_data.get("plans", {}) or {}
    methods = config_data.get("methods", {})

    plan = config_plans.get(plan_id)
    if not plan or plan.get("is_active") != 1:
        await query.edit_message_text("❌ الباقة غير متاحة حالياً")
        return

    if method == "stars":
        # إرسال فاتورة النجوم
        if not methods.get("stars", True):
            await query.edit_message_text("❌ الدفع بالنجوم غير متاح حالياً، جرب طريقة أخرى")
            return
        await send_stars_invoice(query, uid, plan_id, plan, context)

    elif method == "bank":
        # عرض تعليمات التحويل البنكي
        if not methods.get("bank", True):
            await query.edit_message_text("❌ التحويل البنكي غير متاح حالياً، جرب طريقة أخرى")
            return
        await show_bank_instructions(query, plan)

    elif method == "stc":
        # عرض تعليمات STC Pay
        if not methods.get("stc", True):
            await query.edit_message_text("❌ الدفع عبر STC Pay غير متاح حالياً، جرب طريقة أخرى")
            return
        await show_stc_instructions(query, plan)


async def send_stars_invoice(query, uid, plan_id, plan, context):
    """إرسال فاتورة الدفع بالنجوم"""
    from telegram import LabeledPrice

    config_plans = (await _load_payment_config()).get("plans", {}) or {}
    plan = config_plans.get(plan_id) or plan
    if not plan or plan.get("is_active") != 1:
        await query.edit_message_text("❌ الباقة غير متاحة حالياً")
        return

    # إنشاء payload فريد
    timestamp = int(now_timestamp())
    payload = f"stars_{plan_id}_{uid}_{timestamp}"

    try:
        await context.bot.send_invoice(
            chat_id=uid,
            title=f"⭐ اشتراك {_plan_label(plan.get('plan_id'), plan['name'])} - HASAD",
            description=f"الباقة: {_plan_label(plan.get('plan_id'), plan['name'])}\nالمدة: {plan['days']} يوم\nالواجبات: {plan['max_homeworks']} واجب",
            payload=payload,
            provider_token="",  # فارغ للنجوم
            currency="XTR",     # عملة النجوم
            prices=[LabeledPrice(f"اشتراك {_plan_label(plan.get('plan_id'), plan['name'])}", plan['stars'])],
        )

        # تحديث الرسالة

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع للمتجر", callback_data="shop_back")],
        ])

        await query.edit_message_text(
            f"⭐ <b>تم إرسال فاتورة الدفع!</b>\n\n"
            f"📦 <b>الباقة:</b> {_plan_label(plan.get('plan_id'), plan['name'])}\n"
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

    bank_info = (await _load_payment_config()).get("bank", {}) or {}

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
        f"📦 <b>الباقة:</b> {_plan_label(plan.get('plan_id'), plan['name'])}\n"
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

    stc_phone = (await _load_payment_config()).get("stc", {}).get('stc_phone', '05xxxxxxxx')


    await query.edit_message_text(
        f"📱 <b>تعليمات الدفع عبر STC Pay</b>\n\n"
        f"📦 <b>الباقة:</b> {_plan_label(plan.get('plan_id'), plan['name'])}\n"
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

    config_plans = (await _load_payment_config()).get("plans", {}) or {}
    config_plans = {pid: p for pid, p in config_plans.items() if p.get("is_active") == 1}
    weekly = config_plans.get("weekly") or {}
    monthly = config_plans.get("monthly") or {}
    semester = config_plans.get("semester") or {}

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"📅 {weekly.get('name', 'اسبوعي')} | {weekly.get('price', 10)} ريال | {weekly.get('stars', 150)} نجمة⭐️",
                callback_data="shop_plan:weekly",
            ),
        ],
        [
            InlineKeyboardButton(
                f"📆 {monthly.get('name', 'شهري')} | {monthly.get('price', 25)} ريال | {monthly.get('stars', 350)} نجمة⭐️",
                callback_data="shop_plan:monthly",
            ),
        ],
        [
            InlineKeyboardButton(
                f"🎓 {semester.get('name', 'ترم كامل')} | {semester.get('price', 60)} ريال | {semester.get('stars', 1000)} نجمة⭐️",
                callback_data="shop_plan:semester",
            ),
        ],
    ])

    await query.edit_message_text(
        f"⭐️ <b>متجر HASAD</b> ⭐️\n\n"
        "متجر الاشتراكات الرسمي\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✨ <b>اختر الباقة المناسبة لك</b>\n\n"
        "📦 <b>الباقات المتاحة:</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 <b>{weekly.get('name', 'اسبوعي')}</b>\n"
        f"🕐 المدة: {weekly.get('days', 7)} أيام\n"
        f"📚 الواجبات: {weekly.get('max_homeworks', 25)} واجب\n"
        f"💰 السعر: {weekly.get('price', 10)} ريال | {weekly.get('stars', 150)} نجمة\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📆 <b>{monthly.get('name', 'شهري')}</b> ⭐️ الأكثر طلباً\n"
        f"🕐 المدة: {monthly.get('days', 30)} يوم\n"
        f"📚 الواجبات: {monthly.get('max_homeworks', 100)} واجب\n"
        f"💰 السعر: {monthly.get('price', 25)} ريال | {monthly.get('stars', 350)} نجمة\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎓 <b>{semester.get('name', 'ترم كامل')}</b> (الأوفر)\n"
        f"🕐 المدة: {semester.get('days', 120)} يوم\n"
        f"📚 الواجبات: {semester.get('max_homeworks', 200)} واجب\n"
        f"💰 السعر: {semester.get('price', 60)} ريال | {semester.get('stars', 1000)} نجمة\n\n"
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
    config_plans = (await _load_payment_config()).get("plans", {}) or {}
    plan = config_plans.get(plan_id)
    if not plan or plan.get("is_active") != 1:
        await query.edit_message_text("❌ الباقة غير متاحة حالياً")
        return

    # إرسال الفاتورة
    from telegram import LabeledPrice

    await context.bot.send_invoice(
        chat_id=uid,
        title=f"⭐ اشتراك {plan['name']}",
        description=f"الباقة: {plan['name']}\nالمدة: {plan['days']} يوم\nالواجبات: {plan['max_homeworks']} واجب",
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
