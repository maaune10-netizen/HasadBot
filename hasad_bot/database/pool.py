#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database connection pool for HASAD Bot.
Owns the schema definitions, connection management, and pool lifecycle.
"""
import asyncio
import sqlite3
from typing import Optional, List

import aiosqlite
from loguru import logger

from hasad_bot.config import config


class DatabasePool:
    """Database connection pool using aiosqlite with multiple concurrent connections"""

    _instance = None
    _lock = asyncio.Lock()

    POOL_SIZE = 5
    POOL_MAX_OVERFLOW = 3

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.db_path = config.db_file
        self.harvest_path = config.harvest_db
        self._connection: Optional[aiosqlite.Connection] = None
        self._harvest_connection: Optional[aiosqlite.Connection] = None
        self._knowledge_connection: Optional[sqlite3.Connection] = None
        self._knowledge_connection_async: Optional[aiosqlite.Connection] = None

        self._connection_pool: List[aiosqlite.Connection] = []
        self._pool_lock = asyncio.Lock()
        self._pool_semaphore = asyncio.Semaphore(self.POOL_SIZE + self.POOL_MAX_OVERFLOW)

        self._init_task = None

    async def initialize(self):
        """Initialize database connections and create tables"""
        async with self._lock:
            if self._connection is not None:
                return

            logger.info("📦 Initializing database connections...")

            self._connection = await aiosqlite.connect(self.db_path)
            await self._connection.execute("PRAGMA journal_mode=WAL")
            await self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.row_factory = aiosqlite.Row
            await self._create_tables()

            self._harvest_connection = await aiosqlite.connect(self.harvest_path)
            await self._harvest_connection.execute("PRAGMA journal_mode=WAL")
            self._harvest_connection.row_factory = aiosqlite.Row
            await self._create_harvest_tables()

            await self._create_indexes()

            logger.success(f"✅ Database initialized: {self.db_path}")

    async def _create_tables(self):
        """Create main database tables with new fields for gamification and radar"""
        await self._connection.executescript("""
         -- ========== الجداول الموجودة ==========
            CREATE TABLE IF NOT EXISTS users (
                telegram_id   INTEGER PRIMARY KEY,
                name          TEXT    DEFAULT '',
                tg_username   TEXT    DEFAULT '',
                dars360_user  TEXT    DEFAULT '',
                dars360_pass  TEXT    DEFAULT '',
                free_exam_attempts_used INTEGER DEFAULT 0,
                expiry_ts     REAL    DEFAULT 0,
                exam_attempts_used INTEGER DEFAULT 0,
                expiry_hijri  TEXT    DEFAULT '',
                platform_url TEXT DEFAULT '',
                platform_id TEXT DEFAULT '',
                locked_to     INTEGER DEFAULT NULL,
                referral_used_count INTEGER DEFAULT 0,
                lock_request  INTEGER DEFAULT 0,
                lock_request_date REAL DEFAULT 0,
                is_admin      INTEGER DEFAULT 0,
                joined_hijri  TEXT    DEFAULT '',
                created_at    REAL    DEFAULT (strftime('%s','now')),
                free_attempts INTEGER DEFAULT 5,
                referred_by   INTEGER DEFAULT NULL,
                referral_count INTEGER DEFAULT 0,
                real_name     TEXT    DEFAULT '',
                branch        TEXT    DEFAULT '',
                role          TEXT    DEFAULT '',
                phone         TEXT    DEFAULT '',
                profile_pic   TEXT    DEFAULT '',
                total_hw_solved INTEGER DEFAULT 0,
                rank_title    TEXT    DEFAULT '🥉 طالب جديد',
                last_radar_check REAL   DEFAULT 0,
                radar_enabled  INTEGER DEFAULT 1,
                vip_status     INTEGER DEFAULT 0,
                last_active    REAL    DEFAULT 0,
                homeworks_used INTEGER DEFAULT 0,
                parent_admin_id INTEGER DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS license_keys (
                key_code      TEXT    PRIMARY KEY,
                days          INTEGER DEFAULT 30,
                used          INTEGER DEFAULT 0,
                used_by       INTEGER DEFAULT NULL,
                created_hijri TEXT    DEFAULT '',
                used_hijri    TEXT    DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER DEFAULT 0,
                action      TEXT    DEFAULT '',
                subject     TEXT    DEFAULT '',
                detail      TEXT    DEFAULT '',
                source      TEXT    DEFAULT 'SYSTEM',
                created_at  REAL    DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS radar_notifications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                homework_id TEXT,
                notified_at REAL,
                solved      INTEGER DEFAULT 0,
                UNIQUE(telegram_id, homework_id)
            );

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
            );


            CREATE TABLE IF NOT EXISTS event_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_type TEXT,
                event_name TEXT,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                session_id TEXT,
                response_time REAL,
                success BOOLEAN,
                error_message TEXT,
                created_at REAL
            );

            CREATE TABLE IF NOT EXISTS archived_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                    user_name TEXT,
                    platform_user TEXT NOT NULL,
                platform_pass TEXT NOT NULL,
                platform_url TEXT,
                platform_id TEXT,
                archived_at REAL NOT NULL,
                archived_by INTEGER NOT NULL,
                archived_by_name TEXT,
                reason TEXT,
                restored_at REAL,
                restored_by INTEGER,
                restored_by_name TEXT,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );


            CREATE TABLE IF NOT EXISTS solved_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question_id TEXT,
                question_text TEXT,
                answer TEXT,
                source TEXT DEFAULT 'unknown',
                solved_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );


            CREATE TABLE IF NOT EXISTS dashboard_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stat_name TEXT UNIQUE NOT NULL,
                stat_value TEXT,
                updated_at REAL NOT NULL
            );


            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                total_logins INTEGER DEFAULT 0,
                total_homeworks INTEGER DEFAULT 0,
                total_questions INTEGER DEFAULT 0,
                total_errors INTEGER DEFAULT 0,
                avg_response_time REAL DEFAULT 0,
                last_active REAL,
                preferred_time TEXT,
                total_api_calls INTEGER DEFAULT 0,
                groq_calls INTEGER DEFAULT 0,
                gemini_calls INTEGER DEFAULT 0,
                db_hits INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS button_clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                button_name TEXT,
                button_category TEXT,
                click_time REAL,
                session_duration REAL,
                previous_page TEXT
            );

            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                cpu_percent REAL,
                memory_percent REAL,
                active_users INTEGER,
                total_sessions INTEGER,
                browser_contexts INTEGER,
                db_connections INTEGER,
                api_latency REAL
            );

            -- ========== جداول الاشتراكات ==========
            CREATE TABLE IF NOT EXISTS subscription_plans (
                plan_id         TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                price           INTEGER NOT NULL,
                days            INTEGER NOT NULL,
                max_homeworks   INTEGER NOT NULL,
                description     TEXT,
                is_active       INTEGER DEFAULT 1,
                stars           INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                plan_id         TEXT NOT NULL,
                start_date      REAL NOT NULL,
                end_date        REAL NOT NULL,
                homeworks_used  INTEGER DEFAULT 0,
                max_homeworks   INTEGER NOT NULL,
                is_active       INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                FOREIGN KEY (plan_id) REFERENCES subscription_plans(plan_id)
            );

            -- ========== الجداول الجديدة للتسجيل الكامل ==========

            -- 1. طلبات فك القفل
            CREATE TABLE IF NOT EXISTS unlock_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                platform_user TEXT,
                request_date REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                processed_by INTEGER,
                processed_date REAL,
                reason TEXT,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            -- 2. سجل تعديلات الأدمن
            -- ملاحظة: بلا FOREIGN KEY — audit لازم ينجو من حذف المستخدمين،
            -- والـ FK كان يسبب فشل INSERT (admin_id=0) + قفل دائم للاتصال المشترك
            CREATE TABLE IF NOT EXISTS admin_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                admin_name TEXT,
                action_type TEXT NOT NULL,
                target_user_id INTEGER,
                target_user_name TEXT,
                old_value TEXT,
                new_value TEXT,
                details TEXT,
                created_at REAL NOT NULL
            );

            -- 3. سجل الدعم الفني (تذاكر)
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                ticket_type TEXT DEFAULT 'general',
                related_request_id INTEGER,
                related_request_type TEXT,
                status TEXT DEFAULT 'open',
                created_at REAL NOT NULL,
                closed_at REAL,
                closed_by INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            -- 4. رسائل الدعم الفني
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                message_text TEXT,
                has_photo BOOLEAN DEFAULT 0,
                photo_file_id TEXT,
                is_admin BOOLEAN DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES support_tickets(id),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            -- 5. جلسات حل الواجبات التفصيلية
            CREATE TABLE IF NOT EXISTS homework_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subject TEXT,
                homework_id TEXT,
                total_questions INTEGER DEFAULT 0,
                solved_questions INTEGER DEFAULT 0,
                correct_answers INTEGER DEFAULT 0,
                wrong_answers INTEGER DEFAULT 0,
                db_used INTEGER DEFAULT 0,
                groq_used INTEGER DEFAULT 0,
                gemini_used INTEGER DEFAULT 0,
                random_used INTEGER DEFAULT 0,
                start_time REAL NOT NULL,
                end_time REAL,
                status TEXT DEFAULT 'started',
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            -- 6. إشعارات النظام
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                notification_type TEXT,
                title TEXT,
                message TEXT,
                related_id TEXT,
                is_read BOOLEAN DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            -- 7. سجل عمليات تسجيل الدخول
            CREATE TABLE IF NOT EXISTS login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                platform_user TEXT,
                success BOOLEAN DEFAULT 1,
                error_message TEXT,
                ip_address TEXT,
                created_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );
            CREATE TABLE IF NOT EXISTS exam_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id TEXT NOT NULL,
                exam_name TEXT,
                question_number INTEGER NOT NULL,
                question_text TEXT,
                correct_answer TEXT,
                answer_type TEXT DEFAULT 'mcq',
                total_votes INTEGER DEFAULT 0,
                votes_for_answer TEXT,
                confirmed BOOLEAN DEFAULT 0,
                confirmed_at REAL,
                created_at REAL,
                updated_at REAL,
                UNIQUE(exam_id, question_number)
            );

            -- 8. سجل جميع الرسائل النصية
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
                created_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            -- ========== جداول الموزعين (Resellers) ==========

            CREATE TABLE IF NOT EXISTS reseller_keys (
                key_code      TEXT PRIMARY KEY,
                reseller_id   INTEGER NOT NULL,
                plan_type     TEXT NOT NULL,
                homeworks     INTEGER NOT NULL,
                days          INTEGER NOT NULL,
                used          INTEGER DEFAULT 0,
                used_by       INTEGER DEFAULT NULL,
                created_at    REAL DEFAULT (strftime('%s','now')),
                used_at       REAL DEFAULT NULL,
                FOREIGN KEY (reseller_id) REFERENCES users(telegram_id),
                FOREIGN KEY (used_by) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS reseller_transactions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                reseller_id   INTEGER NOT NULL,
                type          TEXT NOT NULL,
                amount        INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                details       TEXT DEFAULT '',
                created_at    REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (reseller_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS reseller_credit_prices (
                plan_type     TEXT PRIMARY KEY,
                credit_cost   INTEGER NOT NULL
            );

            -- ========== جدول سجل المعاملات (Transaction Log) ==========
            CREATE TABLE IF NOT EXISTS transaction_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id  INTEGER NOT NULL,
                to_user_id    INTEGER NOT NULL,
                amount        INTEGER NOT NULL,
                tx_type       TEXT    NOT NULL DEFAULT 'credit_transfer',
                notes         TEXT    DEFAULT '',
                created_at    REAL    DEFAULT (strftime('%s','now')),
                FOREIGN KEY (from_user_id) REFERENCES users(telegram_id),
                FOREIGN KEY (to_user_id)   REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS stars_payments (
                charge_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                plan_id TEXT,
                amount INTEGER,
                created_at REAL NOT NULL
            );
        """)

        # ✅ ✅ ✅ إضافة الأعمدة الجديدة للقاعدة القديمة (بدون مسح البيانات) ✅ ✅ ✅
        try:
            cursor = await self._connection.execute("PRAGMA table_info(users)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            if 'platform_url' not in column_names:
                await self._connection.execute("ALTER TABLE users ADD COLUMN platform_url TEXT DEFAULT ''")
                logger.info("✅ تم إضافة عمود: platform_url")

            if 'platform_id' not in column_names:
                await self._connection.execute("ALTER TABLE users ADD COLUMN platform_id TEXT DEFAULT ''")
                logger.info("✅ تم إضافة عمود: platform_id")

            if 'reseller_credit' not in column_names:
                await self._connection.execute("ALTER TABLE users ADD COLUMN reseller_credit INTEGER DEFAULT 0")
                logger.info("✅ تم إضافة عمود: reseller_credit")

            if 'referred_by_reseller' not in column_names:
                await self._connection.execute("ALTER TABLE users ADD COLUMN referred_by_reseller INTEGER DEFAULT NULL")
                logger.info("✅ تم إضافة عمود: referred_by_reseller")

            if 'parent_admin_id' not in column_names:
                await self._connection.execute("ALTER TABLE users ADD COLUMN parent_admin_id INTEGER DEFAULT NULL")
                logger.info("✅ تم إضافة عمود: parent_admin_id")

            # subscription_plans — عمود stars للقاعدة القديمة (بدون مسح البيانات)
            cursor = await self._connection.execute("PRAGMA table_info(subscription_plans)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            if 'stars' not in column_names:
                await self._connection.execute("ALTER TABLE subscription_plans ADD COLUMN stars INTEGER DEFAULT 0")
                logger.info("✅ تم إضافة عمود: stars (subscription_plans)")

            # جدول transaction_log — CREATE IF NOT EXISTS يكفي (لا يحتاج ALTER)

            await self._connection.commit()

        except Exception as e:
            logger.warning(f"⚠️ لم نتمكن من إضافة الأعمدة: {e}")

        await self._connection.commit()

    async def _create_harvest_tables(self):
        """Create harvest database tables"""
        await self._harvest_connection.execute("""
            CREATE TABLE IF NOT EXISTS student_cvs_v2 (
                platform_user TEXT PRIMARY KEY,
                telegram_id INTEGER,
                local_name TEXT,
                latin_name TEXT,
                identity_no TEXT,
                phone TEXT,
                nationality TEXT,
                stage TEXT,
                grade TEXT,
                student_class TEXT,
                profile_pic TEXT,
                scraped_at REAL
            )
        """)

        await self._harvest_connection.commit()

    async def _create_indexes(self):
        """إنشاء الفهارس لتحسين أداء الاستعلامات"""
        try:
            logger.info("📊 جاري إنشاء الفهارس...")

            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_solved_user ON solved_questions(user_id)")
            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_solved_time ON solved_questions(solved_at)")
            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_solved_source ON solved_questions(source)")

            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_logs_user ON logs(telegram_id)")
            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_logs_time ON logs(created_at)")

            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_events_user ON event_logs(user_id)")
            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_events_time ON event_logs(created_at)")

            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_homework_sessions_user ON homework_sessions(user_id)")
            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_homework_sessions_status ON homework_sessions(status)")

            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_users_expiry ON users(expiry_ts)")
            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_users_rank ON users(rank_title)")
            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_users_parent_admin ON users(parent_admin_id)")

            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_txlog_from ON transaction_log(from_user_id)")
            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_txlog_to ON transaction_log(to_user_id)")
            await self._connection.execute("CREATE INDEX IF NOT EXISTS idx_txlog_time ON transaction_log(created_at)")

            await self._connection.commit()
            logger.success("✅ تم إنشاء الفهارس بنجاح")

        except Exception as e:
            logger.warning(f"⚠️ فشل إنشاء الفهارس: {e}")

    async def get_connection(self) -> aiosqlite.Connection:
        """Get main database connection"""
        if not self._connection:
            await self.initialize()
        return self._connection

    async def get_harvest_connection(self) -> aiosqlite.Connection:
        """Get harvest database connection"""
        if not self._harvest_connection:
            await self.initialize()
        return self._harvest_connection

    def get_knowledge_connection(self) -> sqlite3.Connection:
        """Get knowledge database connection (sync for compatibility)"""
        if not self._knowledge_connection:
            self._knowledge_connection = sqlite3.connect(config.knowledge_db, timeout=60)
            self._knowledge_connection.execute("PRAGMA journal_mode=WAL")
            self._knowledge_connection.execute("PRAGMA synchronous=NORMAL")
            self._knowledge_connection.execute('''
                CREATE TABLE IF NOT EXISTS knowledge
                (subject_name TEXT, img_uuid TEXT UNIQUE, full_img_url TEXT,
                 question_text TEXT, answer TEXT, status TEXT)
            ''')
            self._knowledge_connection.commit()
            logger.info(f"📚 Knowledge DB connection initialized |")
        return self._knowledge_connection

    async def get_knowledge_connection_async(self) -> aiosqlite.Connection:
        """Get async knowledge database connection"""
        if not self._knowledge_connection_async:
            self._knowledge_connection_async = await aiosqlite.connect(config.knowledge_db, timeout=60)
            await self._knowledge_connection_async.execute("PRAGMA journal_mode=WAL")
            await self._knowledge_connection_async.execute("PRAGMA synchronous=NORMAL")
            self._knowledge_connection_async.row_factory = aiosqlite.Row
            await self._knowledge_connection_async.execute('''
                CREATE TABLE IF NOT EXISTS knowledge
                (subject_name TEXT, img_uuid TEXT UNIQUE, full_img_url TEXT,
                 question_text TEXT, answer TEXT, status TEXT)
            ''')
            await self._knowledge_connection_async.commit()
            logger.info(f"📚 Async Knowledge DB connection initialized")
        return self._knowledge_connection_async

    # ==============================================================================
    # ==============================================================================

    async def get_pooled_connection(self) -> aiosqlite.Connection:
        """Get connection from pool with semaphore limiting"""
        async with self._pool_semaphore:
            async with self._pool_lock:
                for conn in self._connection_pool:
                    try:
                        await conn.execute("SELECT 1")
                        logger.debug(f"🔗 Reusing pooled connection")
                        return conn
                    except:
                        self._connection_pool.remove(conn)

                new_conn = await aiosqlite.connect(
                    self.db_path,
                    timeout=30,
                    isolation_level=None
                )
                await new_conn.execute("PRAGMA journal_mode=WAL")
                await new_conn.execute("PRAGMA busy_timeout=30000")
                new_conn.row_factory = aiosqlite.Row
                self._connection_pool.append(new_conn)
                logger.info(f"🔗 New pooled connection created | Pool size: {len(self._connection_pool)}")
                return new_conn

    async def release_pooled_connection(self, conn: aiosqlite.Connection):
        """
        Release connection back to pool (keep it alive for reuse).
        يتحقق من صلاحية الاتصال - إذا فُتح transaction فاسد أو اتصال ميت،
        يُزال من الـ pool ليُستبدل باتصال جديد.
        """
        if conn is None:
            return
        async with self._pool_lock:
            try:
                await conn.execute("SELECT 1")
            except Exception as e:
                try:
                    if conn in self._connection_pool:
                        self._connection_pool.remove(conn)
                    await conn.close()
                except Exception:
                    pass
                logger.warning(f"🗑️ Removed dead connection from pool: {e}")

    async def close_pool(self):
        """Close all pooled connections"""
        async with self._pool_lock:
            for conn in self._connection_pool:
                try:
                    await conn.close()
                except:
                    pass
            self._connection_pool.clear()
            logger.info(f"🔒 Connection pool closed")

    async def close(self):
        """Close all database connections"""
        await self.close_pool()

        if self._connection:
            await self._connection.close()
            logger.info(f"🔒 Main DB connection closed")
        if self._harvest_connection:
            await self._harvest_connection.close()
            logger.info(f"🔒 Harvest DB connection closed")
        if self._knowledge_connection:
            self._knowledge_connection.close()
            logger.info(f"🔒 Sync Knowledge DB connection closed")
        if self._knowledge_connection_async:
            await self._knowledge_connection_async.close()
            logger.info(f"🔒 Async Knowledge DB connection closed")


# Module-level singleton (eager init, idempotent via __new__/__init__ pattern)
db_pool = DatabasePool()
