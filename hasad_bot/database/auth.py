#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Admin actions, login logs, public mode flag, bot freeze flag, settings store.
"""
import asyncio
import time
from loguru import logger

from .pool import db_pool

# قفل لتسلسل كتابة سجلات التدقيق على الاتصال المشترك (يمنع التراجع عن معاملة قيد التنفيذ لكوروتين أخرى)
_audit_lock = asyncio.Lock()


# ==============================================================================
# Settings store
# ==============================================================================

async def db_setting(key: str, default: str = "") -> str:
    """Get setting"""
    conn = await db_pool.get_connection()
    async with conn.execute("SELECT value FROM settings WHERE key=?", (key,)) as c:
        r = await c.fetchone()
        return r[0] if r else default


async def db_set_setting(key: str, value: str):
    """Set setting"""
    conn = await db_pool.get_connection()
    await conn.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value)
    )
    await conn.commit()


async def is_public_mode() -> bool:
    return (await db_setting("public_mode", "0")) == "1"


async def set_public_mode(v: bool):
    await db_set_setting("public_mode", "1" if v else "0")


# ==============================================================================
# Bot freeze
# ==============================================================================

async def is_bot_frozen() -> bool:
    """التحقق من حالة تجميد البوت"""
    try:
        conn = await db_pool.get_connection()
        async with conn.execute("SELECT value FROM settings WHERE key = 'bot_frozen'") as c:
            row = await c.fetchone()
            return row[0] == "1" if row else False
    except:
        return False


async def set_bot_frozen(frozen: bool):
    """تحديث حالة تجميد البوت"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES ('bot_frozen', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("1" if frozen else "0",)
        )
        await conn.commit()
    except:
        pass


# ==============================================================================
# Admin actions log
# ==============================================================================

async def log_admin_action(admin_id: int, admin_name: str, action_type: str,
                           target_user_id: int = None, target_user_name: str = None,
                           old_value: str = "", new_value: str = "", details: str = ""):
    """تسجيل أي إجراء يقوم به الأدمن"""
    async with _audit_lock:
        try:
            conn = await db_pool.get_connection()
            await conn.execute("""
                INSERT INTO admin_actions
                (admin_id, admin_name, action_type, target_user_id, target_user_name,
                 old_value, new_value, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (admin_id, admin_name, action_type, target_user_id, target_user_name,
                  old_value, new_value, details, time.time()))
            await conn.commit()
            logger.info(f"📝 Admin action logged: {admin_name} -> {action_type}")

        except Exception as e:
            # حرج: فشل INSERT يترك transaction مفتوح على الاتصال المشترك → قفل دائم للقاعدة
            try:
                await conn.rollback()
            except Exception:
                pass
            logger.error(f"Error logging admin action: {e}")


# ==============================================================================
# Login logs
# ==============================================================================

async def log_login_attempt(user_id: int, platform_user: str, success: bool = True,
                             error_message: str = "", ip_address: str = ""):
    """تسجيل محاولة تسجيل الدخول"""
    async with _audit_lock:
        try:
            conn = await db_pool.get_connection()
            await conn.execute("""
                INSERT INTO login_logs
                (user_id, platform_user, success, error_message, ip_address, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, platform_user, 1 if success else 0, error_message[:200], ip_address, time.time()))
            await conn.commit()
            logger.info(f"🔐 Login attempt logged: User={user_id}, Success={success}")

        except Exception as e:
            try:
                await conn.rollback()
            except Exception:
                pass
            logger.error(f"Error logging login attempt: {e}")


async def populate_login_logs_from_history():
    """تعبئة جدول login_logs من سجل المستخدمين (مرة واحدة)"""
    conn = await db_pool.get_connection()

    async with conn.execute("SELECT telegram_id, dars360_user, created_at FROM users WHERE dars360_user IS NOT NULL") as c:
        users = await c.fetchall()

    count = 0
    for user in users:
        uid = user[0]
        platform_user = user[1]
        created_at = user[2] or time.time()

        await conn.execute("""
            INSERT INTO login_logs (user_id, platform_user, success, created_at)
            VALUES (?, ?, 1, ?)
        """, (uid, platform_user, created_at))
        count += 1

    await conn.commit()
    print(f"✅ تم إضافة {count} سجل دخول إلى login_logs")
