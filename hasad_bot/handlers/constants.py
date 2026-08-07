"""
constants.py - shared constants for handler modules.

This module holds ConversationHandler state constants, payment configuration
dictionaries, and the list of menu button labels that are routed by
``handle_text``.

Handlers depend on this module (no other handler module should be imported
from here).
"""
from __future__ import annotations

# ConversationHandler state constants - re-exported from hasad_bot.config
# so handlers can import them from a single place.
from hasad_bot.config import (
    MAIN_MENU,
    ADMIN_PANEL,
    AWAIT_LOGIN_USERNAME,
    AWAIT_LOGIN_PASSWORD,
    AWAIT_RENEW_USER,
    AWAIT_RENEW_DAYS,
    AWAIT_REVOKE_USER,
    AWAIT_GENKEY_COUNT,
    AWAIT_ADD_ADMIN,
    AWAIT_SUPPORT_MSG,
    AWAIT_ADMIN_REPLY,
    AWAIT_BROADCAST_MSG,
    AWAIT_CUSTOM_REASON,
    AWAIT_CUSTOM_DAYS,
    AWAIT_BROADCAST_TARGET,
    AWAIT_ADD_HW_COUNT,
    AWAIT_ADD_HW_CONFIRM,
    AWAIT_ADD_HW_CHOICE,
    AWAIT_ADD_HW_ID,
    AWAIT_BROADCAST_CONFIRM,
    AWAIT_RESELLER_CREDIT_AMOUNT,
    AWAIT_RESELLER_CREDIT_USER,
    AWAIT_RESELLER_ACTIVATE_USER,
    AWAIT_RESELLER_PRICES,
    AWAIT_ADMIN_PASSWORD,
    AWAIT_ADMIN_PANEL_USER_ID,
)

# Payment configuration (the LATER definition from bot_handlers.py at L1166).
PAYMENT_SETTINGS = {
    "bank_name": "الراجحي",
    "bank_account_name": "HASAD STORE",
    "bank_account_number": "SA1234567890123456789",
    "bank_iban": "SA1234567890123456789",
    "stc_phone": "05xxxxxxxx",
    "stars_weekly": 150,
    "stars_monthly": 350,
    "stars_semester": 1000,
}

# Subscription plans used by the shop flow.
PLANS = {
    "weekly": {"name": "اسبوعي", "days": 7, "hw": 25, "price": 10, "stars": 150},
    "monthly": {"name": "شهري", "days": 30, "hw": 100, "price": 25, "stars": 350},
    "semester": {"name": "ترم كامل", "days": 120, "hw": 200, "price": 60, "stars": 1000},
}

# Menu button labels that ``handle_text`` routes. Centralised here so the
# router and any unit tests share a single source of truth.
BTN_SOLVE_HOMEWORK = "🤖 حل الواجبات"
BTN_SOLVE_EXAM = "🧪 حل الاختبارات"
BTN_SHARE_AND_EARN = "🎁 شارك واربح"
BTN_MY_ACCOUNT = "👤 حسابي"
BTN_LOGIN = "🔗 ربط المنصة"
BTN_SHOP = "⭐ المتجر"
BTN_SUPPORT = "🆘 الدعم الفني"
BTN_ADMIN_PANEL = "👑 لوحة الإدارة"
BTN_BACK_MAIN = "🔙 الرئيسية"
BTN_END_SUPPORT = "🔙 إنهاء المحادثة"
BTN_CANCEL = "❌ إلغاء"
BTN_ACTIVATE_KEY = "🔑 تفعيل اشتراك"

# Reseller menu button labels.
BTN_RESELLER_PANEL = "🔑 لوحة الموزع"
BTN_RESELLER_CUSTOMERS = "👥 زبائني"
BTN_RESELLER_ACTIVATE = "💰 تفعيل اشتراك"
BTN_RESELLER_STATS = "📊 إحصائياتي"
BTN_RESELLER_LINK = "🔗 رابط الدعوة"

# Admin reseller management buttons.
ADMIN_BTN_RESELLERS = "🏪 إدارة الموزعين"
ADMIN_BTN_ADD_RESELLER = "➕ ترقية موزع"
ADMIN_BTN_RESELLER_CREDIT = "💰 شحن رصيد موزع"
ADMIN_BTN_RESELLER_LIST = "📋 قائمة الموزعين"
ADMIN_BTN_RESELLER_PRICES = "💰 تغيير الأسعار"
ADMIN_BTN_RESELLER_STATS = "📊 إحصائيات الموزعين"

# Owner-only admin management buttons.
ADMIN_BTN_CHARGE_ADMIN = "💰 شحن رصيد أدمن"
ADMIN_BTN_LIST_ADMINS = "👥 قائمة الأدمنز"

# Reseller tree & transaction buttons.
BTN_RESELLER_MY_CUSTOMERS = "👥 زبائني"
BTN_RESELLER_TREE = "🌳 شجرة الموزعين"
BTN_RESELLER_TX_LOG = "📒 سجل المعاملات"

# Admin hidden panel buttons.
ADMIN_BTN_HIDDEN_PANEL = "🔒 لوحة الإدارة"

# Admin menu button labels.
ADMIN_BTN_STATS = "📊 إحصائيات النظام"
ADMIN_BTN_EXTRACT = "🔑 استخراج بيانات المنصة"
ADMIN_BTN_BROADCAST = "📢 رسالة للكل"
ADMIN_BTN_RENEW = "➕ تجديد اشتراك"
ADMIN_BTN_REVOKE = "🚫 إلغاء الأكسس"
ADMIN_BTN_GENKEYS = "🔑 توليد أكواد"
ADMIN_BTN_TOGGLE_MODE = "🔓 وضع عام/خاص"
ADMIN_BTN_LIST_USERS = "👥 قائمة المستخدمين"
ADMIN_BTN_ADD_ADMIN = "👤 إضافة أدمن"
ADMIN_BTN_FILES = "📥 الملفات"
ADMIN_BTN_FULL_RESET = "☢️ ريستارت شامل"

# Buttons that ``log_any_message`` should ignore when logging activity.
IGNORED_LOG_BUTTONS = (
    "👤 حسابي",
    "🤖 حل الواجبات",
    "🎁 شارك واربح",
    "🔗 ربط المنصة",
    "⭐ المتجر",
    "🆘 الدعم الفني",
    "🔙 الرئيسية",
    "👑 لوحة الإدارة",
)

__all__ = [
    # States
    "MAIN_MENU",
    "ADMIN_PANEL",
    "AWAIT_LOGIN_USERNAME",
    "AWAIT_LOGIN_PASSWORD",
    "AWAIT_RENEW_USER",
    "AWAIT_RENEW_DAYS",
    "AWAIT_REVOKE_USER",
    "AWAIT_GENKEY_COUNT",
    "AWAIT_ADD_ADMIN",
    "AWAIT_SUPPORT_MSG",
    "AWAIT_ADMIN_REPLY",
    "AWAIT_BROADCAST_MSG",
    "AWAIT_CUSTOM_REASON",
    "AWAIT_CUSTOM_DAYS",
    "AWAIT_BROADCAST_TARGET",
    "AWAIT_ADD_HW_COUNT",
    "AWAIT_ADD_HW_CONFIRM",
    "AWAIT_ADD_HW_CHOICE",
    "AWAIT_ADD_HW_ID",
    "AWAIT_BROADCAST_CONFIRM",
    "AWAIT_RESELLER_CREDIT_AMOUNT",
    "AWAIT_RESELLER_CREDIT_USER",
    "AWAIT_RESELLER_ACTIVATE_USER",
    "AWAIT_RESELLER_PRICES",
    "AWAIT_ADMIN_PASSWORD",
    "AWAIT_ADMIN_PANEL_USER_ID",
    # Payment
    "PAYMENT_SETTINGS",
    "PLANS",
    # Buttons
    "BTN_SOLVE_HOMEWORK",
    "BTN_SOLVE_EXAM",
    "BTN_SHARE_AND_EARN",
    "BTN_MY_ACCOUNT",
    "BTN_LOGIN",
    "BTN_SHOP",
    "BTN_SUPPORT",
    "BTN_ADMIN_PANEL",
    "BTN_BACK_MAIN",
    "BTN_END_SUPPORT",
    "BTN_CANCEL",
    "BTN_ACTIVATE_KEY",
    "BTN_RESELLER_MY_CUSTOMERS",
    "BTN_RESELLER_TREE",
    "BTN_RESELLER_TX_LOG",
    "ADMIN_BTN_STATS",
    "ADMIN_BTN_EXTRACT",
    "ADMIN_BTN_BROADCAST",
    "ADMIN_BTN_RENEW",
    "ADMIN_BTN_REVOKE",
    "ADMIN_BTN_GENKEYS",
    "ADMIN_BTN_TOGGLE_MODE",
    "ADMIN_BTN_LIST_USERS",
    "ADMIN_BTN_ADD_ADMIN",
    "ADMIN_BTN_FILES",
    "ADMIN_BTN_FULL_RESET",
    "ADMIN_BTN_HIDDEN_PANEL",
    "ADMIN_BTN_CHARGE_ADMIN",
    "ADMIN_BTN_LIST_ADMINS",
    "IGNORED_LOG_BUTTONS",
]
