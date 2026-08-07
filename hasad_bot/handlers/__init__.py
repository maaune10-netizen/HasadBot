"""
hasad_bot.handlers - Telegram bot handler subpackage.

This package is the refactored home of the handlers previously living
in ``hasad_bot/bot_handlers.py``. It is split by feature area:

* ``user``         - end-user flows (start, account, share, text router)
* ``homework``     - homework solving engine + controls
* ``exam``         - exam solving engine + approval callbacks
* ``login``        - dars360 platform linking conversation
* ``payment``      - shop, invoicing, payment-flow handlers
* ``subscriptions`` - key activation + admin approval/rejection flow
* ``support``      - support ticket / admin reply
* ``unlock``       - account unlock / lock request flow
* ``reports``      - per-day homework report views
* ``tunnel``       - Cloudflare tunnel manager + admin commands
* ``admin``        - admin panel, broadcast, renew, genkeys, etc.
* ``infrastructure`` - rate limiting, access checks, error/cancel
* ``constants``    - shared state constants + payment config

After this subpackage is fully imported, ``from hasad_bot.handlers
import <name>`` continues to expose the same public symbols that
``bot_handlers.py`` previously did.
"""
from __future__ import annotations

# --- user handlers -----------------------------------------------------------
from .user import (
    start,
    help_command,
    my_account,
    share_and_earn,
    handle_text,
    cmd_show_archived,
    cmd_restore_archive,
    cmd_admin_panel,
    handle_admin_password,
)

# --- homework / exam --------------------------------------------------------
from .homework import (
    solve_homework,
    engine_callback_handler,
)
from .exam import (
    solve_exam,
    exam_approve_callback,
    exam_reject_callback,
)

# --- login flow -------------------------------------------------------------
from .login import (
    cmd_login,
    login_got_username,
    login_got_password,
    select_school_callback,
    cancel_school_callback,
)

# --- payment flow -----------------------------------------------------------
from .payment import (
    create_stars_invoice_link,
    webapp_data_handler,
    pre_checkout_handler,
    successful_payment_handler,
    open_shop,
    shop_plan_callback,
    shop_pay_callback,
    send_stars_invoice,
    show_bank_instructions,
    show_stc_instructions,
    shop_back_callback,
    handle_pay_stars_callback,
)

# --- subscriptions -----------------------------------------------------------
from .subscriptions import (
    save_payment_request,
    get_all_payment_requests,
    show_all_requests_callback,
    activate_subscription,
    activate_request_callback,
    set_days_callback,
    custom_days_callback,
    handle_custom_days,
    handle_custom_days_input,
    reject_request_callback,
    reject_custom_callback,
    reject_reason_callback,
    handle_custom_reject,
    view_request_callback,
    back_to_request_callback,
)

# --- support ----------------------------------------------------------------
from .support import (
    enter_support_room,
    exit_support_room,
    support_msg_handler,
    cb_view_support_history,
    cb_reply_support,
    admin_send_reply_done,
)

# --- unlock -----------------------------------------------------------------
from .unlock import (
    cb_request_unlock,
    cb_unlock_approve,
    cb_unlock_reject,
    cb_unlock_reason,
    cb_unlock_back,
    cb_unlock_cancel,
    cb_unlock_custom_reason,
    handle_custom_reason,
    cb_back,
)

# --- reports ----------------------------------------------------------------
from .reports import (
    show_reports_list_callback,
    view_day_report_callback,
)

# --- tunnel -----------------------------------------------------------------
from .tunnel import (
    CloudflareTunnelManager,
    tunnel_manager,
    cmd_start_tunnel,
    cmd_stop_tunnel,
    cmd_tunnel_status,
    cmd_dashboard_url,
)
from .user_log import (
    cmd_user_log,
    get_user_logs,
    send_user_log_to,
    get_user_log_stats,
    resolve_user_id,
)
from .announcements import (
    AnnouncementType,
    DEFAULT_TEMPLATES,
    cmd_announce,
    ensure_announcement_tables,
    send_announcement,
    get_target_users,
    get_all_templates,
)
from .onboarding import (
    is_user_linked,
    get_link_info,
    build_link_nudge_message,
    build_link_nudge_keyboard,
    cb_link_help,
    cb_link_nudge_back,
    check_and_nudge,
)

# --- admin panel + navigation ----------------------------------------------
from .admin import (
    admin_panel,
    admin_system_stats,
    admin_extract_credentials,
    admin_broadcast_ask,
    broadcast_target_callback,
    admin_broadcast_send,
    admin_renew_ask,
    admin_renew_got_user,
    admin_renew_got_days,
    admin_revoke_ask,
    admin_revoke_done,
    admin_genkeys_ask,
    admin_genkeys_done,
    admin_toggle_mode,
    admin_list_users,
    admin_add_homework_start,
    admin_add_hw_got_id,
    admin_add_hw_got_count,
    admin_add_hw_choice_callback,
    admin_add_hw_confirm_callback,
    admin_add_admin_ask,
    admin_add_admin_done,
    admin_files,
    admin_full_reset,
    cb_user_detail,
    cb_unlock,
    cb_delete,
    admin_settings,
    admin_panel_web,
    # Navigation helpers exposed at the package root
    back_to_account_callback,
    back_to_main_callback,
)

# --- infrastructure / constants --------------------------------------------
from .infrastructure import (
    RateLimiter,
    rate_limit,
    PlaywrightError,
    safe_playwright_execute,
    check_access,
    log_any_message,
    _cancel_handler,
    error_handler,
)
from .constants import (
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
    PAYMENT_SETTINGS,
    PLANS,
)

__all__ = [
    # user
    "start", "help_command", "my_account", "share_and_earn", "handle_text",
    "cmd_show_archived", "cmd_restore_archive",
    "cmd_admin_panel", "handle_admin_password",
    # homework / exam
    "solve_homework", "engine_callback_handler",
    "solve_exam", "exam_approve_callback", "exam_reject_callback",
    # login
    "cmd_login", "login_got_username", "login_got_password",
    "select_school_callback", "cancel_school_callback",
    # payment
    "create_stars_invoice_link", "webapp_data_handler",
    "pre_checkout_handler", "successful_payment_handler",
    "open_shop", "shop_plan_callback", "shop_pay_callback",
    "send_stars_invoice", "show_bank_instructions", "show_stc_instructions",
    "shop_back_callback", "handle_pay_stars_callback",
    # subscriptions
    "save_payment_request", "get_all_payment_requests",
    "show_all_requests_callback", "activate_subscription",
    "activate_request_callback", "set_days_callback",
    "custom_days_callback", "handle_custom_days", "handle_custom_days_input",
    "reject_request_callback", "reject_custom_callback",
    "reject_reason_callback", "handle_custom_reject",
    "view_request_callback", "back_to_request_callback",
    # support
    "enter_support_room", "exit_support_room", "support_msg_handler",
    "cb_view_support_history", "cb_reply_support", "admin_send_reply_done",
    # unlock
    "cb_request_unlock", "cb_unlock_approve", "cb_unlock_reject",
    "cb_unlock_reason", "cb_unlock_back", "cb_unlock_cancel",
    "cb_unlock_custom_reason", "handle_custom_reason", "cb_back",
    # reports
    "show_reports_list_callback", "view_day_report_callback",
    # tunnel
    "CloudflareTunnelManager", "tunnel_manager",
    "cmd_start_tunnel", "cmd_stop_tunnel", "cmd_tunnel_status", "cmd_dashboard_url",
    "cmd_user_log", "cmd_announce",
    "ensure_announcement_tables", "send_announcement", "AnnouncementType",
    "is_user_linked", "build_link_nudge_message", "build_link_nudge_keyboard",
    "cb_link_help", "cb_link_nudge_back", "check_and_nudge", "get_user_logs", "send_user_log_to",
    # admin
    "admin_panel", "admin_system_stats", "admin_extract_credentials",
    "admin_broadcast_ask", "broadcast_target_callback", "admin_broadcast_send",
    "admin_renew_ask", "admin_renew_got_user", "admin_renew_got_days",
    "admin_revoke_ask", "admin_revoke_done",
    "admin_genkeys_ask", "admin_genkeys_done", "admin_toggle_mode",
    "admin_list_users",
    "admin_add_homework_start", "admin_add_hw_got_id", "admin_add_hw_got_count",
    "admin_add_hw_choice_callback", "admin_add_hw_confirm_callback",
    "admin_add_admin_ask", "admin_add_admin_done",
    "admin_files", "admin_full_reset",
    "cb_user_detail", "cb_unlock", "cb_delete",
    "admin_settings", "admin_panel_web",
    "back_to_account_callback", "back_to_main_callback",
    # infrastructure
    "RateLimiter", "rate_limit", "PlaywrightError",
    "safe_playwright_execute", "check_access", "log_any_message",
    "_cancel_handler", "error_handler",
    # constants / state
    "MAIN_MENU", "ADMIN_PANEL",
    "AWAIT_LOGIN_USERNAME", "AWAIT_LOGIN_PASSWORD",
    "AWAIT_RENEW_USER", "AWAIT_RENEW_DAYS",
    "AWAIT_REVOKE_USER", "AWAIT_GENKEY_COUNT", "AWAIT_ADD_ADMIN",
    "AWAIT_SUPPORT_MSG", "AWAIT_ADMIN_REPLY", "AWAIT_BROADCAST_MSG",
    "AWAIT_CUSTOM_REASON", "AWAIT_CUSTOM_DAYS",
    "AWAIT_BROADCAST_TARGET",
    "AWAIT_ADD_HW_COUNT", "AWAIT_ADD_HW_CONFIRM",
    "AWAIT_ADD_HW_CHOICE", "AWAIT_ADD_HW_ID",
    "AWAIT_BROADCAST_CONFIRM",
    "PAYMENT_SETTINGS", "PLANS",
]
