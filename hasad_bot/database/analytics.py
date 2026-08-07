#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dashboard stats, user segment targets, per-user report aggregation.
"""
import time
from typing import List, Dict

import aiosqlite
from loguru import logger

from .pool import db_pool


# ==============================================================================
# Per-user stats & reports
# ==============================================================================

async def get_user_total_stats(uid: int) -> Dict[str, int]:
    """استرجاع إجمالي إحصائيات المستخدم من جدول users وجدول solved_questions"""
    try:
        conn = await db_pool.get_connection()

        async with conn.execute("""
            SELECT
                total_hw_solved as total_homeworks
            FROM users
            WHERE telegram_id = ?
        """, (uid,)) as c:
            row = await c.fetchone()
            total_homeworks = row['total_homeworks'] or 0 if row else 0

        async with conn.execute("""
            SELECT
                COUNT(*) as total_questions,
                SUM(CASE WHEN source != 'db' THEN 1 ELSE 0 END) as ai_solved
            FROM solved_questions
            WHERE user_id = ?
        """, (uid,)) as c:
            row = await c.fetchone()
            total_questions = row['total_questions'] or 0 if row else 0
            ai_solved = row['ai_solved'] or 0 if row else 0

        async with conn.execute("""
            SELECT
                COALESCE(SUM(total_questions), 0) as sum_questions,
                COALESCE(SUM(correct_answers), 0) as sum_correct,
                COALESCE(SUM(wrong_answers), 0) as sum_wrong
            FROM homework_sessions
            WHERE user_id = ?
        """, (uid,)) as c:
            row = await c.fetchone()
            sum_questions = row['sum_questions'] or 0 if row else 0
            sum_correct = row['sum_correct'] or 0 if row else 0
            sum_wrong = row['sum_wrong'] or 0 if row else 0

        final_questions = max(total_questions, sum_questions)
        final_correct = max(ai_solved, sum_correct)
        final_wrong = sum_wrong

        return {
            'total_homeworks': total_homeworks,
            'total_questions': final_questions,
            'total_correct': final_correct,
            'total_wrong': final_wrong
        }
    except Exception as e:
        logger.error(f"Error getting user total stats: {e}")

    return {'total_homeworks': 0, 'total_questions': 0, 'total_correct': 0, 'total_wrong': 0}


async def get_user_reports_days(uid: int) -> List[Dict]:
    """جلب قائمة الأيام التي حل فيها المستخدم واجبات"""
    try:
        conn = await db_pool.get_connection()

        reports = []
        async with conn.execute("""
            SELECT
                DATE(end_time) as report_date,
                COUNT(*) as total_homeworks,
                SUM(total_questions) as total_questions,
                SUM(correct_answers) as total_correct,
                SUM(wrong_answers) as total_wrong
            FROM homework_sessions
            WHERE user_id = ? AND status = 'completed'
            GROUP BY DATE(end_time)
            ORDER BY report_date DESC
        """, (uid,)) as c:
            async for row in c:
                reports.append(dict(row))

        return reports
    except Exception as e:
        logger.error(f"Error getting user reports days: {e}")
        return []


async def get_user_report_by_date(uid: int, date_str: str) -> List[Dict]:
    """جلب كل واجبات المستخدم في يوم محدد"""
    try:
        conn = await db_pool.get_connection()

        reports = []
        async with conn.execute("""
            SELECT
                id,
                subject,
                total_questions,
                correct_answers,
                wrong_answers,
                end_time
            FROM homework_sessions
            WHERE user_id = ? AND DATE(end_time) = ? AND status = 'completed'
            ORDER BY end_time DESC
        """, (uid, date_str)) as c:
            async for row in c:
                reports.append(dict(row))

        return reports
    except Exception as e:
        logger.error(f"Error getting user report by date: {e}")
        return []


# ==============================================================================
# Dashboard & targets
# ==============================================================================

async def get_dashboard_stats():
    """قراءة الإحصائيات من جدول dashboard_stats"""
    try:
        conn = await db_pool.get_connection()

        async with conn.execute("SELECT stat_name, stat_value FROM dashboard_stats") as c:
            rows = await c.fetchall()

        stats = {}
        for row in rows:
            value = row[1]
            if value.isdigit():
                stats[row[0]] = int(value)
            elif value.replace('.', '').isdigit():
                stats[row[0]] = float(value)
            else:
                stats[row[0]] = value

        return stats

    except Exception as e:
        logger.error(f"Failed to get dashboard stats: {e}")
        return {}


async def get_users_count_by_target(target: str) -> int:
    """حساب عدد المستخدمين حسب الفئة"""
    conn = await db_pool.get_connection()
    now_ts = time.time()

    if target == "all":
        async with conn.execute("SELECT COUNT(*) FROM users") as c:
            row = await c.fetchone()
            return row[0] if row else 0
    elif target == "subscribed":
        async with conn.execute("""
            SELECT COUNT(*) FROM users
            WHERE expiry_ts > ? OR telegram_id IN (
                SELECT user_id FROM user_subscriptions
                WHERE is_active = 1 AND end_date > ?
            )
        """, (now_ts, now_ts)) as c:
            row = await c.fetchone()
            return row[0] if row else 0
    elif target == "not_subscribed":
        async with conn.execute("""
            SELECT COUNT(*) FROM users
            WHERE (expiry_ts IS NULL OR expiry_ts <= ?)
            AND telegram_id NOT IN (
                SELECT user_id FROM user_subscriptions
                WHERE is_active = 1 AND end_date > ?
            )
        """, (now_ts, now_ts)) as c:
            row = await c.fetchone()
            return row[0] if row else 0
    elif target == "linked":
        async with conn.execute("""
            SELECT COUNT(*) FROM users
            WHERE dars360_user IS NOT NULL AND dars360_user != ''
        """) as c:
            row = await c.fetchone()
            return row[0] if row else 0
    elif target == "not_linked":
        async with conn.execute("""
            SELECT COUNT(*) FROM users
            WHERE dars360_user IS NULL OR dars360_user = ''
        """) as c:
            row = await c.fetchone()
            return row[0] if row else 0
    return 0


async def get_users_by_target(target: str) -> List[int]:
    """جلب قائمة معرفات المستخدمين حسب الفئة"""
    conn = await db_pool.get_connection()
    now_ts = time.time()

    if target == "all":
        async with conn.execute("SELECT telegram_id FROM users") as c:
            return [row[0] for row in await c.fetchall()]
    elif target == "subscribed":
        async with conn.execute("""
            SELECT telegram_id FROM users
            WHERE expiry_ts > ? OR telegram_id IN (
                SELECT user_id FROM user_subscriptions
                WHERE is_active = 1 AND end_date > ?
            )
        """, (now_ts, now_ts)) as c:
            return [row[0] for row in await c.fetchall()]
    elif target == "not_subscribed":
        async with conn.execute("""
            SELECT telegram_id FROM users
            WHERE (expiry_ts IS NULL OR expiry_ts <= ?)
            AND telegram_id NOT IN (
                SELECT user_id FROM user_subscriptions
                WHERE is_active = 1 AND end_date > ?
            )
        """, (now_ts, now_ts)) as c:
            return [row[0] for row in await c.fetchall()]
    elif target == "linked":
        async with conn.execute("""
            SELECT telegram_id FROM users
            WHERE dars360_user IS NOT NULL AND dars360_user != ''
        """) as c:
            return [row[0] for row in await c.fetchall()]
    elif target == "not_linked":
        async with conn.execute("""
            SELECT telegram_id FROM users
            WHERE dars360_user IS NULL OR dars360_user = ''
        """) as c:
            return [row[0] for row in await c.fetchall()]
    return []


def get_target_name(target: str) -> str:
    """الحصول على اسم الفئة بالعربية"""
    names = {
        "all": "🌍 الكل",
        "subscribed": "💎 المشتركين",
        "not_subscribed": "❌ غير المشتركين",
        "linked": "🔗 مرتبط المنصة",
        "not_linked": "🚫 غير مرتبط المنصة"
    }
    return names.get(target, target)


async def collect_and_save_dashboard_stats():
    """جمع الإحصائيات من الجداول وحفظها في dashboard_stats"""
    try:
        conn = await db_pool.get_connection()
        now = time.time()
        today_start = now - (now % 86400)
        five_min_ago = now - 300

        # 1. من جدول users
        async with conn.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0] or 0

        async with conn.execute("SELECT COUNT(*) FROM users WHERE last_active > ?", (five_min_ago,)) as c:
            active_now = (await c.fetchone())[0] or 0

        async with conn.execute("SELECT COUNT(*) FROM users WHERE last_active > ?", (today_start,)) as c:
            active_today = (await c.fetchone())[0] or 0

        async with conn.execute("SELECT COUNT(*) FROM users WHERE expiry_ts > ?", (now,)) as c:
            subscribers = (await c.fetchone())[0] or 0

        async with conn.execute("""
            SELECT COUNT(*) FROM users
            WHERE (free_attempts = 0 OR free_attempts IS NULL)
            AND (expiry_ts IS NULL OR expiry_ts < ?)
        """, (now,)) as c:
            finished_free = (await c.fetchone())[0] or 0

        async with conn.execute("SELECT SUM(free_attempts) FROM users WHERE free_attempts > 0") as c:
            remaining_free = (await c.fetchone())[0] or 0

        async with conn.execute("SELECT SUM(total_hw_solved) FROM users") as c:
            total_hw = (await c.fetchone())[0] or 0

        # 2. من جدول homework_sessions
        async with conn.execute("""
            SELECT
                SUM(solved_questions) as total_solved,
                SUM(correct_answers) as total_correct,
                SUM(wrong_answers) as total_wrong
            FROM homework_sessions
            WHERE status = 'completed'
        """) as c:
            row = await c.fetchone()
            total_questions_solved = row[0] or 0 if row else 0
            total_correct = row[1] or 0 if row else 0
            total_wrong = row[2] or 0 if row else 0

        # 3. من جدول solved_questions
        try:
            async with conn.execute("SELECT COUNT(*) FROM solved_questions") as c:
                total_questions = (await c.fetchone())[0] or 0

            async with conn.execute("SELECT COUNT(*) FROM solved_questions WHERE source = 'db'") as c:
                db_hits = (await c.fetchone())[0] or 0

            async with conn.execute("SELECT COUNT(*) FROM solved_questions WHERE source = 'groq'") as c:
                groq = (await c.fetchone())[0] or 0

            async with conn.execute("SELECT COUNT(*) FROM solved_questions WHERE source = 'gemini'") as c:
                gemini = (await c.fetchone())[0] or 0

            async with conn.execute("SELECT COUNT(*) FROM solved_questions WHERE source = 'random'") as c:
                random_count = (await c.fetchone())[0] or 0
        except:
            total_questions = 0
            db_hits = 0
            groq = 0
            gemini = 0
            random_count = 0

        # 4. من جدول event_logs (الأخطاء)
        async with conn.execute("SELECT COUNT(*) FROM event_logs WHERE success = 0") as c:
            total_errors = (await c.fetchone())[0] or 0

        # 5. مقاييس النظام
        cpu = 0
        memory = 0
        try:
            import psutil
            cpu = psutil.cpu_percent()
            memory = psutil.virtual_memory().percent
        except:
            pass

        # 6. حفظ كل الإحصائيات في جدول dashboard_stats
        stats_data = {
            'total_users': total_users,
            'active_now': active_now,
            'active_today': active_today,
            'subscribers': subscribers,
            'finished_free': finished_free,
            'remaining_free': remaining_free,
            'total_hw': total_hw,
            'total_questions_solved': total_questions_solved,
            'total_questions': total_questions,
            'total_correct': total_correct,
            'total_wrong': total_wrong,
            'db_hits': db_hits,
            'groq': groq,
            'gemini': gemini,
            'random': random_count,
            'total_errors': total_errors,
            'cpu': cpu,
            'memory': memory
        }

        for name, value in stats_data.items():
            await conn.execute("""
                INSERT INTO dashboard_stats (stat_name, stat_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(stat_name) DO UPDATE SET
                    stat_value = excluded.stat_value,
                    updated_at = excluded.updated_at
            """, (name, str(value), now))

        await conn.commit()

        return stats_data

    except Exception as e:
        logger.error(f"Failed to collect dashboard stats: {e}")
        return {}
