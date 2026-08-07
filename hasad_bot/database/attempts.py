#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Homework and exam balance: remaining counts, deduct logic, free attempts.
"""
import time
from typing import Dict

import aiosqlite
from loguru import logger

from hasad_bot.config import config
from .pool import db_pool
from .users import db_get_user, is_subscribed


# ==============================================================================
# Free attempts
# ==============================================================================

async def get_user_free_attempts(uid: int) -> int:
    """جلب عدد الواجبات المجانية المتبقية للمستخدم"""
    try:
        conn = await db_pool.get_connection()
        async with conn.execute("SELECT free_attempts FROM users WHERE telegram_id = ?", (uid,)) as c:
            row = await c.fetchone()
            if row:
                return row[0] or 0
    except Exception as e:
        logger.error(f"Error getting free attempts: {e}")
    return 0


async def update_user_free_attempts(uid: int, new_count: int):
    """تحديث عدد الواجبات المجانية للمستخدم"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute("UPDATE users SET free_attempts = ? WHERE telegram_id = ?", (new_count, uid))
        await conn.commit()
        logger.info(f"✅ Updated free attempts for user {uid}: {new_count}")
    except Exception as e:
        logger.error(f"Error updating free attempts: {e}")


# ==============================================================================
# Homework remaining + deduct
# ==============================================================================

async def get_user_remaining_homeworks(uid: int) -> int:
    """حساب عدد الواجبات المتبقية للمستخدم - الكل يحسب"""
    user = await db_get_user(uid)
    if not user:
        return 0

    conn = await db_pool.get_connection()

    async with conn.execute("""
        SELECT homeworks_used, max_homeworks
        FROM user_subscriptions
        WHERE user_id = ? AND is_active = 1 AND end_date > ?
        ORDER BY end_date DESC LIMIT 1
    """, (uid, time.time())) as c:
        sub = await c.fetchone()

    if sub:
        used, max_hw = sub
        remaining = max_hw - used
        logger.info(f"📊 المستخدم {uid}: استخدم {used} من {max_hw} - باقي {remaining}")
        return max(0, remaining)

    return user.get("free_attempts", 0)


async def deduct_homework_attempt(uid: int) -> bool:
    """
    خصم واجب من المستخدم
    ممنوع الدين نهائياً - إذا وصل للحد يتوقف
    """
    user = await db_get_user(uid)
    if not user:
        return False

    conn = await db_pool.get_connection()

    async with conn.execute("""
        SELECT id, homeworks_used, max_homeworks
        FROM user_subscriptions
        WHERE user_id = ? AND is_active = 1 AND end_date > ?
        ORDER BY end_date DESC LIMIT 1
    """, (uid, time.time())) as c:
        sub = await c.fetchone()

    if sub:
        sub_id, used, max_hw = sub

        if used >= max_hw:
            logger.warning(f"❌ المستخدم {uid} استنفذ جميع واجباته ({used}/{max_hw}) - ممنوع الدين")
            return False

        await conn.execute("""
            UPDATE user_subscriptions
            SET homeworks_used = homeworks_used + 1
            WHERE id = ?
        """, (sub_id,))

        await conn.execute("""
            UPDATE users SET total_hw_solved = total_hw_solved + 1
            WHERE telegram_id = ?
        """, (uid,))

        await conn.commit()
        logger.info(f"✅ خصم واجب من الاشتراك للمستخدم {uid}: {used+1}/{max_hw}")
        return True

    free_attempts = user.get("free_attempts", 0)

    if free_attempts <= 0:
        logger.warning(f"❌ المستخدم {uid} ليس لديه محاولات مجانية ({free_attempts}) - ممنوع الدين")
        return False

    await conn.execute("""
        UPDATE users
        SET free_attempts = free_attempts - 1,
            total_hw_solved = total_hw_solved + 1
        WHERE telegram_id = ?
    """, (uid,))
    await conn.commit()

    logger.info(f"✅ خصم محاولة مجانية للمستخدم {uid}: متبقي {free_attempts - 1}")
    return True


async def db_deduct_attempt(uid: int):
    """Deduct free attempt (قديمة - استخدم deduct_homework_attempt بدلاً منها)"""
    await deduct_homework_attempt(uid)


async def get_user_homeworks_stats(uid: int) -> Dict:
    """إحصائيات الواجبات للمستخدم"""
    user = await db_get_user(uid)
    if not user:
        return {"remaining": 0, "total_used": 0, "max_allowed": 0, "plan_name": None, "total_solved": 0, "free_attempts": 0}

    stats = {
        "total_solved": user.get("total_hw_solved", 0),
        "free_attempts": user.get("free_attempts", 0),
        "remaining": 0,
        "total_used": 0,
        "max_allowed": 0,
        "plan_name": None,
        "plan_end_date": None
    }

    from .subscriptions import get_user_subscription
    sub = await get_user_subscription(uid)
    if sub:
        stats["remaining"] = sub.get('max_homeworks', 0) - sub.get('homeworks_used', 0)
        stats["total_used"] = sub.get('homeworks_used', 0)
        stats["max_allowed"] = sub.get('max_homeworks', 0)
        stats["plan_name"] = sub.get('plan_name', None)
        stats["plan_end_date"] = sub.get('end_date', sub.get('expiry_date', None))
    else:
        stats["remaining"] = user.get("free_attempts", 0)
        stats["max_allowed"] = user.get("free_attempts", 0)

    return stats


async def get_remaining_homeworks(uid: int) -> int:
    """
    عدد الواجبات المتبقية للمستخدم من الاشتراك النشط
    """
    if uid == config.admin_id:
        return 999999

    conn = await db_pool.get_connection()
    now_ts = time.time()

    async with conn.execute("""
        SELECT max_homeworks, homeworks_used
        FROM user_subscriptions
        WHERE user_id = ? AND is_active = 1 AND end_date > ?
        ORDER BY end_date DESC LIMIT 1
    """, (uid, now_ts)) as c:
        sub = await c.fetchone()

        if sub:
            max_hw, used = sub
            remaining = max_hw - (used or 0)
            return max(0, remaining)

    return 0


async def deduct_homework(uid: int, amount: int = 1) -> bool:
    """
    خصم واجبات من المستخدم (يدعم خصم أكثر من واحد)
    """
    if uid == config.admin_id:
        return True

    conn = await db_pool.get_connection()
    now_ts = time.time()

    async with conn.execute("""
        SELECT id, homeworks_used, max_homeworks
        FROM user_subscriptions
        WHERE user_id = ? AND is_active = 1 AND end_date > ?
        ORDER BY end_date DESC LIMIT 1
    """, (uid, now_ts)) as c:
        sub = await c.fetchone()

        if sub:
            sub_id, used, max_hw = sub

            if used + amount > max_hw:
                return False

            await conn.execute("""
                UPDATE user_subscriptions
                SET homeworks_used = homeworks_used + ?
                WHERE id = ?
            """, (amount, sub_id))

            await conn.execute("""
                UPDATE users SET total_hw_solved = total_hw_solved + ?
                WHERE telegram_id = ?
            """, (amount, uid))

            await conn.commit()
            logger.info(f"✅ خصم {amount} واجب من الاشتراك للمستخدم {uid}")
            return True

    return False


# ==============================================================================
# Exam attempts
# ==============================================================================

async def get_remaining_exams(uid: int) -> int:
    """
    حساب عدد الاختبارات المتبقية للمستخدم
    - للمشترك: رصيد الواجبات ÷ EXAM_COST_IN_HOMEWORKS
    - لغير المشترك: FREE_EXAM_ATTEMPTS - المستخدم
    """
    if uid == config.admin_id:
        return 999999

    if await is_subscribed(uid):
        remaining_hw = await get_remaining_homeworks(uid)
        return remaining_hw // config.EXAM_COST_IN_HOMEWORKS

    conn = await db_pool.get_connection()
    async with conn.execute("""
        SELECT free_exam_attempts_used FROM users WHERE telegram_id = ?
    """, (uid,)) as c:
        row = await c.fetchone()
        used = row[0] if row else 0
        return max(0, config.FREE_EXAM_ATTEMPTS - used)


async def get_used_exam_attempts(uid: int) -> int:
    """جلب عدد المحاولات المجانية المستخدمة (لغير المشتركين)"""
    conn = await db_pool.get_connection()
    async with conn.execute("""
        SELECT free_exam_attempts_used FROM users WHERE telegram_id = ?
    """, (uid,)) as c:
        row = await c.fetchone()
        return row[0] if row else 0


async def deduct_exam(uid: int) -> bool:
    """
    خصم اختبار واحد من المستخدم
    - للمشترك: يخصم EXAM_COST_IN_HOMEWORKS من رصيد الواجبات
    - لغير المشترك: يزيد free_exam_attempts_used بواحد
    """
    if uid == config.admin_id:
        return True

    if await is_subscribed(uid):
        return await deduct_homework(uid, amount=config.EXAM_COST_IN_HOMEWORKS)

    conn = await db_pool.get_connection()

    async with conn.execute("""
        SELECT free_exam_attempts_used FROM users WHERE telegram_id = ?
    """, (uid,)) as c:
        row = await c.fetchone()
        used = row[0] if row else 0

        if used >= config.FREE_EXAM_ATTEMPTS:
            return False

        await conn.execute("""
            UPDATE users
            SET free_exam_attempts_used = free_exam_attempts_used + 1
            WHERE telegram_id = ?
        """, (uid,))

        await conn.commit()
        logger.info(f"✅ خصم اختبار مجاني للمستخدم {uid} ({used+1}/{config.FREE_EXAM_ATTEMPTS})")
        return True


# ==============================================================================
# Reseller credit
# ==============================================================================

async def get_reseller_credit(reseller_id: int) -> int:
    """Get reseller's credit balance"""
    conn = await db_pool.get_connection()
    cursor = await conn.execute(
        "SELECT reseller_credit FROM users WHERE telegram_id = ?",
        (reseller_id,)
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def add_reseller_credit(reseller_id: int, amount: int, details: str = "") -> bool:
    """Add credit to reseller's wallet (admin action)"""
    try:
        conn = await db_pool.get_connection()
        cursor = await conn.execute(
            "SELECT reseller_credit FROM users WHERE telegram_id = ?",
            (reseller_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return False

        new_balance = row[0] + amount
        await conn.execute(
            "UPDATE users SET reseller_credit = ? WHERE telegram_id = ?",
            (new_balance, reseller_id)
        )

        # Log transaction
        await conn.execute(
            """INSERT INTO reseller_transactions
               (reseller_id, type, amount, balance_after, details)
               VALUES (?, 'credit_added', ?, ?, ?)""",
            (reseller_id, amount, new_balance, details)
        )
        await conn.commit()
        logger.info(f"✅ Added {amount} credit to reseller {reseller_id} (balance: {new_balance})")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to add credit to reseller {reseller_id}: {e}")
        return False


async def deduct_reseller_credit(reseller_id: int, amount: int, details: str = "") -> bool:
    """Deduct credit from reseller's wallet (for key activation)"""
    try:
        conn = await db_pool.get_connection()
        cursor = await conn.execute(
            "SELECT reseller_credit FROM users WHERE telegram_id = ?",
            (reseller_id,)
        )
        row = await cursor.fetchone()
        if not row or row[0] < amount:
            return False

        new_balance = row[0] - amount
        await conn.execute(
            "UPDATE users SET reseller_credit = ? WHERE telegram_id = ?",
            (new_balance, reseller_id)
        )

        # Log transaction
        await conn.execute(
            """INSERT INTO reseller_transactions
               (reseller_id, type, amount, balance_after, details)
               VALUES (?, 'key_activated', ?, ?, ?)""",
            (reseller_id, -amount, new_balance, details)
        )
        await conn.commit()
        logger.info(f"✅ Deducted {amount} credit from reseller {reseller_id} (balance: {new_balance})")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to deduct credit from reseller {reseller_id}: {e}")
        return False


async def get_reseller_credit_price(plan_type: str) -> int:
    """Get the credit cost for a plan type"""
    conn = await db_pool.get_connection()
    cursor = await conn.execute(
        "SELECT credit_cost FROM reseller_credit_prices WHERE plan_type = ?",
        (plan_type,)
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def set_reseller_credit_price(plan_type: str, credit_cost: int) -> bool:
    """Set the credit cost for a plan type (owner action)"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute(
            "INSERT OR REPLACE INTO reseller_credit_prices (plan_type, credit_cost) VALUES (?, ?)",
            (plan_type, credit_cost)
        )
        await conn.commit()
        return True
    except Exception:
        return False


async def get_all_reseller_credit_prices() -> dict:
    """Get all credit prices"""
    conn = await db_pool.get_connection()
    cursor = await conn.execute("SELECT plan_type, credit_cost FROM reseller_credit_prices")
    rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows}


# ==============================================================================
# Credit transfer (جديد — تحويل رصيد)
# ==============================================================================

async def transfer_credit(from_id: int, to_id: int, amount: int, notes: str = "") -> bool:
    """
    Transfer credit between two users (owner→admin, admin→reseller).
    Deducts from sender and adds to receiver. Logs to transaction_log.
    """
    if amount <= 0:
        return False
    try:
        conn = await db_pool.get_connection()

        # Deduct from sender
        cursor = await conn.execute(
            "SELECT reseller_credit FROM users WHERE telegram_id = ?",
            (from_id,)
        )
        row = await cursor.fetchone()
        if not row or row[0] < amount:
            return False

        new_sender = row[0] - amount
        await conn.execute(
            "UPDATE users SET reseller_credit = ? WHERE telegram_id = ?",
            (new_sender, from_id)
        )

        # Add to receiver
        cursor2 = await conn.execute(
            "SELECT reseller_credit FROM users WHERE telegram_id = ?",
            (to_id,)
        )
        row2 = await cursor2.fetchone()
        new_receiver = (row2[0] if row2 else 0) + amount
        await conn.execute(
            "UPDATE users SET reseller_credit = ? WHERE telegram_id = ?",
            (new_receiver, to_id)
        )

        # Log to transaction_log
        await conn.execute(
            """INSERT INTO transaction_log (from_user_id, to_user_id, amount, tx_type, notes)
               VALUES (?, ?, ?, 'credit_transfer', ?)""",
            (from_id, to_id, amount, notes)
        )

        # Also log to reseller_transactions for backward compat
        await conn.execute(
            """INSERT INTO reseller_transactions
               (reseller_id, type, amount, balance_after, details)
               VALUES (?, 'credit_added', ?, ?, ?)""",
            (to_id, amount, new_receiver, notes)
        )

        await conn.commit()
        logger.info(f"✅ Transferred {amount} credit: {from_id} → {to_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to transfer credit {from_id} → {to_id}: {e}")
        return False


async def get_transaction_log(user_id: int, limit: int = 20) -> list:
    """Get recent transactions involving this user (sent or received).
    Reads from BOTH transaction_log and reseller_transactions, merges and sorts."""
    conn = await db_pool.get_connection()

    # 1) transaction_log (transfers between users)
    cursor1 = await conn.execute(
        """SELECT t.id, t.from_user_id, t.to_user_id, t.amount, t.tx_type, t.notes, t.created_at,
                  COALESCE(u1.name, u1.tg_username, CAST(t.from_user_id AS TEXT)) as from_name,
                  COALESCE(u2.name, u2.tg_username, CAST(t.to_user_id AS TEXT)) as to_name
           FROM transaction_log t
           LEFT JOIN users u1 ON t.from_user_id = u1.telegram_id
           LEFT JOIN users u2 ON t.to_user_id = u2.telegram_id
           WHERE t.from_user_id = ? OR t.to_user_id = ?
           ORDER BY t.created_at DESC""",
        (user_id, user_id)
    )
    tx_rows = await cursor1.fetchall()

    # 2) reseller_transactions (credit added/deducted)
    cursor2 = await conn.execute(
        """SELECT r.id, r.reseller_id as from_user_id, r.reseller_id as to_user_id,
                  ABS(r.amount) as amount, r.type, r.details, r.created_at,
                  COALESCE(u.name, u.tg_username, CAST(r.reseller_id AS TEXT)) as from_name,
                  COALESCE(u.name, u.tg_username, CAST(r.reseller_id AS TEXT)) as to_name
           FROM reseller_transactions r
           LEFT JOIN users u ON r.reseller_id = u.telegram_id
           WHERE r.reseller_id = ?
           ORDER BY r.created_at DESC""",
        (user_id,)
    )
    rt_rows = await cursor2.fetchall()

    # 3) Merge: normalize to same format (id, from_id, to_id, amount, tx_type, notes, created_at, from_name, to_name)
    all_txs = []
    for row in tx_rows:
        all_txs.append(row)
    for row in rt_rows:
        all_txs.append(row)

    # Sort by created_at DESC
    all_txs.sort(key=lambda x: x[6] if x[6] else 0, reverse=True)

    return all_txs[:limit]
