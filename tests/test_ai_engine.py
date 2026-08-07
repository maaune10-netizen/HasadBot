"""
اختبارات ai_engine modules — AIManager, api_clients, metrics, logging, state
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# state.py
# =============================================================================
class TestState:
    def test_stats_has_expected_keys(self):
        from hasad_bot.ai_engine.state import stats
        required = ["groq", "gemini", "db_hits", "total_hw", "errors", "random"]
        for key in required:
            assert key in stats, f"stats missing key: {key}"

    def test_active_sessions_is_dict(self):
        from hasad_bot.ai_engine.state import active_sessions
        assert isinstance(active_sessions, dict)


# =============================================================================
# metrics.py
# =============================================================================
class TestMetrics:
    def test_increment_correct_answer(self):
        from hasad_bot.ai_engine.state import stats
        before = stats.get("correct_answers", 0)
        from hasad_bot.ai_engine.metrics import increment_correct_answer
        increment_correct_answer("groq")
        assert stats["correct_answers"] == before + 1

    def test_increment_wrong_answer(self):
        from hasad_bot.ai_engine.state import stats
        before = stats.get("wrong_answers", 0)
        from hasad_bot.ai_engine.metrics import increment_wrong_answer
        increment_wrong_answer()
        assert stats["wrong_answers"] == before + 1

    def test_increment_total_questions(self):
        from hasad_bot.ai_engine.state import stats
        before = stats.get("total_questions", 0)
        from hasad_bot.ai_engine.metrics import increment_total_questions
        increment_total_questions()
        assert stats["total_questions"] == before + 1

    def test_ai_source_increments_solved_by_ai(self):
        from hasad_bot.ai_engine.state import stats
        before = stats.get("solved_by_ai", 0)
        from hasad_bot.ai_engine.metrics import increment_correct_answer
        increment_correct_answer("ensemble")
        assert stats["solved_by_ai"] == before + 1

    def test_non_ai_source_does_not_increment_solved_by_ai(self):
        from hasad_bot.ai_engine.state import stats
        before = stats.get("solved_by_ai", 0)
        from hasad_bot.ai_engine.metrics import increment_correct_answer
        increment_correct_answer("random")
        assert stats["solved_by_ai"] == before


# =============================================================================
# logging.py — AnswerSource
# =============================================================================
class TestAnswerSource:
    def test_answer_source_values(self):
        from hasad_bot.ai_engine.logging import AnswerSource
        assert AnswerSource.DATABASE.value == "db"
        assert AnswerSource.GROQ.value == "groq"
        assert AnswerSource.GEMINI.value == "gemini"
        assert AnswerSource.RANDOM.value == "random"

    def test_answer_source_is_str(self):
        from hasad_bot.ai_engine.logging import AnswerSource
        assert isinstance(AnswerSource.DATABASE, str)
        assert AnswerSource.GROQ.value == "groq"


# =============================================================================
# api_clients.py — GEMINI_AVAILABLE
# =============================================================================
class TestAPIClients:
    def test_gemini_available_is_bool(self):
        from hasad_bot.ai_engine.api_clients import GEMINI_AVAILABLE
        assert isinstance(GEMINI_AVAILABLE, bool)

    def test_gemini_available_reflects_import(self):
        from hasad_bot.ai_engine.api_clients import GEMINI_AVAILABLE
        try:
            from google import genai
            import PIL.Image
            assert GEMINI_AVAILABLE is True
        except ImportError:
            assert GEMINI_AVAILABLE is False


# =============================================================================
# ai_manager.py — AIManager methods exist
# =============================================================================
class TestAIManager:
    def test_ai_manager_has_groq_method(self):
        from hasad_bot.ai_engine.ai_manager import AIManager
        assert hasattr(AIManager, "get_groq_answer")

    def test_ai_manager_has_gemini_text_method(self):
        from hasad_bot.ai_engine.ai_manager import AIManager
        assert hasattr(AIManager, "get_gemini_answer_text")

    def test_ai_manager_has_ensemble_method(self):
        from hasad_bot.ai_engine.ai_manager import AIManager
        assert hasattr(AIManager, "get_ensemble_answer")

    def test_ai_manager_has_gemini_essay_method(self):
        from hasad_bot.ai_engine.ai_manager import AIManager
        assert hasattr(AIManager, "get_gemini_answer_essay")

    def test_ai_manager_has_qwen_method(self):
        from hasad_bot.ai_engine.ai_manager import AIManager
        assert hasattr(AIManager, "get_qwen_answer")
