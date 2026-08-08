"""
admin_reseller.py - Admin reseller management.

Contains:
* ``admin_reseller_panel``      - reseller management menu
* ``admin_add_reseller``        - promote user to reseller
* ``admin_reseller_credit``     - add credit to reseller
* ``admin_reseller_list``       - list all resellers
* ``admin_reseller_prices``     - change credit prices
* ``admin_reseller_stats_panel`` - reseller statistics overview
"""
from __future__ import annotations

import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from hasad_bot.config import (
    config, MAIN_MENU, ADMIN_PANEL,
    AWAIT_RESELLER_CREDIT_AMOUNT, AWAIT_RESELLER_CREDIT_USER,
    AWAIT_RESELLER_PRICES,
)
from hasad_bot.database import (
    is_admin, is_reseller,
    update_user_last_active, db_get_user,
    get_reseller_credit, get_all_reseller_credit_prices,
)
from hasad_bot.utils import admin_trace, now_hijri, kb_admin, config
from hasad_bot.handlers.constants import (
    BTN_BACK_MAIN, BTN_RESELLER_PANEL,
    ADMIN_BTN_RESELLERS, ADMIN_BTN_ADD_RESELLER,
    ADMIN_BTN_RESELLER_CREDIT, ADMIN_BTN_RESELLER_LIST,
    ADMIN_BTN_RESELLER_PRICES, ADMIN_BTN_RESELLER_STATS,
)


# ==============================================================================
# Navigation escape helper — ي跳出 الحالة إذا المستخدم ضغط زر قديم
# ==============================================================================

_ADMIN_NAV_BUTTONS = {
    BTN_BACK_MAIN, BTN_RESELLER_PANEL,
    ADMIN_BTN_RESELLERS, ADMIN_BTN_ADD_RESELLER,
    ADMIN_BTN_RESELLER_CREDIT, ADMIN_BTN_RESELLER_LIST,
    ADMIN_BTN_RESELLER_PRICES, ADMIN_BTN_RESELLER_STATS,
    "🗑️ حذف موزع", "🚫 حظر عميل الموزع",
    "🗑️ حذف أدمن",
}


async def _check_admin_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إذا النص زر تنقل إداري → امسح الحالة وroute للزر. returns True إذا تم التخطي."""
    text = (update.message.text or "").strip()
    if text not in _ADMIN_NAV_BUTTONS:
        return False

    context.user_data.pop('admin_action', None)
    context.user_data.pop('credit_target', None)

    from hasad_bot.handlers.user import handle_text
    await handle_text(update, context)
    return True


# ==============================================================================
# Admin reseller panel
# ==============================================================================

async def admin_reseller_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin reseller management menu"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return MAIN_MENU

    await update_user_last_active(uid)
    is_owner = (uid == config.admin_id)

    text = """
🏪 <b>إدارة الموزعين</b>

━━━━━━━━━━━━━━━━━━
اختر الإجراء المطلوب:
━━━━━━━━━━━━━━━━━━
"""
    from telegram import ReplyKeyboardMarkup
    from hasad_bot.handlers.constants import (
        ADMIN_BTN_ADD_RESELLER, ADMIN_BTN_RESELLER_CREDIT,
        ADMIN_BTN_RESELLER_LIST, ADMIN_BTN_RESELLER_PRICES,
        ADMIN_BTN_RESELLER_STATS, BTN_BACK_MAIN,
    )

    rows = [
        [ADMIN_BTN_ADD_RESELLER, ADMIN_BTN_RESELLER_CREDIT],
        [ADMIN_BTN_RESELLER_LIST, ADMIN_BTN_RESELLER_PRICES],
        [ADMIN_BTN_RESELLER_STATS],
    ]

    if is_owner:
        rows.append(["🗑️ حذف موزع", "🚫 حظر عميل الموزع"])

    rows.append([BTN_BACK_MAIN])

    keyboard = ReplyKeyboardMarkup(rows, resize_keyboard=True)

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    return ADMIN_PANEL


# ==============================================================================
# Add reseller
# ==============================================================================

async def admin_add_reseller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promote user to reseller - ask for user ID"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return MAIN_MENU

    text = """
➕ <b>ترقية موزع</b>

━━━━━━━━━━━━━━━━━━
أرسل <b>معرف المستخدم</b> (Telegram ID) لترقيته كموزع.
━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(text, parse_mode="HTML")
    context.user_data['admin_action'] = 'add_reseller'
    return AWAIT_RESELLER_CREDIT_USER


async def admin_add_reseller_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user ID input for reseller promotion"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return MAIN_MENU
    if await _check_admin_nav(update, context):
        return

    text = update.message.text.strip()
    try:
        target_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ أرسل معرف المستخدم (رقم صحيح).")
        return AWAIT_RESELLER_CREDIT_USER

    from hasad_bot.admin_ops import add_reseller
    _, message = await add_reseller(
        target_id,
        actor_uid=uid,
        actor_name=update.effective_user.full_name or "telegram",
    )
    await update.message.reply_text(message, parse_mode="HTML")

    return ADMIN_PANEL


# ==============================================================================
# Add credit
# ==============================================================================

async def admin_reseller_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add credit to reseller - ask for user ID"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return MAIN_MENU

    text = """
💰 <b>شحن رصيد موزع</b>

━━━━━━━━━━━━━━━━━━
أرسل <b>معرف الموزع</b> (Telegram ID).
━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(text, parse_mode="HTML")
    context.user_data['admin_action'] = 'reseller_credit_user'
    return AWAIT_RESELLER_CREDIT_USER


async def admin_reseller_credit_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user ID input for various reseller actions"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return MAIN_MENU
    if await _check_admin_nav(update, context):
        return

    action = context.user_data.get('admin_action', '')

    # Route to the correct handler based on action
    if action == 'add_reseller':
        return await admin_add_reseller_input(update, context)
    elif action == 'delete_reseller':
        return await admin_handle_delete_reseller(update, context)
    elif action == 'delete_admin':
        return await admin_handle_delete_admin(update, context)
    elif action == 'ban_reseller_customer':
        return await admin_handle_ban_reseller_customer(update, context)
    elif action == 'reseller_credit_user':
        return await _admin_reseller_credit_user_input(update, context)
    elif action == 'charge_admin_user':
        return await _admin_charge_admin_user_input(update, context)
    else:
        await update.message.reply_text("❌ إجراء غير معروف.")
        return ADMIN_PANEL


async def _admin_reseller_credit_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reseller ID input for credit addition"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return MAIN_MENU
    if await _check_admin_nav(update, context):
        return

    text = update.message.text.strip()
    try:
        target_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ أرسل معرف الموزع (رقم صحيح).")
        return AWAIT_RESELLER_CREDIT_USER

    # Check user is reseller
    if not await is_reseller(target_id):
        await update.message.reply_text("❌ هذا المستخدم ليس موزعاً.")
        return ADMIN_PANEL

    context.user_data['credit_target'] = target_id
    credit = await get_reseller_credit(target_id)
    target_user = await db_get_user(target_id)
    name = target_user.get('real_name') or target_user.get('name') or str(target_id)

    text = f"""
💰 <b>شحن رصيد لـ {name}</b>

━━━━━━━━━━━━━━━━━━
💳 الرصيد الحالي: <b>{credit} credit</b>

أرسل الآن <b>عدد الـ credit</b> الذي تريد إضافته.
━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(text, parse_mode="HTML")
    return AWAIT_RESELLER_CREDIT_AMOUNT


async def admin_reseller_credit_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle credit amount input"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return MAIN_MENU
    if await _check_admin_nav(update, context):
        return

    text = update.message.text.strip()
    try:
        amount = int(text)
    except ValueError:
        await update.message.reply_text("❌ أرسل عدد صحيح من الـ credit.")
        return AWAIT_RESELLER_CREDIT_AMOUNT

    target_id = context.user_data.get('credit_target')
    if not target_id:
        await update.message.reply_text("❌ خطأ في العملية.")
        return ADMIN_PANEL

    actor_name = update.effective_user.full_name or "telegram"
    action = context.user_data.get('admin_action', '')
    if action == 'charge_admin_user':
        from hasad_bot.admin_ops import charge_admin_credit
        _, message = await charge_admin_credit(target_id, amount, actor_uid=uid, actor_name=actor_name)
    else:
        from hasad_bot.admin_ops import add_reseller_credit_op
        _, message = await add_reseller_credit_op(target_id, amount, actor_uid=uid, actor_name=actor_name)
    await update.message.reply_text(message, parse_mode="HTML")

    return ADMIN_PANEL


# ==============================================================================
# List resellers
# ==============================================================================

async def admin_reseller_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all resellers"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return MAIN_MENU

    from hasad_bot.admin_ops import list_resellers
    success, resellers, message = await list_resellers(actor_uid=uid)
    if not success:
        await update.message.reply_text(message, parse_mode="HTML")
        return ADMIN_PANEL

    if not resellers:
        text = """
📋 <b>قائمة الموزعين</b>

━━━━━━━━━━━━━━━━━━
📭 لا يوجد موزعين حالياً.
━━━━━━━━━━━━━━━━━━
"""
    else:
        is_owner = (uid == config.admin_id)
        lines = []
        for i, r in enumerate(resellers, 1):
            display = r["name"] or str(r["uid"])
            lines.append(f"{i}. {display} ({r['uid']}) — 💳 {r['credit']} credit")

        text = f"""
📋 <b>قائمة الموزعين ({len(resellers)})</b>

━━━━━━━━━━━━━━━━━━
{chr(10).join(lines)}
━━━━━━━━━━━━━━━━━━
"""
        if is_owner:
            text += "\n💡 للحذف: أرسل <code>حذف موزع</code> أو استخدم الزر في لوحة الإدارة."

    await update.message.reply_text(text, parse_mode="HTML")
    return ADMIN_PANEL


# ==============================================================================
# Change prices
# ==============================================================================

async def admin_reseller_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change credit prices"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return MAIN_MENU

    prices = await get_all_reseller_credit_prices()

    text = f"""
💰 <b>تغيير أسعار Credit</b>

━━━━━━━━━━━━━━━━━━
الأسعار الحالية:
• أسبوعي: {prices.get('weekly', '?')} credit
• شهري: {prices.get('monthly', '?')} credit
• ترم: {prices.get('semester', '?')} credit
━━━━━━━━━━━━━━━━━━

أرسل السعر الجديد بالصيغة:
<code>أسبوعي:10</code> أو <code>شهري:20</code> أو <code>ترم:40</code>
"""
    await update.message.reply_text(text, parse_mode="HTML")
    return AWAIT_RESELLER_PRICES


async def admin_reseller_prices_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle price input"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return MAIN_MENU
    if await _check_admin_nav(update, context):
        return

    text = update.message.text.strip()

    # Parse input: "أسبوعي:10" or "شهري:20" or "ترم:40"
    plan_map = {
        'أسبوعي': 'weekly',
        'شهري': 'monthly',
        'ترم': 'semester',
    }

    try:
        parts = text.split(':')
        plan_name_ar = parts[0].strip()
        new_price = int(parts[1].strip())
    except (IndexError, ValueError):
        await update.message.reply_text(
            "❌ صيغة خاطئة. أرسل:\n"
            "<code>أسبوعي:10</code> أو <code>شهري:20</code> أو <code>ترم:40</code>",
            parse_mode="HTML"
        )
        return AWAIT_RESELLER_PRICES

    plan_type = plan_map.get(plan_name_ar)
    if not plan_type:
        await update.message.reply_text("❌ اسم الخطة غير صحيح. استخدم: أسبوعي، شهري، ترم")
        return AWAIT_RESELLER_PRICES

    if new_price <= 0:
        await update.message.reply_text("❌ السعر يجب أن يكون أكبر من 0.")
        return AWAIT_RESELLER_PRICES

    from hasad_bot.admin_ops import set_reseller_prices_op
    _, message = await set_reseller_prices_op(
        {plan_type: new_price},
        actor_uid=uid,
        actor_name=update.effective_user.full_name or "telegram",
    )
    await update.message.reply_text(message, parse_mode="HTML")

    return ADMIN_PANEL


# ==============================================================================
# Stats overview
# ==============================================================================

async def admin_reseller_stats_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show reseller statistics overview"""
    uid = update.effective_user.id
    if not await is_admin(uid):
        return MAIN_MENU

    from hasad_bot.admin_ops import reseller_stats_op
    success, stats, message = await reseller_stats_op(actor_uid=uid)
    if not success:
        await update.message.reply_text(message, parse_mode="HTML")
        return ADMIN_PANEL

    total = stats["total"]
    total_credit = stats["total_credit"]
    total_keys = stats["total_keys"]
    total_used = stats["total_used"]
    total_customers = stats["total_customers"]

    text = f"""
📊 <b>إحصائيات الموزعين</b>

━━━━━━━━━━━━━━━━━━
🏪 إجمالي الموزعين: <b>{total}</b>
👥 إجمالي الزبائن: <b>{total_customers}</b>
🔑 مفاتيح مولّدة: <b>{total_keys}</b>
🔑 مفاتيح مستخدمة: <b>{total_used}</b>
💳 إجمالي الرصيد: <b>{total_credit} credit</b>
━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(text, parse_mode="HTML")
    return ADMIN_PANEL


# ==============================================================================
# Owner-only: Delete reseller
# ==============================================================================

async def admin_delete_reseller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a reseller (owner only) - ask for user ID"""
    uid = update.effective_user.id
    if uid != config.admin_id:
        await update.message.reply_text("❌ هذا الإجراء للمالك فقط.")
        return ADMIN_PANEL

    text = """
🗑️ <b>حذف موزع</b>

━━━━━━━━━━━━━━━━━━
أرسل <b>معرف الموزع</b> (Telegram ID) لحذفه.
━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(text, parse_mode="HTML")
    context.user_data['admin_action'] = 'delete_reseller'
    return AWAIT_RESELLER_CREDIT_USER


# ==============================================================================
# Owner-only: Ban/Stop subscription for reseller's customer
# ==============================================================================

async def admin_ban_reseller_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban or stop subscription for a reseller's customer (owner only)"""
    uid = update.effective_user.id
    if uid != config.admin_id:
        await update.message.reply_text("❌ هذا الإجراء للمالك فقط.")
        return ADMIN_PANEL

    text = """
🚫 <b>حظر / إيقاف اشتراك عميل</b>

━━━━━━━━━━━━━━━━━━
أرسل <b>معرف العميل</b> (Telegram ID).
━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(text, parse_mode="HTML")
    context.user_data['admin_action'] = 'ban_reseller_customer'
    return AWAIT_RESELLER_CREDIT_USER


# ==============================================================================
# Handle delete actions
# ==============================================================================

async def admin_handle_delete_reseller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle delete reseller action"""
    uid = update.effective_user.id
    if uid != config.admin_id:
        await update.message.reply_text("❌ هذا الإجراء للمالك فقط.")
        return ADMIN_PANEL
    if await _check_admin_nav(update, context):
        return

    text = update.message.text.strip()
    try:
        target_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ أرسل معرف المستخدم (رقم صحيح).")
        return ADMIN_PANEL

    from hasad_bot.admin_ops import delete_reseller_op
    _, message = await delete_reseller_op(
        target_id,
        actor_uid=uid,
        actor_name=update.effective_user.full_name or "telegram",
    )
    await update.message.reply_text(message, parse_mode="HTML")

    return ADMIN_PANEL


# ==============================================================================
# Owner-only: Delete admin
# ==============================================================================

async def admin_delete_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete an admin (owner only) - ask for user ID"""
    uid = update.effective_user.id
    if uid != config.admin_id:
        await update.message.reply_text("❌ هذا الإجراء للمالك فقط.")
        return ADMIN_PANEL

    text = """
🗑️ <b>حذف أدمن</b>

━━━━━━━━━━━━━━━━━━
أرسل <b>معرف الأدمن</b> (Telegram ID) لحذفه.
━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(text, parse_mode="HTML")
    context.user_data['admin_action'] = 'delete_admin'
    return AWAIT_RESELLER_CREDIT_USER


async def admin_handle_delete_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle delete admin action"""
    uid = update.effective_user.id
    if uid != config.admin_id:
        await update.message.reply_text("❌ هذا الإجراء للمالك فقط.")
        return ADMIN_PANEL
    if await _check_admin_nav(update, context):
        return

    text = update.message.text.strip()
    try:
        target_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ أرسل معرف المستخدم (رقم صحيح).")
        return ADMIN_PANEL

    from hasad_bot.admin_ops import delete_admin
    _, message = await delete_admin(
        target_id,
        actor_uid=uid,
        actor_name=update.effective_user.full_name or "telegram",
    )
    await update.message.reply_text(message)

    return ADMIN_PANEL


async def admin_handle_ban_reseller_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ban/stop subscription for reseller's customer"""
    uid = update.effective_user.id
    if uid != config.admin_id:
        await update.message.reply_text("❌ هذا الإجراء للمالك فقط.")
        return ADMIN_PANEL
    if await _check_admin_nav(update, context):
        return

    text = update.message.text.strip()
    try:
        target_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ أرسل معرف المستخدم (رقم صحيح).")
        return ADMIN_PANEL

    target_user = await db_get_user(target_id)
    if not target_user:
        await update.message.reply_text("❌ المستخدم غير موجود.")
        return ADMIN_PANEL

    reseller_id = target_user.get('referred_by_reseller')
    if not reseller_id:
        await update.message.reply_text("❌ هذا العميل ليس مرتبطاً بأي موزع.")
        return ADMIN_PANEL

    # Get reseller name
    reseller_user = await db_get_user(reseller_id)
    reseller_name = reseller_user.get('real_name') or reseller_user.get('name') or str(reseller_id) if reseller_user else str(reseller_id)
    customer_name = target_user.get('real_name') or target_user.get('name') or str(target_id)

    # Show options: ban or stop subscription
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 حظر المستخدم", callback_data=f"res_ban:ban:{target_id}")],
        [InlineKeyboardButton("⏹️ إيقاف الاشتراك", callback_data=f"res_ban:stop:{target_id}")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="res_ban:cancel:0")],
    ])

    await update.message.reply_text(
        f"🚫 <b>ilihjam / iqaf اشتراك العميل</b>\n\n"
        f"👤 العميل: {customer_name} ({target_id})\n"
        f"🏪 الموزع: {reseller_name}\n\n"
        f"اختر الإجراء:",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    return ADMIN_PANEL


async def admin_handle_ban_reseller_customer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ban/stop subscription callback"""
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if uid != config.admin_id:
        await q.edit_message_text("❌ هذا الإجراء للمالك فقط.")
        return

    data = q.data
    parts = data.split(':')
    if len(parts) != 3:
        return

    _, action, target_id_str = parts

    if action == 'cancel':
        await q.edit_message_text("❌ تم الإلغاء.")
        return

    try:
        target_id = int(target_id_str)
    except ValueError:
        await q.edit_message_text("❌ خطأ في معرف المستخدم.")
        return

    from hasad_bot.admin_ops import ban_reseller_customer_op
    _, message = await ban_reseller_customer_op(
        target_id,
        action,
        actor_uid=uid,
        actor_name=q.from_user.full_name or "telegram",
    )
    await q.edit_message_text(message)


# ==============================================================================
# Owner-only: List admins
# ==============================================================================

async def admin_list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all admins (owner only)"""
    uid = update.effective_user.id
    if uid != config.admin_id:
        await update.message.reply_text("❌ هذا الإجراء للمالك فقط.")
        return ADMIN_PANEL

    from hasad_bot.admin_ops import list_admins
    success, admins, message = await list_admins(actor_uid=uid)
    if not success:
        await update.message.reply_text(message, parse_mode="HTML")
        return ADMIN_PANEL

    if not admins:
        text = """
📋 <b>قائمة الأدمنز</b>

━━━━━━━━━━━━━━━━━━
📭 لا يوجد أدمنز حالياً.
━━━━━━━━━━━━━━━━━━
"""
    else:
        lines = []
        for i, r in enumerate(admins, 1):
            display = r["name"] or r["tg_username"] or str(r["uid"])
            lines.append(f"{i}. {display} ({r['uid']}) — 💳 {r['credit']} credit")

        text = f"""
📋 <b>قائمة الأدمنز ({len(admins)})</b>

━━━━━━━━━━━━━━━━━━
{chr(10).join(lines)}
━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(text, parse_mode="HTML")
    return ADMIN_PANEL


# ==============================================================================
# Owner-only: Charge admin credit
# ==============================================================================

async def admin_charge_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Charge credit to admin — ask for admin ID (owner only)"""
    uid = update.effective_user.id
    if uid != config.admin_id:
        await update.message.reply_text("❌ هذا الإجراء للمالك فقط.")
        return ADMIN_PANEL

    text = """
💰 <b>شحن رصيد أدمن</b>

━━━━━━━━━━━━━━━━━━
أرسل <b>معرف الأدمن</b> (Telegram ID).
━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(text, parse_mode="HTML")
    context.user_data['admin_action'] = 'charge_admin_user'
    return AWAIT_RESELLER_CREDIT_USER


async def _admin_charge_admin_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin ID input for credit charging (owner only)"""
    uid = update.effective_user.id
    if uid != config.admin_id:
        await update.message.reply_text("❌ هذا الإجراء للمالك فقط.")
        return ADMIN_PANEL
    if await _check_admin_nav(update, context):
        return

    text = update.message.text.strip()
    try:
        target_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ أرسل معرف المستخدم (رقم صحيح).")
        return AWAIT_RESELLER_CREDIT_USER

    user = await db_get_user(target_id)
    if not user:
        await update.message.reply_text("❌ المستخدم غير موجود.")
        return ADMIN_PANEL

    if not (user.get('is_admin', 0) >= 1):
        await update.message.reply_text("❌ هذا المستخدم ليس أدمن.")
        return ADMIN_PANEL

    context.user_data['credit_target'] = target_id
    credit = user.get('reseller_credit', 0)
    name = user.get('real_name') or user.get('name') or str(target_id)

    text = f"""
💰 <b>شحن رصيد لـ {name}</b>

━━━━━━━━━━━━━━━━━━
💳 الرصيد الحالي: <b>{credit} credit</b>

أرسل الآن <b>عدد الـ credit</b> الذي تريد إضافته.
━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(text, parse_mode="HTML")
    return AWAIT_RESELLER_CREDIT_AMOUNT
