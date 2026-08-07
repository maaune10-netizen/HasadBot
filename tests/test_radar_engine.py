"""
اختبارات hasad_bot.radar_engine
تغطية: regression test للـ Bug #1 (now = now() UnboundLocalError)
"""
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestRadarLoopRegression:
    """
    Bug #1 كان: في radar_engine.py كان هناك:
        def radar_loop():
            now = time.time()  # ← يعرّف `now` كـ local
            ...
            target = now.replace(hour=20)  # ← AttributeError

    الـ fix كان: استخدام `current_time` بدلاً من `now`.
    """

    def test_no_local_variable_now_in_radar_engine(self):
        """
        التأكد من أن radar_engine.py لا يستخدم `now` كـ local variable
        في الـ radar_loop function
        """
        radar_path = PROJECT_ROOT / "hasad_bot" / "radar_engine.py"
        content = radar_path.read_text(encoding="utf-8")
        # البحث عن `now = ` في الكود (assignment يعرّفه local)
        # لكن `now()` كاستدعاء دالة لا يعرّفه
        assert "now = time.time()" not in content, \
            "radar_engine.py shouldn't assign to `now` (would shadow the import)"
        assert "now = datetime.now()" not in content, \
            "radar_engine.py shouldn't assign to `now`"

    def test_current_time_replaces_now_in_radar_loop(self):
        """التأكد من استخدام current_time في radar_loop"""
        radar_path = PROJECT_ROOT / "hasad_bot" / "radar_engine.py"
        content = radar_path.read_text(encoding="utf-8")
        # إذا radar_loop موجود، يجب أن يستخدم current_time
        if "async def radar_loop" in content or "def radar_loop" in content:
            assert "current_time" in content, \
                "radar_loop should use `current_time` instead of `now`"

    def test_now_function_call_works_in_radar_logic(self):
        """
        محاكاة منطق radar_loop للتأكد من أن:
        - استدعاء now() يعمل
        - .replace() على النتيجة يعمل
        - لا UnboundLocalError
        """
        from hasad_bot.datetime_utils import now

        # هذا بالضبط ما كان يكسر في الـ bug
        current_time = now()
        target = current_time.replace(hour=20, minute=0, second=0, microsecond=0)
        assert target.hour == 20
        assert target.minute == 0
        assert isinstance(target, datetime)


class TestRadarEngineImports:
    """اختبارات imports الـ radar_engine"""

    def test_radar_engine_module_imports(self):
        """التأكد من أن radar_engine يستورد بدون أخطاء"""
        try:
            from hasad_bot import radar_engine
            assert hasattr(radar_engine, "RadarEngine") or \
                   hasattr(radar_engine, "radar_loop") or \
                   hasattr(radar_engine, "check_new_homework"), \
                   "radar_engine should expose RadarEngine or radar functions"
        except ImportError as e:
            pytest.fail(f"Failed to import radar_engine: {e}")
