#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database lifecycle: initialization, payment table, and WAL cleanup.
"""
import os
import sqlite3
from loguru import logger

from hasad_bot.config import config
from hasad_bot.utils import now_hijri, admin_trace
from .pool import db_pool


async def ensure_payment_requests_table():
    """التأكد من وجود جدول payment_requests"""
    try:
        conn = await db_pool.get_connection()
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                plan_id TEXT,
                plan_name TEXT,
                price REAL,
                payment_method TEXT,
                payment_method_name TEXT,
                note TEXT,
                status TEXT DEFAULT 'pending',
                created_at REAL,
                processed_at REAL,
                processed_by INTEGER
            )
        """)
        await conn.commit()
        logger.info("✅ Payment requests table ensured")
    except Exception as e:
        logger.error(f"Error creating payment_requests table: {e}")


async def db_init():
    """Initialize database"""
    await db_pool.initialize()
    await ensure_payment_requests_table()
    from .subscriptions import db_init_plans
    await db_init_plans()
    await _seed_reseller_credit_prices()
    from .payment_settings import ensure_payment_settings
    await ensure_payment_settings()
    logger.info(f"✅ Database initialized: {config.db_file}")


async def _seed_reseller_credit_prices():
    """Seed default credit prices for reseller plans (owner can change later)."""
    try:
        conn = await db_pool.get_connection()
        defaults = {
            'weekly': 10,
            'monthly': 20,
            'semester': 40,
        }
        for plan_type, cost in defaults.items():
            await conn.execute(
                "INSERT OR IGNORE INTO reseller_credit_prices (plan_type, credit_cost) VALUES (?, ?)",
                (plan_type, cost)
            )
        await conn.commit()
        logger.info("✅ Reseller credit prices seeded")
    except Exception as e:
        logger.warning(f"⚠️ Reseller credit prices seed skip: {e}")


def auto_cleanup_db(db_path: str = None):
    """
    وظيفة احترافية لدمج ملفات WAL و SHM تلقائياً داخل ملف القاعدة الأساسي.
    تستخدم لضمان أعلى أداء وتقليل حجم المجلد.
    """
    if db_path is None:
        db_path = str(config.knowledge_db)

    hijri_date = now_hijri()

    if not os.path.exists(db_path):
        print(f"[{hijri_date}] [CRITICAL] [DATABASE] >> فشل الوصول للقاعدة: المسار غير صحيح!")
        return

    try:
        print(f"[{hijri_date}] [INFO] [DATABASE] >> بدء عملية التنظيف الذاتي (Checkpointing)...")

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.execute("PRAGMA optimize;")
        conn.close()

        size_mb = os.path.getsize(db_path) / (1024 * 1024)
        print(f"[{hijri_date}] [SUCCESS] [DATABASE] >> تم الدمج بنجاح. الحجم الحالي للقاعدة: {size_mb:.2f} MB")

        admin_trace("DB_CLEANUP", f"WAL checkpointed, size: {size_mb:.2f} MB")

    except sqlite3.Error as e:
        print(f"[{hijri_date}] [ERROR] [DATABASE] >> فشل الدمج بسبب قفل القاعدة: {e}")
    except Exception as e:
        print(f"[{hijri_date}] [ERROR] [SYSTEM] >> خطأ غير متوقع: {e}")
