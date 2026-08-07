"""
connection_pool.py — Connection pools for Knowledge DB + HTTP clients.

يوفر:
- KnowledgeDBPool: aiosqlite connection واحدة تُعاد استخدامها لجميع الاستعلامات
- HTTPPool: httpx.AsyncClient واحد دائم لـ Groq + Gemini

يدعم 100+ مستخدم متزامن بدون فتح/إغلاق اتصالات.
"""

import asyncio
import aiosqlite
import httpx
from loguru import logger
from hasad_bot.config import config


# ==============================================================================
# Knowledge DB Pool — connection واحدة aiosqlite
# ==============================================================================

class KnowledgeDBPool:
    """
    Pool بسيط لقاعدة المعرفة — connection واحدة async تُعاد استخدامها.
    آمن لـ 100+ مستخدم (aiosqlite يدعم WAL mode بشكل افتراضي).
    """
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conn = None
            cls._instance._initialized = False
        return cls._instance

    async def get_connection(self) -> aiosqlite.Connection:
        """إعادة الاتصال الموجود أو إنشاء واحد جديد"""
        if self._conn is None:
            self._conn = await aiosqlite.connect(str(config.knowledge_db))
            # WAL mode = أسرع لقراءات متزامنة
            await self._conn.execute("PRAGMA journal_mode=WAL")
            # Busy timeout = ينتظر بدل ما يفشل فوراً
            await self._conn.execute("PRAGMA busy_timeout=5000")
            # إنشاء جدول knowledge إذا لم يكن موجوداً
            await self._conn.execute('''
                CREATE TABLE IF NOT EXISTS knowledge
                (subject_name TEXT, img_uuid TEXT UNIQUE, full_img_url TEXT,
                 question_text TEXT, answer TEXT, status TEXT)
            ''')
            await self._conn.commit()
            self._initialized = True
            logger.info("Knowledge DB pool initialized (WAL mode)")
        return self._conn

    async def execute(self, query: str, params=()) -> aiosqlite.Cursor:
        """تنفيذ استعلام — يعيد الـ cursor"""
        conn = await self.get_connection()
        return await conn.execute(query, params)

    async def fetchone(self, query: str, params=()):
        """جلب صف واحد"""
        cursor = await self.execute(query, params)
        return await cursor.fetchone()

    async def fetchall(self, query: str, params=()):
        """جلب كل الصفوف"""
        cursor = await self.execute(query, params)
        return await cursor.fetchall()

    async def commit(self):
        """حفظ التغييرات"""
        conn = await self.get_connection()
        await conn.commit()

    async def close(self):
        """إغلاق الاتصال (عند إيقاف البوت)"""
        if self._conn:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None
            self._initialized = False
            logger.info("Knowledge DB pool closed")


# ==============================================================================
# HTTP Pool — httpx.AsyncClient واحد دائم
# ==============================================================================

class HTTPPool:
    """
    Pool لـ httpx clients — client واحد دائم لكل API.
    يدعم 100+ مستخدم متزامن بدون فتح/إغلاق TCP connections.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._groq_client = None
            cls._instance._gemini_client = None
        return cls._instance

    def get_groq_client(self) -> httpx.AsyncClient:
        """إعادة client Groq أو إنشاء واحد جديد"""
        if self._groq_client is None or self._groq_client.is_closed:
            self._groq_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=20,
                    keepalive_expiry=300,
                ),
                headers={
                    "Content-Type": "application/json",
                },
            )
            logger.info("Groq HTTP pool initialized")
        return self._groq_client

    def get_gemini_client(self) -> httpx.AsyncClient:
        """إعادة client Gemini أو إنشاء واحد جديد"""
        if self._gemini_client is None or self._gemini_client.is_closed:
            self._gemini_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=20,
                    keepalive_expiry=300,
                ),
            )
            logger.info("Gemini HTTP pool initialized")
        return self._gemini_client

    async def close(self):
        """إغلاق كل الـ clients"""
        for name, client in [("Groq", self._groq_client), ("Gemini", self._gemini_client)]:
            if client and not client.is_closed:
                try:
                    await client.aclose()
                except Exception:
                    pass
                logger.info(f"{name} HTTP pool closed")
        self._groq_client = None
        self._gemini_client = None


# ==============================================================================
# Global instances
# ==============================================================================

kb_pool = KnowledgeDBPool()
http_pool = HTTPPool()
