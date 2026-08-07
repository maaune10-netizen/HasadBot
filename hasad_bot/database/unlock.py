#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unlock requests (when account is locked) and credential archive/restore.
"""
import time
from typing import List, Dict

import aiosqlite
from loguru import logger

from .pool import db_pool
from .users import db_get_user


# ==============================================================================
# Unlock requests
# ==============================================================================

async def save_unlock_request(uid: int, user_name: str, platform_user: str) -> int:
    """حفظ طلب فك القفل"""
    try:
        conn = await db_pool.get_connection()

        await conn.execute("""
            UPDATE users SET lock_request = 1, lock_request_date = ?
            WHERE telegram_id = ?
        """, (time.time(), uid))

        await conn.execute("""
            INSERT INTO unlock_requests (user_id, user_name, platform_user, request_date, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (uid, user_name, platform_user, time.time()))
        await conn.commit()

        cursor = await conn.execute("SELECT last_insert_rowid()")
        row = await cursor.fetchone()
        request_id = row[0] if row else 0

        logger.info(f"📝 Unlock request saved: ID={request_id}, User={uid}")
        return request_id

    except Exception as e:
        logger.error(f"Error saving unlock request: {e}")
        return 0


async def update_unlock_request(request_id: int, status: str, processed_by: int, reason: str = ""):
    """تحديث حالة طلب فك القفل"""
    try:
        conn = await db_pool.get_connection()

        async with conn.execute("SELECT user_id FROM unlock_requests WHERE id = ?", (request_id,)) as c:
            row = await c.fetchone()
            user_id = row[0] if row else None

        await conn.execute("""
            UPDATE unlock_requests
            SET status = ?, processed_by = ?, processed_date = ?, reason = ?
            WHERE id = ?
        """, (status, processed_by, time.time(), reason, request_id))

        if status == 'approved' and user_id:
            await conn.execute("""
                UPDATE users SET lock_request = 0, locked_to = NULL, dars360_user = NULL, dars360_pass = NULL
                WHERE telegram_id = ?
            """, (user_id,))
        elif status == 'rejected' and user_id:
            await conn.execute("""
                UPDATE users SET lock_request = 0
                WHERE telegram_id = ?
            """, (user_id,))

        await conn.commit()
        logger.info(f"✅ Unlock request {request_id} updated: {status}")

    except Exception as e:
        logger.error(f"Error updating unlock request: {e}")


async def get_pending_unlock_requests() -> List[Dict]:
    """جلب طلبات فك القفل المعلقة"""
    try:
        conn = await db_pool.get_connection()
        conn.row_factory = aiosqlite.Row

        requests = []
        async with conn.execute("""
            SELECT ur.*, u.name, u.dars360_user
            FROM unlock_requests ur
            JOIN users u ON ur.user_id = u.telegram_id
            WHERE ur.status = 'pending'
            ORDER BY ur.request_date DESC
        """) as cursor:
            async for row in cursor:
                requests.append(dict(row))

        return requests
    except Exception as e:
        logger.error(f"Error getting pending unlock requests: {e}")
        return []


# ==============================================================================
# Credential archive
# ==============================================================================

async def archive_user_credentials(user_id: int, archived_by: int, archived_by_name: str, reason: str = "فك القفل"):
    """نقل بيانات المستخدم من جدول users إلى جدول archived_credentials"""
    try:
        conn = await db_pool.get_connection()

        user = await db_get_user(user_id)
        if not user:
            return False, "المستخدم غير موجود"

        platform_user = user.get('dars360_user')
        platform_pass = user.get('dars360_pass')

        if not platform_user or not platform_pass:
            return False, "لا توجد بيانات منصة لأرشفها"

        await conn.execute("""
            INSERT INTO archived_credentials
            (user_id, user_name, platform_user, platform_pass, platform_url, platform_id,
             archived_at, archived_by, archived_by_name, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            user.get('name', ''),
            platform_user,
            platform_pass,
            user.get('platform_url', ''),
            user.get('platform_id', ''),
            time.time(),
            archived_by,
            archived_by_name,
            reason
        ))

        await conn.execute("""
            UPDATE users
            SET dars360_user = NULL,
                dars360_pass = NULL,
                platform_url = NULL,
                platform_id = NULL,
                locked_to = NULL,
                lock_request = 0
            WHERE telegram_id = ?
        """, (user_id,))

        await conn.commit()

        logger.info(f"📦 Archived credentials for user {user_id} by {archived_by_name}")
        return True, "تم أرشفة البيانات بنجاح"

    except Exception as e:
        logger.error(f"Failed to archive credentials: {e}")
        return False, str(e)


async def restore_archived_credentials(user_id: int, restored_by: int, restored_by_name: str):
    """استعادة أحدث بيانات مؤرشفة للمستخدم إلى جدول users"""
    try:
        conn = await db_pool.get_connection()

        async with conn.execute("""
            SELECT * FROM archived_credentials
            WHERE user_id = ?
            ORDER BY archived_at DESC
            LIMIT 1
        """, (user_id,)) as c:
            archive = await c.fetchone()

        if not archive:
            return False, "لا توجد بيانات مؤرشفة لهذا المستخدم"

        await conn.execute("""
            UPDATE users
            SET dars360_user = ?,
                dars360_pass = ?,
                platform_url = ?,
                platform_id = ?
            WHERE telegram_id = ?
        """, (archive[3], archive[4], archive[5], archive[6], user_id))

        await conn.execute("""
            UPDATE archived_credentials
            SET restored_at = ?, restored_by = ?, restored_by_name = ?
            WHERE id = ?
        """, (time.time(), restored_by, restored_by_name, archive[0]))

        await conn.commit()

        logger.info(f"📦 Restored credentials for user {user_id} by {restored_by_name}")
        return True, "تم استعادة البيانات بنجاح"

    except Exception as e:
        logger.error(f"Failed to restore credentials: {e}")
        return False, str(e)


async def get_all_archived_credentials(limit: int = 50):
    """جلب جميع البيانات المؤرشفة (للإدارة)"""
    try:
        conn = await db_pool.get_connection()
        conn.row_factory = aiosqlite.Row

        async with conn.execute("""
            SELECT * FROM archived_credentials
            ORDER BY archived_at DESC
            LIMIT ?
        """, (limit,)) as c:
            return await c.fetchall()

    except Exception as e:
        logger.error(f"Failed to get archived credentials: {e}")
        return []


async def get_archived_by_user_id(user_id: int):
    """جلب بيانات مؤرشفة لمستخدم معين"""
    try:
        conn = await db_pool.get_connection()
        conn.row_factory = aiosqlite.Row

        async with conn.execute("""
            SELECT * FROM archived_credentials
            WHERE user_id = ?
            ORDER BY archived_at DESC
        """, (user_id,)) as c:
            return await c.fetchall()

    except Exception as e:
        logger.error(f"Failed to get archived by user: {e}")
        return []
