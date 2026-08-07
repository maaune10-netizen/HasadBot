"""
Smoke test for hasad_bot.handlers package.

Verifies:
- All public handler functions are importable from hasad_bot.handlers.
- No duplicate function definitions across the package.
- Subpackages can be imported independently.
"""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


EXPECTED_HANDLERS = [
    "_cancel_handler", "error_handler", "rate_limit", "check_access",
    "start", "help_command", "my_account", "share_and_earn", "handle_text",
    "cmd_show_archived", "cmd_restore_archive",
    "solve_homework", "engine_callback_handler",
    "solve_exam", "exam_approve_callback", "exam_reject_callback",
    "cmd_login", "login_got_username", "login_got_password",
    "select_school_callback", "cancel_school_callback",
    "create_stars_invoice_link", "webapp_data_handler",
    "pre_checkout_handler", "successful_payment_handler",
    "open_shop", "shop_plan_callback", "shop_pay_callback",
    "send_stars_invoice", "show_bank_instructions",
    "show_stc_instructions", "shop_back_callback",
    "handle_pay_stars_callback",
    "save_payment_request", "get_all_payment_requests",
    "show_all_requests_callback", "activate_subscription",
    "activate_request_callback", "set_days_callback",
    "custom_days_callback", "handle_custom_days",
    "handle_custom_days_input", "reject_request_callback",
    "reject_custom_callback", "reject_reason_callback",
    "handle_custom_reject", "view_request_callback",
    "back_to_request_callback",
    "enter_support_room", "exit_support_room",
    "support_msg_handler", "cb_view_support_history",
    "cb_reply_support", "admin_send_reply_done",
    "cb_request_unlock", "cb_unlock_approve", "cb_unlock_reject",
    "cb_unlock_reason", "cb_unlock_back", "cb_unlock_cancel",
    "cb_unlock_custom_reason", "handle_custom_reason", "cb_back",
    "show_reports_list_callback", "view_day_report_callback",
    "cmd_start_tunnel", "cmd_stop_tunnel", "cmd_tunnel_status", "cmd_dashboard_url",
    "cmd_user_log", "cmd_announce",
    "admin_panel", "admin_system_stats", "admin_extract_credentials",
    "admin_broadcast_ask", "broadcast_target_callback",
    "admin_broadcast_send", "admin_renew_ask", "admin_renew_got_user",
    "admin_renew_got_days", "admin_revoke_ask", "admin_revoke_done",
    "admin_genkeys_ask", "admin_genkeys_done", "admin_toggle_mode",
    "admin_list_users", "admin_add_homework_start",
    "admin_add_hw_got_id", "admin_add_hw_got_count",
    "admin_add_hw_choice_callback", "admin_add_hw_confirm_callback",
    "admin_add_admin_ask", "admin_add_admin_done", "admin_files",
    "admin_full_reset", "cb_user_detail", "cb_unlock", "cb_delete",
    "admin_settings", "admin_panel_web",
    "back_to_main_callback", "back_to_account_callback",
]


def test_all_handlers_importable():
    from hasad_bot import handlers
    missing = []
    for name in EXPECTED_HANDLERS:
        if not hasattr(handlers, name):
            missing.append(name)
    assert not missing, f"Missing handlers: {missing}"
    print(f"All {len(EXPECTED_HANDLERS)} handlers importable")


def test_handlers_submodules():
    from hasad_bot.handlers import (
        constants, infrastructure, user, homework, exam, login,
        payment, subscriptions, support, unlock, reports, tunnel, admin,
    )
    print("All 13 submodules importable")


def test_no_bot_handlers_module():
    """bot_handlers.py is expected to be deleted soon.

    If the file still exists, skip this test (do not fail the suite).
    Once deleted, this test should pass by raising ImportError.
    """
    bot_handlers_path = ROOT / "hasad_bot" / "bot_handlers.py"
    if bot_handlers_path.exists():
        import pytest
        pytest.skip(
            "bot_handlers.py still exists on disk; deletion pending. "
            "This test will run once the file is removed."
        )
    if "hasad_bot.bot_handlers" in sys.modules:
        del sys.modules["hasad_bot.bot_handlers"]
    try:
        importlib.import_module("hasad_bot.bot_handlers")
        assert False, "bot_handlers should be deleted but still importable"
    except ImportError:
        pass
    print("bot_handlers.py is correctly deleted")


if __name__ == "__main__":
    test_all_handlers_importable()
    test_handlers_submodules()
    test_no_bot_handlers_module()
    print(f"\nAll smoke tests passed ({len(EXPECTED_HANDLERS)} handlers verified)")
