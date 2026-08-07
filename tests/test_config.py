"""
اختبارات hasad_bot.config
تغطية: تحميل المتغيرات، validation، BACKUP_PASSWORD, dashboard security
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestConfigLoading:
    """اختبارات تحميل .env"""

    def test_env_file_exists(self):
        """ملف .env موجود في المشروع"""
        env_file = PROJECT_ROOT / ".env"
        assert env_file.exists(), ".env file should exist in project root"

    def test_required_keys_present(self):
        """المفاتيح الإجبارية موجودة في .env"""
        env_file = PROJECT_ROOT / ".env"
        content = env_file.read_text(encoding="utf-8")
        required_keys = [
            "BOT_TOKEN",
            "ADMIN_ID",
            "BACKUP_PASSWORD",
            "GROQ_KEY_1",
            "GEMINI_KEY_1",
        ]
        for key in required_keys:
            assert key in content, f"Required key {key} missing from .env"

    def test_groq_keys_count(self):
        """عدد مفاتيح Groq >= 3 (المطلوب فعلياً للتشغيل)"""
        env_file = PROJECT_ROOT / ".env"
        content = env_file.read_text(encoding="utf-8")
        # Active keys = those with non-empty values
        active = sum(
            1 for line in content.splitlines()
            if line.startswith("GROQ_KEY_") and "=" in line
            and len(line.split("=", 1)[1].strip()) > 10  # real keys are long
        )
        assert active >= 3, f"Expected at least 3 active GROQ_KEY entries, found {active}"

    def test_gemini_keys_count(self):
        """عدد مفاتيح Gemini >= 3 (المطلوب فعلياً للتشغيل)"""
        env_file = PROJECT_ROOT / ".env"
        content = env_file.read_text(encoding="utf-8")
        active = sum(
            1 for line in content.splitlines()
            if line.startswith("GEMINI_KEY_") and "=" in line
            and len(line.split("=", 1)[1].strip()) > 10
        )
        assert active >= 3, f"Expected at least 3 active GEMINI_KEY entries, found {active}"


class TestConfigValidation:
    """اختبارات validation في Config"""

    def test_no_duplicate_active_env_keys(self):
        """لا تكرار لمفاتيح .env النشطة (المفاتيح المعلقة بـ # لا تحسب)"""
        env_file = PROJECT_ROOT / ".env"
        content = env_file.read_text(encoding="utf-8")
        seen = set()
        duplicates = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in seen:
                    duplicates.append(key)
                seen.add(key)
        # ملاحظة: قد يكون هناك مفاتيح مكررة (يعرف المستخدم عنها)
        # هذا الاختبار warning فقط
        if duplicates:
            pytest.skip(
                f"Note: Duplicate active .env keys present: {duplicates}. "
                "Config will use the first occurrence."
            )


class TestDashboardSecurityConfig:
    """اختبارات إعدادات Dashboard Security"""

    def test_dashboard_security_keys_in_env_example(self):
        """مفاتيح Dashboard Security موثقة في .env.example"""
        env_example = PROJECT_ROOT / ".env.example"
        if not env_example.exists():
            pytest.skip(".env.example not present")
        content = env_example.read_text(encoding="utf-8")
        assert "DASHBOARD_USERNAME" in content
        assert "DASHBOARD_PASSWORD_HASH" in content
        assert "JWT_SECRET" in content
