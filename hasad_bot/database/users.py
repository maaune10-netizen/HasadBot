#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
User CRUD, permission checks, message logging, CV storage, rank/stats maintenance.
"""
import time
from typing import Optional, Dict, List

import aiosqlite
from loguru import logger

from hasad_bot.config import config
from hasad_bot.utils import admin_trace
from hasad_bot.datetime_utils import now_timestamp
from .pool import db_pool


# ==============================================================================
# User CRUD
# ==============================================================================

async def db_get_user(uid: int) -> Optional[Dict]:
    """Get user by ID"""
    conn = await db_pool.get_connection()
    conn.row_factory = aiosqlite.Row
    async with conn.execute("SELECT * FROM users WHERE telegram_id=?", (uid,)) as c:
        r = await c.fetchone()
        return dict(r) if r else None


async def db_get_user_by_platform(platform_user: str) -> Optional[Dict]:
    """Get user by platform username"""
    conn = await db_pool.get_connection()
    conn.row_factory = aiosqlite.Row
    async with conn.execute("SELECT * FROM users WHERE dars360_user=?", (platform_user,)) as c:
        r = await c.fetchone()
        return dict(r) if r else None


async def db_set_user(uid: int, **fields):
    """Insert or update user"""
    conn = await db_pool.get_connection()
    existing = await db_get_user(uid)

    if not existing:
        cols = ["telegram_id"] + list(fields.keys())
        vals = [uid] + list(fields.values())
        ph = ",".join("?" * len(cols))
        await conn.execute(f"INSERT INTO users ({','.join(cols)}) VALUES ({ph})", vals)
    elif fields:
        clause = ", ".join(f"{k}=?" for k in fields)
        await conn.execute(f"UPDATE users SET {clause} WHERE telegram_id=?", list(fields.values()) + [uid])
    await conn.commit()


async def db_all_users() -> List[Dict]:
    """Get all users"""
    conn = await db_pool.get_connection()
    conn.row_factory = aiosqlite.Row
    async with conn.execute("SELECT * FROM users ORDER BY created_at DESC") as c:
        return [dict(r) for r in await c.fetchall()]


async def db_get_vip_users() -> List[Dict]:
    """Get VIP users"""
    conn = await db_pool.get_connection()
    now_ts = now_timestamp()

    conn.row_factory = aiosqlite.Row
    async with conn.execute(
        "SELECT * FROM users WHERE expiry_ts > ? AND radar_enabled = 1",
        (now_ts,)
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def db_delete_user(uid: int):
    """حذف مستخدم مع جميع سجلاته المرتبطة (بالترتيب الصحيح)"""
    conn = await db_pool.get_connection()

    # 1. رسائل المستخدم
    await conn.execute("DELETE FROM all_messages WHERE user_id = ?", (uid,))
    # 2. سجل الأحداث
    await conn.execute("DELETE FROM event_logs WHERE user_id = ?", (uid,))
    # 3. سجل اللوجات القديمة
    await conn.execute("DELETE FROM logs WHERE telegram_id = ?", (uid,))
    # 4. اشتراكات المستخدم
    await conn.execute("DELETE FROM user_subscriptions WHERE user_id = ?", (uid,))
    # 5. جلسات حل الواجبات
    await conn.execute("DELETE FROM homework_sessions WHERE user_id = ?", (uid,))
    # 6. إشعارات المستخدم
    await conn.execute("DELETE FROM notifications WHERE user_id = ?", (uid,))
    # 7. تذاكر الدعم
    await conn.execute("DELETE FROM support_tickets WHERE user_id = ?", (uid,))
    # 8. طلبات الدفع
    await conn.execute("DELETE FROM payment_requests WHERE user_id = ?", (uid,))
    # 9. سجل تسجيل الدخول
    await conn.execute("DELETE FROM login_logs WHERE user_id = ?", (uid,))
    # 10. طلبات فك القفل
    await conn.execute("DELETE FROM unlock_requests WHERE user_id = ?", (uid,))
    # ✅ أخيراً حذف المستخدم نفسه
    await conn.execute("DELETE FROM users WHERE telegram_id = ?", (uid,))
    await conn.commit()

    logger.info(f"✅ User {uid} and all related records deleted")


async def update_user_last_active(uid: int):
    """تحديث آخر نشاط للمستخدم - نسخة آمنة"""
    try:
        conn = await db_pool.get_connection()

        async with conn.execute("PRAGMA table_info(users)") as c:
            columns = await c.fetchall()
            column_names = [col[1] for col in columns]

        if 'last_active' in column_names:
            await conn.execute(
                "UPDATE users SET last_active = ? WHERE telegram_id = ?",
                (time.time(), uid)
            )
            await conn.commit()
        else:
            try:
                await conn.execute("ALTER TABLE users ADD COLUMN last_active REAL DEFAULT 0")
                await conn.commit()
                await conn.execute(
                    "UPDATE users SET last_active = ? WHERE telegram_id = ?",
                    (time.time(), uid)
                )
                await conn.commit()
                logger.info("✅ تم إضافة عمود last_active وتحديثه")
            except Exception as e:
                logger.error(f"فشل إضافة عمود last_active: {e}")

    except Exception as e:
        logger.error(f"Error in update_user_last_active: {e}")


# ==============================================================================
# Permission checks
# ==============================================================================

async def is_admin(uid: int) -> bool:
    """Check if user is admin"""
    if uid == config.admin_id:
        return True
    u = await db_get_user(uid)
    return bool(u and u.get("is_admin", 0) >= 1)


async def is_subscribed(uid: int) -> bool:
    """Check if user has active subscription"""
    if uid == config.admin_id:
        return True
    u = await db_get_user(uid)
    if not u:
        return False
    return time.time() < (u.get("expiry_ts") or 0)


async def is_vip(uid: int) -> bool:
    """Check if user is VIP"""
    return await is_subscribed(uid)


async def is_teacher(uid: int) -> bool:
    """التحقق إذا كان المستخدم أستاذ (ليس طالباً)"""
    user = await db_get_user(uid)
    if not user:
        return False

    username = user.get('dars360_user', '')
    if not username:
        return False

    is_student = username.isdigit() and len(username) in [10, 11, 9]
    return not is_student


async def is_reseller(uid: int) -> bool:
    """Check if user is a reseller (or admin/owner — they have reseller access too)"""
    if uid == config.admin_id:
        return True
    u = await db_get_user(uid)
    if not u:
        return False
    return u.get("role") == "reseller" or u.get("is_admin", 0) >= 1


async def promote_to_reseller(uid: int) -> bool:
    """Promote a user to reseller role"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute(
            "UPDATE users SET role = 'reseller' WHERE telegram_id = ?",
            (uid,)
        )
        await conn.commit()
        return True
    except Exception:
        return False


async def demote_from_reseller(uid: int) -> bool:
    """Remove reseller role from user (owner only)"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute(
            "UPDATE users SET role = '' WHERE telegram_id = ? AND telegram_id != ?",
            (uid, config.admin_id)
        )
        await conn.commit()
        return True
    except Exception:
        return False


async def demote_from_admin(uid: int) -> bool:
    """Remove admin role from user (owner only) — resets role, is_admin, parent_admin_id"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute(
            """UPDATE users SET role = '', is_admin = 0, parent_admin_id = NULL
               WHERE telegram_id = ? AND telegram_id != ?""",
            (uid, config.admin_id)
        )
        await conn.commit()
        return True
    except Exception:
        return False


async def remove_customer_from_reseller(customer_id: int) -> bool:
    """Remove customer from reseller's list (set referred_by_reseller to NULL)"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute(
            "UPDATE users SET referred_by_reseller = NULL WHERE telegram_id = ?",
            (customer_id,)
        )
        await conn.commit()
        return True
    except Exception:
        return False


async def get_reseller_customers(reseller_id: int) -> list:
    """Get all customers who joined via this reseller's link with subscription info"""
    conn = await db_pool.get_connection()
    cursor = await conn.execute(
        """SELECT u.telegram_id, u.name, u.real_name, u.tg_username, u.created_at,
                  u.expiry_ts, u.free_attempts,
                  us.plan_id, us.end_date, us.max_homeworks, us.homeworks_used
           FROM users u
           LEFT JOIN user_subscriptions us ON u.telegram_id = us.user_id AND us.is_active = 1
           WHERE u.referred_by_reseller = ?
           ORDER BY u.created_at DESC""",
        (reseller_id,)
    )
    return await cursor.fetchall()


async def get_reseller_stats(reseller_id: int) -> dict:
    """Get reseller statistics"""
    conn = await db_pool.get_connection()

    # Total customers
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM users WHERE referred_by_reseller = ?",
        (reseller_id,)
    )
    total_customers = (await cursor.fetchone())[0]

    # Active subscriptions among customers
    now = time.time()
    cursor = await conn.execute(
        """SELECT COUNT(*) FROM users
           WHERE referred_by_reseller = ? AND expiry_ts > ?""",
        (reseller_id, now)
    )
    active_customers = (await cursor.fetchone())[0]

    # Credit spent (total deductions)
    cursor = await conn.execute(
        """SELECT COALESCE(SUM(ABS(amount)), 0)
           FROM reseller_transactions
           WHERE reseller_id = ? AND type = 'key_activated'""",
        (reseller_id,)
    )
    credit_spent = (await cursor.fetchone())[0]

    return {
        'total_customers': total_customers,
        'active_customers': active_customers,
        'credit_spent': credit_spent,
    }


# ==============================================================================
# Admin tree management (جديد — شجرة الموزعين)
# ==============================================================================

async def promote_to_admin(uid: int, parent_admin_id: int = None) -> bool:
    """Promote a user to admin role (main reseller / رئيس موردين)"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute(
            "UPDATE users SET role = 'admin', is_admin = 1, parent_admin_id = ? WHERE telegram_id = ?",
            (parent_admin_id, uid)
        )
        await conn.commit()
        return True
    except Exception:
        return False


async def get_admin_sub_resellers(admin_id: int) -> list:
    """Get all sub-resellers created by a specific admin"""
    conn = await db_pool.get_connection()
    cursor = await conn.execute(
        """SELECT u.telegram_id, u.name, u.tg_username, u.reseller_credit,
                  u.created_at,
                  (SELECT COUNT(*) FROM users WHERE referred_by_reseller = u.telegram_id) as customer_count
           FROM users u
           WHERE u.parent_admin_id = ? AND u.role = 'reseller'
           ORDER BY u.created_at DESC""",
        (admin_id,)
    )
    return await cursor.fetchall()


async def get_admin_customers(admin_id: int) -> list:
    """Get all customers under an admin (direct + sub-reseller customers)"""
    conn = await db_pool.get_connection()
    cursor = await conn.execute(
        """SELECT u.telegram_id, u.name, u.tg_username, u.expiry_ts, u.free_attempts,
                  u.referred_by_reseller,
                  us.plan_id, us.end_date, us.max_homeworks, us.homeworks_used
           FROM users u
           LEFT JOIN user_subscriptions us ON u.telegram_id = us.user_id AND us.is_active = 1
           WHERE u.referred_by_reseller IN (
               SELECT telegram_id FROM users WHERE parent_admin_id = ?
           )
           ORDER BY u.created_at DESC""",
        (admin_id,)
    )
    return await cursor.fetchall()


async def create_sub_reseller(uid: int, admin_id: int) -> bool:
    """Create a sub-reseller under an admin (sets role='reseller' + parent_admin_id)"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute(
            "UPDATE users SET role = 'reseller', parent_admin_id = ? WHERE telegram_id = ?",
            (admin_id, uid)
        )
        await conn.commit()
        return True
    except Exception:
        return False


async def get_all_full_admins() -> list:
    """Get all full admins (role='admin' OR is_admin >= 1, excluding owner)"""
    conn = await db_pool.get_connection()
    cursor = await conn.execute(
        """SELECT telegram_id, name, tg_username, reseller_credit, created_at
           FROM users
           WHERE (role = 'admin' OR is_admin >= 1)
             AND telegram_id != ?
           ORDER BY created_at DESC""",
        (config.admin_id,)
    )
    return await cursor.fetchall()


# ==============================================================================
# Rank, CV, log, message logging
# ==============================================================================

async def db_update_rank(uid: int, total_solved: int):
    """تحديث رتبة المستخدم"""
    rank_title = "🥉 طالب جديد"
    if total_solved >= 20:
        rank_title = "🥇 أسطورة المدرسة"
    elif total_solved >= 5:
        rank_title = "🥈 دافور"

    await db_set_user(uid, total_hw_solved=total_solved, rank_title=rank_title)


async def db_save_cv(uid: int, platform_user: str, cv_data: dict):
    """Save student CV data"""
    conn = await db_pool.get_harvest_connection()
    await conn.execute("""
        INSERT INTO student_cvs_v2 (
            platform_user, telegram_id, local_name, latin_name, identity_no,
            phone, nationality, stage, grade, student_class, profile_pic, scraped_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(platform_user) DO UPDATE SET
            telegram_id=excluded.telegram_id, local_name=excluded.local_name,
            latin_name=excluded.latin_name, identity_no=excluded.identity_no,
            phone=excluded.phone, nationality=excluded.nationality,
            stage=excluded.stage, grade=excluded.grade, student_class=excluded.student_class,
            profile_pic=excluded.profile_pic, scraped_at=excluded.scraped_at
    """, (
        platform_user, uid,
        cv_data.get('local_name', ''), cv_data.get('latin_name', ''),
        cv_data.get('identity_no', ''), cv_data.get('phone', ''),
        cv_data.get('nationality', ''), cv_data.get('stage', ''),
        cv_data.get('grade', ''), cv_data.get('student_class', ''),
        cv_data.get('pic', ''), time.time()
    ))
    await conn.commit()


async def db_log(uid: int, action: str, subject: str = "", detail: str = "", source: str = "SYSTEM"):
    """Add log entry to logs table"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute(
            "INSERT INTO logs(telegram_id, action, subject, detail, source, created_at) VALUES(?,?,?,?,?,?)",
            (uid, action, subject, detail[:1000], source, time.time())
        )
        await conn.commit()
        logger.info(f"📝 Log entry: {action} for user {uid}")
    except Exception as e:
        logger.error(f"Failed to add log entry: {e}")


async def log_user_message(user_id: int, user_name: str, message_text: str,
                           message_type: str = "text", chat_id: int = None,
                           message_id: int = None, is_response: bool = False,
                           response_to: str = ""):
    """تسجيل رسالة المستخدم في قاعدة البيانات"""
    try:
        conn = await db_pool.get_connection()

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS all_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                message_text TEXT,
                message_type TEXT DEFAULT 'text',
                is_response BOOLEAN DEFAULT 0,
                response_to TEXT,
                chat_id INTEGER,
                message_id INTEGER,
                created_at REAL NOT NULL
            )
        """)

        await conn.execute("""
            INSERT INTO all_messages
            (user_id, user_name, message_text, message_type, is_response,
             response_to, chat_id, message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, user_name, message_text[:1000], message_type,
              1 if is_response else 0, response_to, chat_id, message_id, time.time()))

        await conn.commit()
        logger.info(f"📝 Message logged: user={user_id}, type={message_type}")

    except Exception as e:
        logger.error(f"Error logging user message: {e}")


# ==============================================================================
# Comprehensive stats maintenance
# ==============================================================================

async def update_user_stats_comprehensive(user_id: int):
    """تحديث جميع إحصائيات المستخدم في جدول user_stats"""
    try:
        conn = await db_pool.get_connection()
        now = time.time()

        async with conn.execute("SELECT total_hw_solved FROM users WHERE telegram_id = ?", (user_id,)) as c:
            user_row = await c.fetchone()
            total_homeworks = user_row[0] if user_row else 0

        async with conn.execute("""
            SELECT COALESCE(SUM(total_questions), 0) FROM homework_sessions
            WHERE user_id = ? AND status = 'completed'
        """, (user_id,)) as c:
            total_questions = (await c.fetchone())[0] or 0

        async with conn.execute("""
            SELECT
                (SELECT COUNT(*) FROM login_logs WHERE user_id = ?) as total_logins,
                (SELECT SUM(wrong_answers) FROM homework_sessions WHERE user_id = ? AND status = 'completed') as total_errors,
                (SELECT AVG(end_time - start_time) FROM homework_sessions WHERE user_id = ? AND status = 'completed' AND end_time > start_time) as avg_response_time,
                (SELECT MAX(end_time) FROM homework_sessions WHERE user_id = ? AND status = 'completed') as last_active,
                (SELECT COUNT(*) FROM solved_questions WHERE user_id = ? AND source IN ('groq', 'gemini')) as total_api_calls,
                (SELECT COUNT(*) FROM solved_questions WHERE user_id = ? AND source = 'groq') as groq_calls,
                (SELECT COUNT(*) FROM solved_questions WHERE user_id = ? AND source = 'gemini') as gemini_calls,
                (SELECT COUNT(*) FROM solved_questions WHERE user_id = ? AND source = 'db') as db_hits
        """, (user_id, user_id, user_id, user_id, user_id, user_id, user_id, user_id)) as c:
            row = await c.fetchone()

        if row:
            await conn.execute("""
                INSERT OR REPLACE INTO user_stats
                (user_id, total_logins, total_homeworks, total_questions, total_errors,
                 avg_response_time, last_active, total_api_calls, groq_calls, gemini_calls, db_hits)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id,
                  row[0] or 0,
                  total_homeworks,
                  total_questions,
                  row[1] or 0,
                  row[2] or 0,
                  row[3] or now,
                  row[4] or 0,
                  row[5] or 0,
                  row[6] or 0,
                  row[7] or 0))

        await conn.commit()

    except Exception as e:
        logger.error(f"Error updating comprehensive user stats: {e}")


async def populate_all_user_stats():
    """تعبئة إحصائيات جميع المستخدمين الحاليين في جدول user_stats"""
    print("🚀 بدء تعبئة إحصائيات المستخدمين...")

    try:
        conn = await db_pool.get_connection()

        async with conn.execute("SELECT telegram_id FROM users") as c:
            users = await c.fetchall()

        if not users:
            print("📭 لا يوجد مستخدمين في قاعدة البيانات")
            return

        count = 0
        for user in users:
            uid = user[0]

            async with conn.execute("""
                SELECT
                    (SELECT COUNT(*) FROM login_logs WHERE user_id = ?) as total_logins,
                    (SELECT COUNT(*) FROM homework_sessions WHERE user_id = ? AND status = 'completed') as total_homeworks,
                    (SELECT COUNT(*) FROM solved_questions WHERE user_id = ?) as total_questions,
                    (SELECT COUNT(*) FROM event_logs WHERE user_id = ? AND success = 0) as total_errors,
                    (SELECT AVG(response_time) FROM event_logs WHERE user_id = ? AND response_time > 0) as avg_response_time,
                    (SELECT MAX(created_at) FROM event_logs WHERE user_id = ?) as last_active,
                    (SELECT COUNT(*) FROM solved_questions WHERE user_id = ? AND source IN ('groq', 'gemini')) as total_api_calls,
                    (SELECT COUNT(*) FROM solved_questions WHERE user_id = ? AND source = 'groq') as groq_calls,
                    (SELECT COUNT(*) FROM solved_questions WHERE user_id = ? AND source = 'gemini') as gemini_calls,
                    (SELECT COUNT(*) FROM solved_questions WHERE user_id = ? AND source = 'db') as db_hits
            """, (uid, uid, uid, uid, uid, uid, uid, uid, uid, uid)) as c2:
                row = await c2.fetchone()

            if row:
                now = time.time()
                await conn.execute("""
                    INSERT OR REPLACE INTO user_stats
                    (user_id, total_logins, total_homeworks, total_questions, total_errors,
                     avg_response_time, last_active, total_api_calls, groq_calls, gemini_calls, db_hits)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (uid,
                      row[0] or 0,
                      row[1] or 0,
                      row[2] or 0,
                      row[3] or 0,
                      row[4] or 0,
                      row[5] or now,
                      row[6] or 0,
                      row[7] or 0,
                      row[8] or 0,
                      row[9] or 0))

            count += 1
            if count % 10 == 0:
                print(f"✅ تم تحديث {count} مستخدم...")

        await conn.commit()
        print(f"✅ تم تحديث إحصائيات {count} مستخدم بنجاح")

    except Exception as e:
        print(f"❌ خطأ في تعبئة الإحصائيات: {e}")
