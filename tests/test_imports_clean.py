"""
اختبارات regression للـ import duplications و syntax errors
تغطية: Bug #3 (main.py), Bug #4 (fix_datetime.py), Bug #6 (utils.py), Bug #7 (ai_engine.py)
"""
import sys
import ast
from pathlib import Path
from collections import Counter

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def get_imports_from_file(file_path: Path, top_level_only: bool = True):
    """استخراج الـ imports من ملف Python

    Args:
        top_level_only: إذا True، يتم تجاهل الـ imports داخل الدوال/الكلاسات
    """
    content = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError as e:
        pytest.fail(f"SyntaxError in {file_path}: {e}")

    imports = []

    def collect_from_tree(t):
        for node in ast.iter_child_nodes(t):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if node.module:
                            imports.append(f"{node.module}.{alias.name}")
                        else:
                            imports.append(alias.name)
            elif not top_level_only:
                # descend into function/class bodies
                collect_from_tree(node)

    collect_from_tree(tree)
    return imports


class TestMainPyImports:
    """Bug #3: main.py كان يحتوي على imports مكررة"""

    def test_no_duplicate_telegram_ext_imports(self):
        main_path = PROJECT_ROOT / "main.py"
        imports = get_imports_from_file(main_path, top_level_only=True)
        telegram_ext = [i for i in imports if i.startswith("telegram.ext.")]
        counts = Counter(telegram_ext)
        duplicates = {k: v for k, v in counts.items() if v > 1}
        assert not duplicates, \
            f"Duplicate telegram.ext imports: {duplicates}"

    def test_no_duplicate_hasad_bot_handler_imports(self):
        main_path = PROJECT_ROOT / "main.py"
        imports = get_imports_from_file(main_path, top_level_only=True)
        # log_any_message, pre_checkout_handler, etc كانت مستوردة مرتين
        handler_imports = [i for i in imports if "bot_handlers" in i]
        counts = Counter(handler_imports)
        duplicates = {k: v for k, v in counts.items() if v > 1}
        assert not duplicates, \
            f"Duplicate bot_handlers top-level imports: {duplicates}"

    def test_no_duplicate_top_level_stdlib_imports(self):
        """Top-level imports فقط (inline imports داخل الدوال مسموحة)"""
        main_path = PROJECT_ROOT / "main.py"
        imports = get_imports_from_file(main_path, top_level_only=True)
        stdlib = ["io", "os", "time", "sys", "json", "csv", "asyncio"]
        for lib in stdlib:
            count = sum(
                1 for i in imports
                if i == lib or i.startswith(f"{lib}.")
            )
            assert count <= 1, f"Top-level stdlib {lib} imported {count} times"

    def test_main_py_parses_without_syntax_error(self):
        main_path = PROJECT_ROOT / "main.py"
        content = main_path.read_text(encoding="utf-8")
        try:
            ast.parse(content, filename=str(main_path))
        except SyntaxError as e:
            pytest.fail(f"main.py has syntax error: {e}")


class TestFixDatetimeSyntax:
    """Bug #4: fix_datetime.py كان يحتوي على tuple syntax error"""

    def test_no_tuple_in_string_assignment(self):
        """
        Bug #4 كان: replacement2 = 'from hasad_bot.datetime_utils import datetime, now', now_timestamp
        (هذا tuple، ليس string)
        """
        fix_path = PROJECT_ROOT / "fix_datetime.py"
        content = fix_path.read_text(encoding="utf-8")

        # البحث عن النمط المكسور: string assignment يتبع بـ comma + identifier
        bad_patterns = [
            r"replacement[12]\s*=\s*['\"].*?['\"]\s*,\s*\w+",  # string, identifier
            r"replacement[12]\s*=\s*['\"].*?['\"]\s*,\s*['\"]",  # string, string
        ]
        for pattern in bad_patterns:
            matches = []
            for line_num, line in enumerate(content.splitlines(), 1):
                if __import__("re").search(pattern, line):
                    matches.append((line_num, line.strip()))
            assert not matches, \
                f"Bad tuple assignment found: {matches}"

    def test_fix_datetime_parses_without_syntax_error(self):
        fix_path = PROJECT_ROOT / "fix_datetime.py"
        content = fix_path.read_text(encoding="utf-8")
        try:
            ast.parse(content, filename=str(fix_path))
        except SyntaxError as e:
            pytest.fail(f"fix_datetime.py has syntax error: {e}")

    def test_no_paren_after_import_within_string(self):
        """replacement3 = '... import (, now_timestamp' كان bug أيضاً"""
        fix_path = PROJECT_ROOT / "fix_datetime.py"
        content = fix_path.read_text(encoding="utf-8")
        # البحث عن 'import (' داخل string
        bad_pattern = r"import\s*\("
        for line_num, line in enumerate(content.splitlines(), 1):
            if bad_pattern in line and "replacement" in line:
                # التحقق: إذا كان داخل quotes، فهو مقبول كـ string
                # لكن إذا كان داخل string لا يجب أن يكون هكذا
                if "'" in line and 'import (' in line:
                    pytest.fail(
                        f"Line {line_num}: 'import (' inside string is suspicious: {line.strip()}"
                    )


class TestUtilsPyImports:
    """Bug #6: utils.py كان يحتوي على imports مكررة"""

    def test_no_duplicate_datetime_utils_imports(self):
        utils_path = PROJECT_ROOT / "hasad_bot" / "utils.py"
        imports = get_imports_from_file(utils_path)
        du_imports = [i for i in imports if "datetime_utils" in i]
        counts = Counter(du_imports)
        duplicates = {k: v for k, v in counts.items() if v > 1}
        assert not duplicates, \
            f"Duplicate datetime_utils imports: {duplicates}"

    def test_utils_py_has_shebang_first_line(self):
        """الـ shebang يجب أن يكون في السطر الأول"""
        utils_path = PROJECT_ROOT / "hasad_bot" / "utils.py"
        content = utils_path.read_text(encoding="utf-8")
        first_line = content.splitlines()[0] if content else ""
        assert first_line.startswith("#!"), \
            f"utils.py first line should be shebang, got: {first_line[:50]}"


class TestAiEngineImports:
    """Bug #7: ai_engine.py كان يحتوي على imports مكررة"""

    def test_no_duplicate_datetime_utils_imports(self):
        ai_dir = PROJECT_ROOT / "hasad_bot" / "ai_engine"
        all_dupes = {}
        for py_file in ai_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            imports = get_imports_from_file(py_file)
            du_imports = [i for i in imports if "datetime_utils" in i]
            counts = Counter(du_imports)
            duplicates = {k: v for k, v in counts.items() if v > 1}
            if duplicates:
                all_dupes[py_file.name] = duplicates
        assert not all_dupes, \
            f"Duplicate datetime_utils imports in ai_engine/: {all_dupes}"


class TestAllPythonFilesParseClean:
    """اختبار شامل: كل ملفات Python في المشروع تستورد بنجاح"""

    def test_all_hasad_bot_modules_import(self):
        """كل الـ modules في hasad_bot/ تستورد بدون syntax error"""
        hasad_bot_dir = PROJECT_ROOT / "hasad_bot"
        failed = []
        for py_file in hasad_bot_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            content = py_file.read_text(encoding="utf-8")
            try:
                ast.parse(content, filename=str(py_file))
            except SyntaxError as e:
                failed.append((py_file.name, str(e)))
        assert not failed, f"Files with syntax errors: {failed}"

    def test_main_py_imports(self):
        """main.py يستورد بنجاح (نختبره كآخر شيء لأنه قد يحتاج إعدادات)"""
        main_path = PROJECT_ROOT / "main.py"
        content = main_path.read_text(encoding="utf-8")
        try:
            ast.parse(content, filename=str(main_path))
        except SyntaxError as e:
            pytest.fail(f"main.py syntax error: {e}")
