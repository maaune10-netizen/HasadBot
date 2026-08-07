#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database package for HASAD Bot.

Public surface (all names below are importable as `from hasad_bot.database import X`):
  Pool:                  DatabasePool, _db_pool
  Lifecycle:             db_init, ensure_payment_requests_table, auto_cleanup_db
   Users:                 db_get_user, db_get_user_by_platform, db_set_user, db_all_users,
                         db_get_vip_users, db_delete_user, update_user_last_active,
                         update_user_stats_comprehensive, populate_all_user_stats,
                         is_admin, is_subscribed, is_vip, is_teacher,
                          is_reseller, promote_to_reseller, demote_from_reseller, demote_from_admin,
                         remove_customer_from_reseller, get_reseller_customers, get_reseller_stats,
                         promote_to_admin, get_admin_sub_resellers, get_admin_customers,
                         create_sub_reseller, get_all_full_admins,
                         db_update_rank, db_save_cv, db_log, log_user_message
  Subscriptions:         db_init_plans, get_plan_by_id, get_all_plans,
                         create_user_subscription, get_user_subscription,
                         db_create_keys, db_activate_key, _get_plan_name_from_days
   Attempts:              get_user_remaining_homeworks, deduct_homework_attempt,
                         get_user_homeworks_stats, get_user_free_attempts,
                         update_user_free_attempts, get_remaining_homeworks,
                         get_remaining_exams, get_used_exam_attempts,
                         deduct_exam, deduct_homework, db_deduct_attempt,
                         get_reseller_credit, add_reseller_credit, deduct_reseller_credit,
                         get_reseller_credit_price, set_reseller_credit_price,
                         get_all_reseller_credit_prices,
                         transfer_credit, get_transaction_log
  Sessions:              start_homework_session, update_homework_session, get_user_homework_sessions
  Notifications:         db_add_radar_notification, db_was_notified,
                         create_notification, mark_notification_read, get_user_notifications,
                         create_support_ticket, add_support_message,
                         close_support_ticket, get_user_tickets
  Unlock:                save_unlock_request, update_unlock_request, get_pending_unlock_requests,
                         archive_user_credentials, restore_archived_credentials,
                         get_all_archived_credentials, get_archived_by_user_id
  Analytics:             get_user_total_stats, get_user_reports_days, get_user_report_by_date,
                         get_dashboard_stats, get_users_count_by_target,
                         get_users_by_target, get_target_name, collect_and_save_dashboard_stats
  Exams:                 update_exam_vote, get_confirmed_exam_answer
  Files:                 download_and_save_image, save_image_reference,
                         download_and_save_file, save_file_reference, get_image_path
  Auth:                  db_setting, db_set_setting, is_public_mode, set_public_mode,
                         is_bot_frozen, set_bot_frozen,
                         log_admin_action, log_login_attempt, populate_login_logs_from_history
"""

# Pool — the shared singleton
from .pool import DatabasePool, db_pool as _db_pool

# Lifecycle
from .init import db_init, ensure_payment_requests_table, auto_cleanup_db

# Users
from .users import (
    db_get_user, db_get_user_by_platform, db_set_user, db_all_users,
    db_get_vip_users, db_delete_user, update_user_last_active,
    update_user_stats_comprehensive, populate_all_user_stats,
    is_admin, is_subscribed, is_vip, is_teacher, is_reseller,
    promote_to_reseller, demote_from_reseller, demote_from_admin, remove_customer_from_reseller,
    get_reseller_customers, get_reseller_stats,
    promote_to_admin, get_admin_sub_resellers, get_admin_customers,
    create_sub_reseller, get_all_full_admins,
    db_update_rank, db_save_cv, db_log, log_user_message,
)

# Subscriptions
from .subscriptions import (
    db_init_plans, get_plan_by_id, get_all_plans,
    create_user_subscription, get_user_subscription,
    db_create_keys, db_activate_key, _get_plan_name_from_days,
    generate_reseller_key, activate_reseller_key, get_reseller_keys,
)

# Attempts
from .attempts import (
    get_user_remaining_homeworks, deduct_homework_attempt,
    get_user_homeworks_stats, get_user_free_attempts,
    update_user_free_attempts, get_remaining_homeworks,
    get_remaining_exams, get_used_exam_attempts,
    deduct_exam, deduct_homework, db_deduct_attempt,
    get_reseller_credit, add_reseller_credit, deduct_reseller_credit,
    get_reseller_credit_price, set_reseller_credit_price,
    get_all_reseller_credit_prices,
    transfer_credit, get_transaction_log,
)

# Sessions
from .sessions import (
    start_homework_session, update_homework_session, get_user_homework_sessions,
)

# Notifications
from .notifications import (
    db_add_radar_notification, db_was_notified,
    create_notification, mark_notification_read, get_user_notifications,
    create_support_ticket, add_support_message,
    close_support_ticket, get_user_tickets,
)

# Unlock
from .unlock import (
    save_unlock_request, update_unlock_request, get_pending_unlock_requests,
    archive_user_credentials, restore_archived_credentials,
    get_all_archived_credentials, get_archived_by_user_id,
)

# Analytics
from .analytics import (
    get_user_total_stats, get_user_reports_days, get_user_report_by_date,
    get_dashboard_stats, get_users_count_by_target,
    get_users_by_target, get_target_name, collect_and_save_dashboard_stats,
)

# Exams
from .exams import update_exam_vote, get_confirmed_exam_answer

# Files
from .files import (
    download_and_save_image, save_image_reference,
    download_and_save_file, save_file_reference, get_image_path,
)

# Auth
from .auth import (
    db_setting, db_set_setting, is_public_mode, set_public_mode,
    is_bot_frozen, set_bot_frozen,
    log_admin_action, log_login_attempt, populate_login_logs_from_history,
)


__all__ = [
    # Pool
    "DatabasePool", "_db_pool",
    # Lifecycle
    "db_init", "ensure_payment_requests_table", "auto_cleanup_db",
    # Users
    "db_get_user", "db_get_user_by_platform", "db_set_user", "db_all_users",
    "db_get_vip_users", "db_delete_user", "update_user_last_active",
    "update_user_stats_comprehensive", "populate_all_user_stats",
    "is_admin", "is_subscribed", "is_vip", "is_teacher", "is_reseller",
    "promote_to_reseller", "demote_from_reseller", "demote_from_admin",
    "get_reseller_customers", "get_reseller_stats",
    "promote_to_admin", "get_admin_sub_resellers", "get_admin_customers",
    "create_sub_reseller", "get_all_full_admins",
    "db_update_rank", "db_save_cv", "db_log", "log_user_message",
    # Subscriptions
    "db_init_plans", "get_plan_by_id", "get_all_plans",
    "create_user_subscription", "get_user_subscription",
    "db_create_keys", "db_activate_key", "_get_plan_name_from_days",
    "generate_reseller_key", "activate_reseller_key", "get_reseller_keys",
    # Attempts
    "get_user_remaining_homeworks", "deduct_homework_attempt",
    "get_user_homeworks_stats", "get_user_free_attempts",
    "update_user_free_attempts", "get_remaining_homeworks",
    "get_remaining_exams", "get_used_exam_attempts",
    "deduct_exam", "deduct_homework", "db_deduct_attempt",
    "get_reseller_credit", "add_reseller_credit", "deduct_reseller_credit",
    "get_reseller_credit_price", "set_reseller_credit_price",
    "get_all_reseller_credit_prices",
    "transfer_credit", "get_transaction_log",
    # Sessions
    "start_homework_session", "update_homework_session", "get_user_homework_sessions",
    # Notifications
    "db_add_radar_notification", "db_was_notified",
    "create_notification", "mark_notification_read", "get_user_notifications",
    "create_support_ticket", "add_support_message",
    "close_support_ticket", "get_user_tickets",
    # Unlock
    "save_unlock_request", "update_unlock_request", "get_pending_unlock_requests",
    "archive_user_credentials", "restore_archived_credentials",
    "get_all_archived_credentials", "get_archived_by_user_id",
    # Analytics
    "get_user_total_stats", "get_user_reports_days", "get_user_report_by_date",
    "get_dashboard_stats", "get_users_count_by_target",
    "get_users_by_target", "get_target_name", "collect_and_save_dashboard_stats",
    # Exams
    "update_exam_vote", "get_confirmed_exam_answer",
    # Files
    "download_and_save_image", "save_image_reference",
    "download_and_save_file", "save_file_reference", "get_image_path",
    # Auth
    "db_setting", "db_set_setting", "is_public_mode", "set_public_mode",
    "is_bot_frozen", "set_bot_frozen",
    "log_admin_action", "log_login_attempt", "populate_login_logs_from_history",
]
