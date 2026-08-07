"""
اختبارات connection_pool.py — KnowledgeDBPool + HTTPPool
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestKnowledgeDBPoolSingleton:
    """KnowledgeDBPool يجب أن يكون Singleton"""

    def test_singleton_same_instance(self):
        from hasad_bot.ai_engine.connection_pool import KnowledgeDBPool
        a = KnowledgeDBPool()
        b = KnowledgeDBPool()
        assert a is b, "KnowledgeDBPool must return the same instance"

    def test_singleton_has_lock(self):
        from hasad_bot.ai_engine.connection_pool import KnowledgeDBPool
        pool = KnowledgeDBPool()
        assert hasattr(pool, "_lock"), "Pool must have _lock attribute"

    def test_singleton_initial_state(self):
        from hasad_bot.ai_engine.connection_pool import KnowledgeDBPool
        pool = KnowledgeDBPool()
        assert pool._conn is None or pool._initialized is False


class TestHTTPPoolSingleton:
    """HTTPPool يجب أن يكون Singleton"""

    def test_singleton_same_instance(self):
        from hasad_bot.ai_engine.connection_pool import HTTPPool
        a = HTTPPool()
        b = HTTPPool()
        assert a is b, "HTTPPool must return the same instance"

    def test_groq_client_none_initially(self):
        from hasad_bot.ai_engine.connection_pool import HTTPPool
        pool = HTTPPool()
        pool._groq_client = None
        pool._gemini_client = None

        with patch("hasad_bot.ai_engine.connection_pool.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = MagicMock(is_closed=False)
            client = pool.get_groq_client()
            assert client is not None

    def test_gemini_client_none_initially(self):
        from hasad_bot.ai_engine.connection_pool import HTTPPool
        pool = HTTPPool()
        pool._groq_client = None
        pool._gemini_client = None

        with patch("hasad_bot.ai_engine.connection_pool.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = MagicMock(is_closed=False)
            client = pool.get_gemini_client()
            assert client is not None

    def test_groq_client_reuse(self):
        from hasad_bot.ai_engine.connection_pool import HTTPPool
        pool = HTTPPool()
        fake_client = MagicMock(is_closed=False)
        pool._groq_client = fake_client

        result = pool.get_groq_client()
        assert result is fake_client, "Should reuse existing non-closed client"

    def test_gemini_client_reuse(self):
        from hasad_bot.ai_engine.connection_pool import HTTPPool
        pool = HTTPPool()
        fake_client = MagicMock(is_closed=False)
        pool._gemini_client = fake_client

        result = pool.get_gemini_client()
        assert result is fake_client, "Should reuse existing non-closed client"

    def test_groq_client_recreated_when_closed(self):
        from hasad_bot.ai_engine.connection_pool import HTTPPool
        pool = HTTPPool()
        old_client = MagicMock(is_closed=True)
        pool._groq_client = old_client

        with patch("hasad_bot.ai_engine.connection_pool.httpx") as mock_httpx:
            new_client = MagicMock(is_closed=False)
            mock_httpx.AsyncClient.return_value = new_client
            client = pool.get_groq_client()
            assert client is new_client

    def test_global_instances_exist(self):
        from hasad_bot.ai_engine.connection_pool import kb_pool, http_pool
        assert kb_pool is not None
        assert http_pool is not None
