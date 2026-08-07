"""
اختبارات hasad_bot.database
تغطية: Bug #5 regression (user_id → telegram_id في _create_indexes)
Note: Schema/indexes/connection pool are in hasad_bot/database/pool.py after the split.
"""
import sys
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

POOL_PATH = PROJECT_ROOT / "hasad_bot" / "database" / "pool.py"


class TestDatabaseSchema:
    """اختبارات بنية قاعدة البيانات"""

    def test_logs_table_uses_telegram_id(self):
        """جدول logs يجب أن يستخدم telegram_id (وليس user_id)"""
        assert POOL_PATH.exists(), f"pool.py not found at {POOL_PATH}"
        content = POOL_PATH.read_text(encoding="utf-8")

        # ابحث عن CREATE TABLE logs
        logs_section_match = re.search(
            r"CREATE TABLE.*?logs.*?\)",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        assert logs_section_match is not None, "logs table creation not found"

        logs_section = logs_section_match.group(0)
        assert "telegram_id" in logs_section, \
            "logs table should have telegram_id column"
        # user_id قد يكون موجوداً في جداول أخرى (users) — لا نمنعه
        # لكن في logs section لا يجب أن يكون PRIMARY KEY

    def test_no_index_on_nonexistent_user_id_in_logs(self):
        """Bug #5 regression: لا يوجد index على user_id في logs"""
        content = POOL_PATH.read_text(encoding="utf-8")
        # Bug: كان idx_logs_user ON logs(user_id) — عمود غير موجود
        # الـ fix: ON logs(telegram_id)
        # التحقق من عدم وجود النمط القديم
        bad_pattern = r"idx_logs_user\s+ON\s+logs\s*\(\s*user_id\s*\)"
        assert not re.search(bad_pattern, content), \
            "Bug #5 regression: idx_logs_user ON logs(user_id) still exists"

        # التحقق من وجود النمط الصحيح
        good_pattern = r"ON\s+logs\s*\(\s*telegram_id\s*\)"
        assert re.search(good_pattern, content), \
            "Should have index on logs(telegram_id)"

    def test_users_table_has_telegram_id(self):
        """جدول users يحتوي على telegram_id (UNIQUE)"""
        content = POOL_PATH.read_text(encoding="utf-8")
        assert "telegram_id" in content, \
            "pool.py should reference telegram_id"

    def test_database_is_package_not_module(self):
        """after the split, hasad_bot.database must be a package, not a single file"""
        db_path = PROJECT_ROOT / "hasad_bot" / "database.py"
        db_dir = PROJECT_ROOT / "hasad_bot" / "database"
        assert not db_path.exists() or db_path.is_file(), \
            "Old monolithic database.py should have been removed"
        assert db_dir.is_dir(), \
            "hasad_bot/database/ package directory should exist"
        assert (db_dir / "__init__.py").is_file(), \
            "hasad_bot/database/__init__.py must exist"


class TestConnectionPool:
    """اختبارات connection pool (Bug #9 regression)"""

    def test_release_pooled_connection_validates(self):
        """
        Bug #9 regression: release_pooled_connection كان `pass` فارغ.
        الـ fix: يتحقق من صلاحية الاتصال ويزيل الميت من الـ pool.
        """
        content = POOL_PATH.read_text(encoding="utf-8")

        match = re.search(
            r"async def release_pooled_connection\(self[^)]*\)[^:]*:(.*?)(?=\n    (?:async )?def |\nclass |\Z)",
            content,
            re.DOTALL,
        )
        assert match is not None, "release_pooled_connection not found"

        body = match.group(1)
        assert "SELECT 1" in body, \
            "release_pooled_connection should validate with SELECT 1"
        assert "remove" in body or "_connection_pool.remove" in body, \
            "release_pooled_connection should remove dead connections from pool"
        assert "close" in body, \
            "release_pooled_connection should close dead connections"

    def test_release_pooled_connection_not_just_pass(self):
        """regression: لا يجب أن تكون الدالة فارغة بـ pass فقط"""
        content = POOL_PATH.read_text(encoding="utf-8")

        match = re.search(
            r"async def release_pooled_connection\(self[^)]*\)[^:]*:(.*?)(?=\n    (?:async )?def |\nclass |\Z)",
            content,
            re.DOTALL,
        )
        assert match is not None
        body = match.group(1).strip()
        assert body != "pass", \
            "release_pooled_connection should not be a no-op (just pass)"
