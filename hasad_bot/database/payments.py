#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stars payment idempotency ledger.

Marks a stars charge as processed so a re-delivered successful_payment message
(Telegram retries/redelivery) cannot grant extra free subscription days.
"""
import time

from loguru import logger

from .pool import db_pool


async def is_stars_payment_processed(charge_id: str) -> bool:
    """هل تمت معالجة هذا الـ charge سابقاً؟ (SELECT فقط — بدون كتابة)"""
    try:
        conn = await db_pool.get_connection()
        async with conn.execute(
            "SELECT 1 FROM stars_payments WHERE charge_id = ? LIMIT 1", (charge_id,)
        ) as c:
            row = await c.fetchone()
        return row is not None
    except Exception as e:
        logger.error(f"Error checking stars payment: {e}")
        return False


async def mark_stars_payment_processed(charge_id: str, user_id: int, plan_id: str, amount: int) -> bool:
    """Record a processed stars charge idempotently.

    Returns True if the row was actually inserted (first time this charge_id
    was seen), False if it already existed (duplicate / re-delivered message).
    """
    try:
        conn = await db_pool.get_connection()
        cursor = await conn.execute(
            """
            INSERT OR IGNORE INTO stars_payments
            (charge_id, user_id, plan_id, amount, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (charge_id, user_id, plan_id, amount, time.time()),
        )
        await conn.commit()
        return cursor.rowcount == 1
    except Exception as e:
        # فشل INSERT يترك transaction مفتوحًا على الاتصال المشترك → قفل دائم للقاعدة
        try:
            await conn.rollback()
        except Exception:
            pass
        logger.error(f"Error marking stars payment processed: {e}")
        return True
