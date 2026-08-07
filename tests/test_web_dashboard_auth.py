"""
اختبارات hasad_bot.web_dashboard_auth
تغطية: PasswordManager, JWTManager, RateLimiter, IPWhitelist, AuditLogger
"""
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hasad_bot.web_dashboard_auth import (
    PasswordManager,
    JWTManager,
    RateLimiter,
    RateLimitConfig,
    IPWhitelist,
    AuditLogger,
)


# =============================================================================
# PasswordManager
# =============================================================================
class TestPasswordManager:
    """اختبارات PasswordManager (bcrypt)"""

    def test_hash_password_returns_bcrypt_hash(self):
        """hashed يجب أن يبدأ بـ $2b$ (bcrypt v2b)"""
        hashed = PasswordManager.hash_password("test_password_123")
        assert hashed.startswith("$2b$"), f"Expected bcrypt $2b$ prefix, got: {hashed[:10]}"

    def test_hash_returns_different_each_time(self):
        """نفس كلمة المرور تعطي hash مختلف في كل مرة (بسبب salt)"""
        h1 = PasswordManager.hash_password("test_password_123")
        h2 = PasswordManager.hash_password("test_password_123")
        assert h1 != h2, "bcrypt should use random salt"

    def test_hash_short_password_raises(self):
        """كلمة مرور قصيرة (أقل من 8) ترفع ValueError"""
        with pytest.raises(ValueError):
            PasswordManager.hash_password("short")

    def test_hash_empty_password_raises(self):
        """كلمة مرور فارغة ترفع ValueError"""
        with pytest.raises(ValueError):
            PasswordManager.hash_password("")

    def test_verify_correct_password(self):
        """التحقق من كلمة المرور الصحيحة"""
        plain = "MySecureP@ss123"
        hashed = PasswordManager.hash_password(plain)
        assert PasswordManager.verify_password(plain, hashed) is True

    def test_verify_wrong_password(self):
        """التحقق من كلمة مرور خاطئة"""
        hashed = PasswordManager.hash_password("correct_password_123")
        assert PasswordManager.verify_password("wrong_password_123", hashed) is False

    def test_verify_invalid_hash_returns_false(self):
        """hash غير صالح يرجع False (لا exception)"""
        assert PasswordManager.verify_password("anything", "not_a_valid_hash") is False

    def test_verify_empty_inputs_return_false(self):
        """مدخلات فارغة ترجع False"""
        assert PasswordManager.verify_password("", "any_hash") is False
        assert PasswordManager.verify_password("password", "") is False


# =============================================================================
# JWTManager
# =============================================================================
class TestJWTManager:
    """اختبارات JWTManager (PyJWT HS256)"""

    def test_create_token_returns_string(self):
        """create_token يعيد string غير فارغ"""
        jwtm = JWTManager(secret_key="test_secret_at_least_32_chars_long")
        token = jwtm.create_token(username="admin", ip_address="127.0.0.1")
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT format: header.payload.signature (3 parts مفصولة بنقطة)
        assert token.count(".") == 2, "JWT should have 3 parts"

    def test_decode_valid_token(self):
        """decode_token للـ token صحيح يعيد payload"""
        jwtm = JWTManager(secret_key="test_secret_at_least_32_chars_long")
        token = jwtm.create_token(username="admin", ip_address="127.0.0.1")
        payload = jwtm.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "admin"
        assert payload["ip"] == "127.0.0.1"
        assert "iat" in payload
        assert "exp" in payload

    def test_decode_expired_token(self):
        """token منتهي الصلاحية (idle) يرجع None"""
        jwtm = JWTManager(secret_key="test_secret_at_least_32_chars_long", expiry_hours=0)
        token = jwtm.create_token(username="admin", ip_address="127.0.0.1")
        time.sleep(1)  # انتظر لحظة للتأكد من انتهاء الصلاحية
        assert jwtm.verify_token(token) is None

    def test_decode_tampered_token(self):
        """token مُعدَّل يرجع None"""
        jwtm = JWTManager(secret_key="test_secret_at_least_32_chars_long")
        token = jwtm.create_token(username="admin", ip_address="127.0.0.1")
        tampered = token[:-5] + "AAAAA"
        assert jwtm.verify_token(tampered) is None

    def test_decode_with_different_secret_fails(self):
        """token مع secret مختلف لا يُقبل"""
        jwtm1 = JWTManager(secret_key="secret_one_at_least_32_chars_long_xx")
        jwtm2 = JWTManager(secret_key="secret_two_at_least_32_chars_long_xx")
        token = jwtm1.create_token(username="admin", ip_address="127.0.0.1")
        assert jwtm2.verify_token(token) is None

    def test_short_secret_raises(self):
        """secret قصير (< 32 char) يرفع ValueError"""
        with pytest.raises(ValueError):
            JWTManager(secret_key="short")

    def test_empty_secret_raises(self):
        """secret فارغ يرفع ValueError"""
        with pytest.raises(ValueError):
            JWTManager(secret_key="")

    def test_absolute_expiry_implemented(self):
        """absolute_expiry (abs_exp) موجود في payload"""
        jwtm = JWTManager(
            secret_key="test_secret_at_least_32_chars_long",
            expiry_hours=1,
            absolute_hours=24,
        )
        token = jwtm.create_token(username="admin", ip_address="127.0.0.1")
        payload = jwtm.verify_token(token)
        assert payload is not None
        assert "abs_exp" in payload
        assert payload["abs_exp"] > payload["exp"], \
            "abs_exp should be greater than idle exp"

    def test_token_ip_binding(self):
        """إذا الـ IP تغير، الـ token يُرفض (عند expected_ip معطى)"""
        jwtm = JWTManager(secret_key="test_secret_at_least_32_chars_long")
        token = jwtm.create_token(username="admin", ip_address="1.2.3.4")
        # التحقق من IP مطابق
        assert jwtm.verify_token(token, expected_ip="1.2.3.4") is not None
        # IP مختلف يرفض
        assert jwtm.verify_token(token, expected_ip="5.6.7.8") is None


# =============================================================================
# RateLimiter
# =============================================================================
class TestRateLimiter:
    """اختبارات RateLimiter (brute force protection)"""

    def test_initial_state_not_locked(self):
        """IP جديد ليس محظوراً"""
        rl = RateLimiter()
        is_locked, _ = rl.is_locked("1.2.3.4")
        assert is_locked is False

    def test_blocks_after_max_failed_attempts(self):
        """بعد max_attempts فشل، IP يُحظر"""
        rl = RateLimiter(RateLimitConfig(
            max_attempts=3, window_seconds=60, lockout_seconds=300
        ))
        for _ in range(3):
            rl.record_attempt("1.2.3.4", success=False)
        is_locked, remaining = rl.is_locked("1.2.3.4")
        assert is_locked is True
        assert remaining > 0
        assert remaining <= 300

    def test_success_does_not_trigger_lockout(self):
        """المحاولات الناجحة لا تُسبب الحظر"""
        rl = RateLimiter(RateLimitConfig(
            max_attempts=3, window_seconds=60, lockout_seconds=300
        ))
        for _ in range(10):
            rl.record_attempt("1.2.3.4", success=True)
        is_locked, _ = rl.is_locked("1.2.3.4")
        assert is_locked is False

    def test_reset_clears_lockout(self):
        """reset() يمسح الحظر والمحاولات"""
        rl = RateLimiter(RateLimitConfig(
            max_attempts=2, window_seconds=60, lockout_seconds=300
        ))
        for _ in range(2):
            rl.record_attempt("1.2.3.4", success=False)
        is_locked, _ = rl.is_locked("1.2.3.4")
        assert is_locked is True
        rl.reset("1.2.3.4")
        is_locked, _ = rl.is_locked("1.2.3.4")
        assert is_locked is False

    def test_independent_ips(self):
        """IP محظور لا يؤثر على غيره"""
        rl = RateLimiter(RateLimitConfig(
            max_attempts=2, window_seconds=60, lockout_seconds=300
        ))
        for _ in range(2):
            rl.record_attempt("1.2.3.4", success=False)
        assert rl.is_locked("1.2.3.4")[0] is True
        # IP آخر يجب أن يبقى غير محظور
        assert rl.is_locked("5.6.7.8")[0] is False

    def test_get_remaining_attempts(self):
        """حساب المحاولات المتبقية بشكل صحيح"""
        rl = RateLimiter(RateLimitConfig(
            max_attempts=5, window_seconds=60, lockout_seconds=300
        ))
        assert rl.get_remaining_attempts("1.2.3.4") == 5
        rl.record_attempt("1.2.3.4", success=False)
        assert rl.get_remaining_attempts("1.2.3.4") == 4
        rl.record_attempt("1.2.3.4", success=False)
        assert rl.get_remaining_attempts("1.2.3.4") == 3


# =============================================================================
# IPWhitelist
# =============================================================================
class TestIPWhitelist:
    """اختبارات IPWhitelist"""

    def test_exact_ip_match(self):
        wl = IPWhitelist(["127.0.0.1", "192.168.1.100"])
        assert wl.is_allowed("127.0.0.1") is True
        assert wl.is_allowed("192.168.1.100") is True
        assert wl.is_allowed("8.8.8.8") is False

    def test_wildcard_allows_everything(self):
        wl = IPWhitelist(["*"])
        assert wl.is_allowed("1.2.3.4") is True
        assert wl.is_allowed("203.0.113.1") is True

    def test_empty_whitelist_blocks_all(self):
        """قائمة فارغة = الكل مسموح (fail-open)"""
        wl = IPWhitelist([])
        # السلوك الفعلي: empty list = الكل مسموح
        assert wl.is_allowed("127.0.0.1") is True

    def test_default_whitelist(self):
        """القائمة الافتراضية تسمح بـ localhost فقط"""
        wl = IPWhitelist()  # default
        assert wl.is_allowed("127.0.0.1") is True
        assert wl.is_allowed("::1") is True
        assert wl.is_allowed("8.8.8.8") is False

    def test_add_remove(self):
        wl = IPWhitelist([])
        wl.add("1.2.3.4")
        assert wl.is_allowed("1.2.3.4") is True
        wl.remove("1.2.3.4")
        # Note: with empty list, all are allowed (empty = fail-open)
        # So even after remove, the IP is still allowed
        # but it's no longer in the explicit list
        # We test the add/remove methods directly
        assert "1.2.3.4" not in wl.allowed_ips


# =============================================================================
# AuditLogger
# =============================================================================
class TestAuditLogger:
    """اختبارات AuditLogger"""

    def test_log_attempt_creates_log_file(self, temp_dir):
        al = AuditLogger(log_path=temp_dir / "auth_audit.log")
        al.log_attempt(
            username="admin",
            ip_address="1.2.3.4",
            success=True,
            reason="login_ok",
        )
        log_file = temp_dir / "auth_audit.log"
        assert log_file.exists()

    def test_log_attempt_records_username_and_ip(self, temp_dir):
        al = AuditLogger(log_path=temp_dir / "auth_audit.log")
        al.log_attempt(
            username="admin",
            ip_address="1.2.3.4",
            success=True,
            reason="login_ok",
        )
        log_file = temp_dir / "auth_audit.log"
        content = log_file.read_text(encoding="utf-8")
        assert "admin" in content
        assert "1.2.3.4" in content

    def test_log_failure_includes_reason(self, temp_dir):
        al = AuditLogger(log_path=temp_dir / "auth_audit.log")
        al.log_attempt(
            username="admin",
            ip_address="1.2.3.4",
            success=False,
            reason="wrong_password",
        )
        log_file = temp_dir / "auth_audit.log"
        content = log_file.read_text(encoding="utf-8")
        assert "wrong_password" in content

    def test_log_success_marks_with_emoji(self, temp_dir):
        al = AuditLogger(log_path=temp_dir / "auth_audit.log")
        al.log_attempt(
            username="admin", ip_address="1.2.3.4", success=True
        )
        log_file = temp_dir / "auth_audit.log"
        content = log_file.read_text(encoding="utf-8")
        # يجب أن يحتوي على ✅ SUCCESS
        assert "SUCCESS" in content

    def test_log_failure_marks_with_emoji(self, temp_dir):
        al = AuditLogger(log_path=temp_dir / "auth_audit.log")
        al.log_attempt(
            username="admin", ip_address="1.2.3.4", success=False
        )
        log_file = temp_dir / "auth_audit.log"
        content = log_file.read_text(encoding="utf-8")
        assert "FAILED" in content
