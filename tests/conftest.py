"""
Pytest configuration & shared fixtures
"""
import sys
import os
import asyncio
import tempfile
from pathlib import Path

# ضمان إضافة مسار المشروع لـ sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
import pytest_asyncio


# -----------------------------------------------------------------------------
# Event Loop Policy (pytest-asyncio)
# -----------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole test session"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# -----------------------------------------------------------------------------
# Temporary directories
# -----------------------------------------------------------------------------
@pytest.fixture
def temp_dir():
    """مجلد مؤقت لكل اختبار"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_env_file(temp_dir):
    """ملف .env مؤقت بالحد الأدنى من المتطلبات"""
    env_file = temp_dir / ".env"
    env_file.write_text(
        "BOT_TOKEN=test_token\n"
        "ADMIN_ID=123456\n"
        "BACKUP_CHANNEL_ID=-100123456\n"
        "BACKUP_PASSWORD=test123\n"
        "GROQ_KEY_1=gsk_test1\n"
        "GROQ_KEY_2=gsk_test2\n"
        "GROQ_KEY_3=gsk_test3\n"
        "GROQ_KEY_4=gsk_test4\n"
        "GROQ_KEY_5=gsk_test5\n"
        "GROQ_KEY_6=gsk_test6\n"
        "GROQ_KEY_7=gsk_test7\n"
        "GROQ_KEY_8=gsk_test8\n"
        "GROQ_KEY_9=gsk_test9\n"
        "GROQ_KEY_10=gsk_test10\n"
        "GEMINI_KEY_1=AIza_test1\n"
        "GEMINI_KEY_2=AIza_test2\n"
        "GEMINI_KEY_3=AIza_test3\n"
        "GEMINI_KEY_4=AIza_test4\n"
        "GEMINI_KEY_5=AIza_test5\n"
        "GEMINI_KEY_6=AIza_test6\n"
        "GEMINI_KEY_7=AIza_test7\n"
        "GEMINI_KEY_8=AIza_test8\n"
        "GEMINI_KEY_9=AIza_test9\n"
        "GEMINI_KEY_10=AIza_test10\n"
        "DASHBOARD_USERNAME=admin\n"
        "DASHBOARD_PASSWORD_HASH=$2b$12$test_bcrypt_hash_here\n"
        "JWT_SECRET=test_jwt_secret_for_testing_only\n",
        encoding="utf-8",
    )
    return env_file


# -----------------------------------------------------------------------------
# Markers configuration
# -----------------------------------------------------------------------------
def pytest_configure(config):
    """تسجيل الـ markers المخصصة"""
    config.addinivalue_line(
        "markers", "slow: اختبارات بطيئة (تتجاوز 5 ثوانٍ)"
    )
    config.addinivalue_line(
        "markers", "integration: اختبارات تحتاج Telegram bot حقيقي"
    )
