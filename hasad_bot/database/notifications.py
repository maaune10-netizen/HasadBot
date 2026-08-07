#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Radar notifications, user notifications, and support tickets.
"""
import time
from typing import List, Dict

import aiosqlite
from loguru import logger

from .pool import db_pool


# ==============================================================================
# Radar notifications
# ==============================================================================

async def db_add_radar_notification(uid: int, homework_id: str):
    """تسجيل إشعار رادار"""
    conn = await db_pool.get_connection()
    await conn.execute(
        "INSERT OR IGNORE INTO radar_notifications(telegram_id, homework_id, notified_at) VALUES(?,?,?)",
        (uid, homework_id, time.time())
    )
    await conn.commit()


async def db_was_notified(uid: int, homework_id: str) -> bool:
    """التحقق مما إذا تم إشعار هذا الواجب مسبقاً"""
    conn = await db_pool.get_connection()
    async with conn.execute(
        "SELECT 1 FROM radar_notifications WHERE telegram_id=? AND homework_id=?",
        (uid, homework_id)
    ) as c:
        return await c.fetchone() is not None


# ==============================================================================
# User notifications
# ==============================================================================

async def create_notification(user_id: int, notification_type: str, title: str,
                               message: str, related_id: str = ""):
    """إنشاء إشعار للمستخدم"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute("""
            INSERT INTO notifications
            (user_id, notification_type, title, message, related_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, notification_type, title, message[:500], related_id, time.time()))
        await conn.commit()
        logger.info(f"📝 Notification created for user {user_id}: {title}")

    except Exception as e:
        logger.error(f"Error creating notification: {e}")


async def mark_notification_read(notification_id: int):
    """تحديد إشعار كمقروء"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute("""
            UPDATE notifications SET is_read = 1 WHERE id = ?
        """, (notification_id,))
        await conn.commit()

    except Exception as e:
        logger.error(f"Error marking notification read: {e}")


async def get_user_notifications(user_id: int, unread_only: bool = False) -> List[Dict]:
    """جلب إشعارات المستخدم"""
    try:
        conn = await db_pool.get_connection()

        query = "SELECT * FROM notifications WHERE user_id = ?"
        params = [user_id]

        if unread_only:
            query += " AND is_read = 0"

        query += " ORDER BY created_at DESC LIMIT 50"

        notifications = []
        async with conn.execute(query, params) as cursor:
            async for row in cursor:
                notifications.append(dict(row))

        return notifications
    except Exception as e:
        logger.error(f"Error getting user notifications: {e}")
        return []


# ==============================================================================
# Support tickets
# ==============================================================================

async def create_support_ticket(user_id: int, user_name: str, ticket_type: str = 'general',
                                 related_request_id: int = None, related_request_type: str = None) -> int:
    """إنشاء تذكرة دعم جديدة"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute("""
            INSERT INTO support_tickets
            (user_id, user_name, ticket_type, related_request_id, related_request_type,
             status, created_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?)
        """, (user_id, user_name, ticket_type, related_request_id, related_request_type, time.time()))
        await conn.commit()

        cursor = await conn.execute("SELECT last_insert_rowid()")
        row = await cursor.fetchone()
        ticket_id = row[0] if row else 0

        logger.info(f"📝 Support ticket created: ID={ticket_id}, User={user_id}")
        return ticket_id

    except Exception as e:
        logger.error(f"Error creating support ticket: {e}")
        return 0


async def add_support_message(ticket_id: int, user_id: int, user_name: str,
                              message_text: str = "", has_photo: bool = False,
                              photo_file_id: str = "", is_admin: bool = False):
    """إضافة رسالة إلى تذكرة الدعم"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute("""
            INSERT INTO support_messages
            (ticket_id, user_id, user_name, message_text, has_photo, photo_file_id,
             is_admin, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (ticket_id, user_id, user_name, message_text[:2000], has_photo,
              photo_file_id, is_admin, time.time()))
        await conn.commit()

        logger.info(f"📝 Support message added to ticket {ticket_id}")

    except Exception as e:
        logger.error(f"Error adding support message: {e}")


async def close_support_ticket(ticket_id: int, closed_by: int):
    """إغلاق تذكرة الدعم"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute("""
            UPDATE support_tickets
            SET status = 'closed', closed_at = ?, closed_by = ?
            WHERE id = ?
        """, (time.time(), closed_by, ticket_id))
        await conn.commit()
        logger.info(f"✅ Support ticket {ticket_id} closed")

    except Exception as e:
        logger.error(f"Error closing support ticket: {e}")


async def get_user_tickets(user_id: int) -> List[Dict]:
    """جلب تذاكر الدعم لمستخدم معين"""
    try:
        conn = await db_pool.get_connection()

        tickets = []
        async with conn.execute("""
            SELECT * FROM support_tickets
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,)) as cursor:
            async for row in cursor:
                tickets.append(dict(row))

        return tickets
    except Exception as e:
        logger.error(f"Error getting user tickets: {e}")
        return []
