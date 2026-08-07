"""
reseller.py - Reseller panel and actions.

Contains:
* ``reseller_panel``          - main reseller menu
* ``reseller_customers``      - list customers
* ``reseller_activate``       - activate subscription for customer
* ``reseller_stats``          - reseller statistics
* ``reseller_link``           - show referral link
* ``reseller_customer_detail`` - customer detail + activate button
"""
from __future__ import annotations

import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from hasad_bot.config import (
    config, MAIN_MENU, AWAIT_RESELLER_ACTIVATE_USER,
)
from hasad_bot.database import (
    is_bot_frozen, is_admin, is_reseller,
    update_user_last_active, db_get_user, db_log,
    get_reseller_credit, get_reseller_customers, get_reseller_stats,
    get_all_reseller_credit_prices, get_plan_by_id,
    generate_reseller_key, activate_reseller_key,
    get_transaction_log,
)
from hasad_bot.utils import admin_trace, now_hijri, kb_main
from hasad_bot.logger import log_button_click
from hasad_bot.handlers.constants import (
    BTN_RESELLER_CUSTOMERS, BTN_RESELLER_ACTIVATE,
    BTN_RESELLER_STATS, BTN_RESELLER_LINK,
    BTN_RESELLER_TX_LOG,
    BTN_BACK_MAIN,
)


# ==============================================================================
# Reseller panel
# ==============================================================================

async def reseller_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main reseller menu"""
    uid = update.effective_user.id
    await update_user_last_active(uid)
    await log_button_click(uid, "🔑 لوحة الموزع", "main")

    from hasad_bot.database import is_reseller, get_reseller_credit, is_admin

    if not await is_reseller(uid) and not await is_admin(uid):
        await update.message.reply_text("❌ هذا القسم للموزعين فقط.")
        return MAIN_MENU

    credit = await get_reseller_credit(uid)
    prices = await get_all_reseller_credit_prices()

    text = f"""
🔑 <b>لوحة الموزع</b>

━━━━━━━━━━━━━━━━━━
💳 رصيدك الحالي: <b>{credit} credit</b>

📦 أسعار التفعيل:
• أسبوعي: {prices.get('weekly', '?')} credit
• شهري: {prices.get('monthly', '?')} credit
• ترم: {prices.get('semester', '?')} credit
━━━━━━━━━━━━━━━━━━
"""
    from telegram import ReplyKeyboardMarkup
    keyboard = ReplyKeyboardMarkup([
        [BTN_RESELLER_CUSTOMERS, BTN_RESELLER_ACTIVATE],
        [BTN_RESELLER_STATS, BTN_RESELLER_LINK],
        [BTN_RESELLER_TX_LOG],
        [BTN_BACK_MAIN],
    ], resize_keyboard=True)

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    return MAIN_MENU


# ==============================================================================
# Customers list
# ==============================================================================

async def reseller_customers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show reseller's customers"""
    uid = update.effective_user.id
    await update_user_last_active(uid)

    from hasad_bot.database import is_reseller, get_reseller_customers

    if not await is_reseller(uid):
        await update.message.reply_text("❌ هذا القسم للموزعين فقط.")
        return MAIN_MENU

    customers = await get_reseller_customers(uid)

    if not customers:
        text = """
👥 <b>زبائني</b>

━━━━━━━━━━━━━━━━━━
📭 لا يوجد زبائن بعد.

شارك رابط الدعوة الخاص بك لجلب الزبائن!
━━━━━━━━━━━━━━━━━━
"""
    else:
        now = time.time()
        plan_names = {'weekly': 'أسبوعي', 'monthly': 'شهري', 'semester': 'ترم'}
        lines = []
        for i, c in enumerate(customers[:20], 1):
            c_id, name, real_name, tg_username, created_at, expiry_ts, free_attempts, plan_id, end_date, max_hw, hw_used = c
            display = real_name or name or str(c_id)

            if plan_id and end_date and end_date > now:
                days_left = int((end_date - now) / 86400)
                plan_display = plan_names.get(plan_id, plan_id)
                remaining_hw = (max_hw or 0) - (hw_used or 0)
                lines.append(f"{i}. ✅ <b>{display}</b> — {plan_display} ({days_left} يوم) | {remaining_hw} واجب")
            else:
                lines.append(f"{i}. ❌ <b>{display}</b> — بدون اشتراك")

        text = f"""
👥 <b>زبائني ({len(customers)} عميل)</b>

━━━━━━━━━━━━━━━━━━
{chr(10).join(lines)}
━━━━━━━━━━━━━━━━━━
"""
        if len(customers) > 20:
            text += f"\n<i>عرض أول 20 من {len(customers)}</i>"

    await update.message.reply_text(text, parse_mode="HTML")
    return MAIN_MENU


# ==============================================================================
# Activate subscription for customer (button-based flow)
# ==============================================================================

async def reseller_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show customer buttons for activation"""
    uid = update.effective_user.id
    await update_user_last_active(uid)

    from hasad_bot.database import is_reseller, get_reseller_credit, get_all_reseller_credit_prices, get_reseller_customers

    if not await is_reseller(uid):
        await update.message.reply_text("❌ هذا القسم للموزعين فقط.")
        return MAIN_MENU

    credit = await get_reseller_credit(uid)
    customers = await get_reseller_customers(uid)

    if not customers:
        text = """
💰 <b>تفعيل اشتراك لعميل</b>

━━━━━━━━━━━━━━━━━━
📭 لا يوجد زبائن بعد.

شارك رابط الدعوة الخاص بك لجلب الزبائن!
━━━━━━━━━━━━━━━━━━
"""
        await update.message.reply_text(text, parse_mode="HTML")
        return MAIN_MENU

    prices = await get_all_reseller_credit_prices()
    now = time.time()
    plan_names = {'weekly': 'أسبوعي', 'monthly': 'شهري', 'semester': 'ترم'}

    text = f"""
💰 <b>اختر العميل للتفعيل</b>

━━━━━━━━━━━━━━━━━━
💳 رصيدك: <b>{credit} credit</b>
👥 الزبائن: <b>{len(customers)}</b>
━━━━━━━━━━━━━━━━━━
"""

    buttons = []
    for c in customers[:20]:
        c_id, name, real_name, tg_username, created_at, expiry_ts, free_attempts, plan_id, end_date, max_hw, hw_used = c
        display = real_name or name or str(c_id)

        if plan_id and end_date and end_date > now:
            days_left = int((end_date - now) / 86400)
            plan_display = plan_names.get(plan_id, plan_id)
            remaining_hw = (max_hw or 0) - (hw_used or 0)
            label = f"✅ {display} — {plan_display} ({days_left} يوم) | {remaining_hw} واجب"
        else:
            label = f"❌ {display} — بدون اشتراك"

        buttons.append([InlineKeyboardButton(label, callback_data=f"res_sel_cust:{c_id}")])

    buttons.append([InlineKeyboardButton("❌ إلغاء", callback_data="res_activate:cancel:0")])

    await update.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return MAIN_MENU


async def reseller_select_customer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle customer selection - show plan options"""
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    from hasad_bot.database import (
        is_reseller, db_get_user, get_reseller_credit,
        get_all_reseller_credit_prices,
    )

    if not await is_reseller(uid):
        await q.edit_message_text("❌ غير مصرح لك.")
        return

    data = q.data
    parts = data.split(':')
    if len(parts) != 2:
        return

    try:
        customer_id = int(parts[1])
    except ValueError:
        return

    customer = await db_get_user(customer_id)
    if not customer:
        await q.edit_message_text("❌ المستخدم غير موجود.")
        return

    # Security: only allow activation for YOUR customers
    customer_reseller = customer.get('referred_by_reseller')
    if customer_reseller != uid:
        await q.edit_message_text(
            "❌ هذا العميل ليس من زبائنك!"
        )
        return

    credit = await get_reseller_credit(uid)
    prices = await get_all_reseller_credit_prices()
    customer_name = customer.get('real_name') or customer.get('name') or str(customer_id)

    # Get current subscription info
    now = time.time()
    expiry_ts = customer.get('expiry_ts', 0) or 0
    plan_names = {'weekly': 'أسبوعي', 'monthly': 'شهري', 'semester': 'ترم'}

    if expiry_ts and expiry_ts > now:
        days_left = int((expiry_ts - now) / 86400)
        expiry_display = f"✅ اشتراك نشط — {days_left} يوم متبقي"
    else:
        expiry_display = "❌ بدون اشتراك"

    buttons = [
        [InlineKeyboardButton(f"📦 أسبوعي — {prices.get('weekly', '?')} cr", callback_data=f"res_activate:weekly:{customer_id}")],
        [InlineKeyboardButton(f"📦 شهري — {prices.get('monthly', '?')} cr", callback_data=f"res_activate:monthly:{customer_id}")],
        [InlineKeyboardButton(f"📦 ترم — {prices.get('semester', '?')} cr", callback_data=f"res_activate:semester:{customer_id}")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="res_activate:cancel:0")],
    ]

    await q.edit_message_text(
        f"💰 <b>تفعيل اشتراك لـ {customer_name}</b>\n\n"
        f"💳 رصيدك: <b>{credit} credit</b>\n"
        f"📦 الحالة: {expiry_display}\n\n"
        f"اختر الخطة:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ==============================================================================
# Reseller stats
# ==============================================================================

async def reseller_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show reseller statistics"""
    uid = update.effective_user.id
    await update_user_last_active(uid)

    from hasad_bot.database import is_reseller, get_reseller_credit, get_reseller_stats

    if not await is_reseller(uid):
        await update.message.reply_text("❌ هذا القسم للموزعين فقط.")
        return MAIN_MENU

    credit = await get_reseller_credit(uid)
    stats = await get_reseller_stats(uid)

    text = f"""
📊 <b>إحصائياتي كموزع</b>

━━━━━━━━━━━━━━━━━━
💳 الرصيد الحالي: <b>{credit} credit</b>
👥 إجمالي الزبائن: <b>{stats['total_customers']}</b>
✅ زبائن باشتراك نشط: <b>{stats['active_customers']}</b>
💳 الرصيد المستهلك: <b>{stats['credit_spent']} credit</b>
━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(text, parse_mode="HTML")
    return MAIN_MENU


# ==============================================================================
# Reseller referral link
# ==============================================================================

async def reseller_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show reseller's referral link"""
    uid = update.effective_user.id
    await update_user_last_active(uid)

    from hasad_bot.database import is_reseller

    if not await is_reseller(uid):
        await update.message.reply_text("❌ هذا القسم للموزعين فقط.")
        return MAIN_MENU

    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start=res_{uid}"

    text = f"""
🔗 <b>رابط الدعوة الخاص بك</b>

━━━━━━━━━━━━━━━━━━
{ref_link}
━━━━━━━━━━━━━━━━━━

📋 شارك هذا الرابط مع أي شخص.
عند تسجيله عبر رابطك، يصبح <b>عميلك</b> تلقائياً.

💡 يمكنك تفعيل الاشتراك له مباشرة من قسم "💰 تفعيل اشتراك".
"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📱 مشاركة", url=f"https://t.me/share/url?url={ref_link}"),
            InlineKeyboardButton(
                text="📋 نسخ الرابط",
                copy_text=CopyTextButton(text=ref_link)
            )
        ]
    ])

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True)
    return MAIN_MENU


# ==============================================================================
# Callback handler for activation confirmation
# ==============================================================================

async def reseller_activate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle activation plan selection callback"""
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    from hasad_bot.database import (
        is_reseller, db_get_user, get_reseller_credit,
        get_all_reseller_credit_prices, activate_reseller_key,
        generate_reseller_key, db_activate_key,
    )
    from hasad_bot.utils import kb_main

    data = q.data
    # Format: res_activate:plan:customer_id
    parts = data.split(':')
    if len(parts) != 3:
        return

    _, plan_type, customer_id_str = parts

    if plan_type == 'cancel':
        await q.edit_message_text("❌ تم الإلغاء.")
        return

    if not await is_reseller(uid):
        await q.edit_message_text("❌ غير مصرح لك.")
        return

    try:
        customer_id = int(customer_id_str)
    except ValueError:
        await q.edit_message_text("❌ خطأ في معرف المستخدم.")
        return

    # Get plan and prices
    plan = await get_plan_by_id(plan_type)
    prices = await get_all_reseller_credit_prices()
    credit_cost = prices.get(plan_type, 0)

    if not plan:
        await q.edit_message_text("❌ خطة غير موجودة.")
        return

    # Check credit
    credit = await get_reseller_credit(uid)
    if credit < credit_cost:
        await q.edit_message_text(
            f"❌ رصيدك غير كافٍ!\n\n"
            f"💳 لديك: {credit} credit\n"
            f"💰 تحتاج: {credit_cost} credit"
        )
        return

    # Check customer exists
    customer = await db_get_user(customer_id)
    if not customer:
        await q.edit_message_text("❌ المستخدم غير موجود.")
        return

    # Security: only allow activation for YOUR customers
    customer_reseller = customer.get('referred_by_reseller')
    if customer_reseller != uid:
        await q.edit_message_text(
            "❌ هذا العميل ليس من زبائنك!\n\n"
            "يمكنك تفعيل الاشتراك فقط للعملاء الذين جاؤوا عبر رابط الدعوة الخاص بك."
        )
        return

    customer_name = customer.get('real_name') or customer.get('name') or str(customer_id)

    # Deduct credit and create subscription
    from hasad_bot.database.pool import db_pool
    import time as _time

    conn = await db_pool.get_connection()

    # Deduct credit
    from hasad_bot.database.attempts import deduct_reseller_credit
    ok = await deduct_reseller_credit(uid, credit_cost, details=f"Activated {plan_type} for {customer_id}")
    if not ok:
        await q.edit_message_text("❌ فشل خصم الرصيد.")
        return

    # Create subscription for customer
    now = _time.time()
    new_exp = now + plan['days'] * 86400

    try:
        # Deactivate old subscriptions
        await conn.execute(
            "UPDATE user_subscriptions SET is_active = 0 WHERE user_id = ? AND is_active = 1",
            (customer_id,)
        )

        # Insert new subscription
        await conn.execute(
            """INSERT INTO user_subscriptions
               (user_id, plan_id, start_date, end_date, max_homeworks, homeworks_used, is_active)
               VALUES (?, ?, ?, ?, ?, 0, 1)""",
            (customer_id, plan_type, now, new_exp, plan['max_homeworks'])
        )

        # Update user expiry
        from hasad_bot.utils import gregorian_to_hijri
        from datetime import datetime
        exp_h = gregorian_to_hijri(datetime.fromtimestamp(new_exp))
        await conn.execute(
            "UPDATE users SET expiry_ts = ?, expiry_hijri = ?, vip_status = 1 WHERE telegram_id = ?",
            (new_exp, exp_h, customer_id)
        )

        await conn.commit()

        new_credit = credit - credit_cost
        await q.edit_message_text(
            f"✅ <b>تم التفعيل بنجاح!</b>\n\n"
            f"👤 العميل: {customer_name}\n"
            f"📦 الخطة: {plan['name']}\n"
            f"📅 المدة: {plan['days']} يوم\n"
            f"💳 تم خصم: {credit_cost} credit\n"
            f"💰 متبقي: {new_credit} credit",
            parse_mode="HTML"
        )

        # Notify customer
        try:
            await context.bot.send_message(
                chat_id=customer_id,
                text=f"🎉 <b>تم تفعيل اشتراكك!</b>\n\n"
                     f"📦 الخطة: {plan['name']}\n"
                     f"📅 المدة: {plan['days']} يوم\n"
                     f"📚 واجباتك: {plan['max_homeworks']} واجب\n\n"
                     f"استخدم /start للبدء!",
                parse_mode="HTML"
            )
        except Exception:
            pass  # Customer may have blocked the bot

    except Exception as e:
        await conn.rollback()
        admin_trace("RESELLER_ACTIVATE_ERR", f"Failed: {e}", uid)
        await q.edit_message_text(f"❌ خطأ في التفعيل: {str(e)[:100]}")


# ==============================================================================
# Transaction log
# ==============================================================================

async def reseller_tx_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show reseller's transaction history"""
    uid = update.effective_user.id
    await update_user_last_active(uid)

    if not await is_reseller(uid):
        await update.message.reply_text("❌ هذا القسم للموزعين فقط.")
        return MAIN_MENU

    txs = await get_transaction_log(uid, limit=20)

    if not txs:
        text = """
📒 <b>سجل المعاملات</b>

━━━━━━━━━━━━━━━━━━
📭 لا توجد معاملات بعد.
━━━━━━━━━━━━━━━━━━
"""
    else:
        lines = []
        for tx in txs:
            tx_id, from_id, to_id, amount, tx_type, notes, created_at, from_name, to_name = tx
            date_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(created_at))

            # Determine display based on tx_type
            if tx_type == 'credit_added':
                icon = "📥"
                label = "شحن رصيد"
                detail = notes or ""
                sign = f"+{amount}"
            elif tx_type == 'key_activated':
                icon = "📤"
                label = "تفعيل اشتراك"
                detail = notes or ""
                sign = f"-{amount}"
            elif tx_type == 'credit_transfer':
                if from_id == uid:
                    icon = "📤"
                    label = "إرسال رصيد"
                    detail = f"إلى {to_name}"
                    sign = f"-{amount}"
                else:
                    icon = "📥"
                    label = "استلام رصيد"
                    detail = f"من {from_name}"
                    sign = f"+{amount}"
            else:
                if from_id == uid:
                    icon = "📤"
                    label = "إرسال"
                    detail = f"إلى {to_name}"
                    sign = f"-{amount}"
                else:
                    icon = "📥"
                    label = "استلام"
                    detail = f"من {from_name}"
                    sign = f"+{amount}"

            detail_str = f" — {detail}" if detail else ""
            lines.append(f"{icon} {date_str} | {label}{detail_str} | {sign} cr")

        text = f"""
📒 <b>سجل المعاملات ({len(txs)})</b>

━━━━━━━━━━━━━━━━━━
{chr(10).join(lines)}
━━━━━━━━━━━━━━━━━━
"""

    await update.message.reply_text(text, parse_mode="HTML")
    return MAIN_MENU
