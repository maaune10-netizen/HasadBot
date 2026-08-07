"""
اختبارات ui.py + exam_finish.py
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestGetEngineKeyboard:
    """اختبارات get_engine_keyboard"""

    def test_returns_markup_when_no_session(self):
        from hasad_bot.ai_engine.ui import get_engine_keyboard
        markup = get_engine_keyboard(None)
        assert hasattr(markup, "inline_keyboard")

    def test_returns_start_button_when_not_running(self):
        from hasad_bot.ai_engine.ui import get_engine_keyboard
        session = MagicMock()
        session.is_running = False
        markup = get_engine_keyboard(session)
        buttons = markup.inline_keyboard[0]
        assert any("بدء" in b.text for b in buttons)

    def test_returns_stop_button_when_running(self):
        from hasad_bot.ai_engine.ui import get_engine_keyboard
        session = MagicMock()
        session.is_running = True
        markup = get_engine_keyboard(session)
        all_text = str(markup)
        assert "إيقاف" in all_text


class TestExamFinish:
    """اختبارات exam_finish.py — is_essay_question"""

    def test_is_essay_question_exists(self):
        from hasad_bot.ai_engine.exam_finish import is_essay_question
        assert callable(is_essay_question)

    def test_get_total_questions_count_exists(self):
        from hasad_bot.ai_engine.exam_finish import get_total_questions_count
        assert callable(get_total_questions_count)
