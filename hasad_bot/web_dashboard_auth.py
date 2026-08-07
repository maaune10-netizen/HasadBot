#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HASAD Bot - Dashboard Authentication Module
وحدة مصادقة احترافية للوحة التحكم

Features:
- bcrypt password hashing
- JWT session tokens (HttpOnly cookies)
- In-memory rate limiting (brute force protection)
- Session timeout (idle + absolute)
- Audit logging (login attempts)
- IP whitelisting
"""

import os
import sys
import time
import secrets
import hashlib
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timedelta

# تأكد من إضافة المجلد الرئيسي للمسار
sys.path.insert(0, str(Path(__file__).parent.parent))

import bcrypt
import jwt
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from loguru import logger

try:
    from hasad_bot.config import config
    from hasad_bot.utils import now_hijri
except ImportError as e:
    logger.error(f"Failed to import config/utils: {e}")
    raise


# ==============================================================================
# Constants - تم نقلها من hardcoded إلى config
# ==============================================================================

# Cookie names
COOKIE_NAME = "hasad_session"
CSRF_COOKIE_NAME = "hasad_csrf"

# JWT settings
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "hasad-bot-dashboard"


# ==============================================================================
# Password Hashing (bcrypt)
# ==============================================================================

class PasswordManager:
    """إدارة كلمات المرور باستخدام bcrypt"""

    @staticmethod
    def hash_password(plain_password: str) -> str:
        """
        تشفير كلمة المرور باستخدام bcrypt
        Returns: hashed string (bcrypt format)
        """
        if not plain_password or len(plain_password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        التحقق من كلمة المرور مقابل الـ hash
        Returns: True if match, False otherwise
        """
        if not plain_password or not hashed_password:
            return False
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8")
            )
        except (ValueError, TypeError) as e:
            logger.warning(f"Password verification error: {e}")
            return False

    @staticmethod
    def needs_rehash(hashed_password: str) -> bool:
        """التحقق إذا كان الـ hash يحتاج إعادة تشفير (cost قديم)"""
        try:
            # bcrypt cost factor 12 = $2b$12$
            return hashed_password.startswith("$2b$10$") or hashed_password.startswith("$2a$10$")
        except Exception:
            return True


# ==============================================================================
# JWT Token Management
# ==============================================================================

class JWTManager:
    """إدارة JWT tokens"""

    def __init__(self, secret_key: str, expiry_hours: int = 8, absolute_hours: int = 24):
        if not secret_key or len(secret_key) < 32:
            raise ValueError("JWT secret key must be at least 32 characters")
        self.secret_key = secret_key
        self.expiry_seconds = expiry_hours * 3600
        self.absolute_seconds = absolute_hours * 3600

    def create_token(self, username: str, ip_address: str) -> str:
        """
        إنشاء JWT token جديد
        - issued_at: وقت الإنشاء
        - expires_at: انتهاء الجلسة (idle timeout)
        - absolute_exp: انتهاء مطلق (يجب إعادة تسجيل دخول)
        """
        now = int(time.time())
        payload = {
            "sub": username,
            "iat": now,
            "exp": now + self.expiry_seconds,  # idle timeout
            "abs_exp": now + self.absolute_seconds,  # absolute timeout
            "ip": ip_address,
            "iss": JWT_ISSUER,
            "jti": secrets.token_hex(16),  # unique token id
        }
        return jwt.encode(payload, self.secret_key, algorithm=JWT_ALGORITHM)

    def verify_token(self, token: str, expected_ip: Optional[str] = None) -> Optional[Dict]:
        """
        التحقق من صلاحية الـ token
        Returns: payload dict if valid, None otherwise
        """
        if not token:
            return None
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[JWT_ALGORITHM],
                issuer=JWT_ISSUER,
            )

            # التحقق من absolute expiration
            now = int(time.time())
            if payload.get("abs_exp", 0) < now:
                logger.warning(f"Token expired (absolute): user={payload.get('sub')}")
                return None

            # التحقق من IP (اختياري - يمكن تعطيله)
            if expected_ip and payload.get("ip") != expected_ip:
                logger.warning(
                    f"Token IP mismatch: token_ip={payload.get('ip')}, "
                    f"current_ip={expected_ip}"
                )
                return None

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Token expired (idle)")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None

    def get_remaining_seconds(self, payload: Dict) -> int:
        """حساب الثواني المتبقية قبل انتهاء الـ idle timeout"""
        return max(0, payload.get("exp", 0) - int(time.time()))


# ==============================================================================
# Rate Limiter (Brute Force Protection)
# ==============================================================================

@dataclass
class RateLimitConfig:
    """إعدادات Rate Limiting"""
    max_attempts: int = 5  # عدد المحاولات
    window_seconds: int = 300  # النافذة الزمنية (5 دقائق)
    lockout_seconds: int = 900  # مدة الحظر (15 دقيقة)
    cleanup_interval: int = 3600  # تنظيف كل ساعة


class RateLimiter:
    """
    مانع Brute Force - in-memory
    للإنتاج الكبير، يُفضل استخدام Redis
    """

    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()
        # {ip_address: [(timestamp, success), ...]}
        self._attempts: Dict[str, List[Tuple[float, bool]]] = defaultdict(list)
        # {ip_address: unlock_timestamp}
        self._lockouts: Dict[str, float] = {}
        self._last_cleanup = time.time()

    def _cleanup_old(self):
        """تنظيف السجلات القديمة"""
        now = time.time()
        if now - self._last_cleanup < self.config.cleanup_interval:
            return

        cutoff = now - self.config.window_seconds
        # تنظيف المحاولات القديمة
        for ip in list(self._attempts.keys()):
            self._attempts[ip] = [
                (ts, success) for ts, success in self._attempts[ip]
                if ts > cutoff
            ]
            if not self._attempts[ip]:
                del self._attempts[ip]

        # تنظيف الحظر المنتهي
        for ip in list(self._lockouts.keys()):
            if self._lockouts[ip] < now:
                del self._lockouts[ip]

        self._last_cleanup = now

    def is_locked(self, ip_address: str) -> Tuple[bool, int]:
        """
        التحقق إذا كان الـ IP محظور
        Returns: (is_locked, seconds_remaining)
        """
        self._cleanup_old()
        unlock_time = self._lockouts.get(ip_address, 0)
        now = time.time()
        if unlock_time > now:
            return True, int(unlock_time - now)
        return False, 0

    def record_attempt(self, ip_address: str, success: bool) -> None:
        """تسجيل محاولة تسجيل دخول"""
        now = time.time()
        self._attempts[ip_address].append((now, success))

        # إذا فشلت، نتحقق من عدد المحاولات
        if not success:
            cutoff = now - self.config.window_seconds
            recent_failures = sum(
                1 for ts, success in self._attempts[ip_address]
                if ts > cutoff and not success
            )
            if recent_failures >= self.config.max_attempts:
                self._lockouts[ip_address] = now + self.config.lockout_seconds
                logger.warning(
                    f"🔒 IP locked out: {ip_address} "
                    f"({recent_failures} failed attempts)"
                )

    def get_remaining_attempts(self, ip_address: str) -> int:
        """عدد المحاولات المتبقية قبل الحظر"""
        self._cleanup_old()
        cutoff = time.time() - self.config.window_seconds
        recent_failures = sum(
            1 for ts, success in self._attempts[ip_address]
            if ts > cutoff and not success
        )
        return max(0, self.config.max_attempts - recent_failures)

    def reset(self, ip_address: str) -> None:
        """إعادة تعيين محاولات IP (بعد تسجيل دخول ناجح)"""
        if ip_address in self._attempts:
            del self._attempts[ip_address]
        if ip_address in self._lockouts:
            del self._lockouts[ip_address]


# ==============================================================================
# Audit Logger (Login Attempts)
# ==============================================================================

class AuditLogger:
    """تسجيل محاولات تسجيل الدخول في ملف + console"""

    def __init__(self, log_path: Path = None):
        self.log_path = log_path or Path(config.log_dir) / "dashboard_auth.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_attempt(
        self,
        username: str,
        ip_address: str,
        success: bool,
        reason: str = ""
    ):
        """تسجيل محاولة تسجيل دخول"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "✅ SUCCESS" if success else "❌ FAILED"
        reason_text = f" | Reason: {reason}" if reason else ""

        log_line = (
            f"[{timestamp}] {status} | "
            f"User: {username} | IP: {ip_address}"
            f"{reason_text}\n"
        )

        # كتابة في الملف
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

        # طباعة في الكونسول (بدون بيانات حساسة)
        if success:
            logger.info(f"🔐 Dashboard login: {username} from {ip_address}")
        else:
            logger.warning(f"⚠️ Failed dashboard login: {username} from {ip_address} - {reason}")


# ==============================================================================
# IP Whitelist (Optional Security Layer)
# ==============================================================================

class IPWhitelist:
    """قائمة IP مسموح لها بالوصول"""

    def __init__(self, allowed_ips: List[str] = None):
        # قائمة افتراضية: localhost فقط
        self.allowed_ips = set(allowed_ips or [
            "127.0.0.1",
            "::1",
            "localhost",
        ])

    def is_allowed(self, ip_address: str) -> bool:
        """التحقق إذا كان IP مسموح"""
        if not self.allowed_ips:
            return True  # إذا القائمة فارغة، الكل مسموح
        if "*" in self.allowed_ips:
            return True  # wildcard: الكل مسموح
        return ip_address in self.allowed_ips

    def add(self, ip_address: str):
        """إضافة IP للقائمة البيضاء"""
        self.allowed_ips.add(ip_address)

    def remove(self, ip_address: str):
        """إزالة IP من القائمة البيضاء"""
        self.allowed_ips.discard(ip_address)


# ==============================================================================
# Authentication Manager (Facade)
# ==============================================================================

class AuthManager:
    """
    المدير الرئيسي للمصادقة
    يجمع كل المكونات معاً
    """

    def __init__(self):
        # التحقق من الإعدادات المطلوبة
        if not config.dashboard_username:
            raise ValueError(
                "❌ CRITICAL: DASHBOARD_USERNAME not set in .env file!\n"
                "Add: DASHBOARD_USERNAME=your_username"
            )

        if not config.dashboard_password_hash:
            raise ValueError(
                "❌ CRITICAL: DASHBOARD_PASSWORD_HASH not set in .env file!\n"
                "Generate hash with: python generate_dashboard_password.py"
            )

        # تهيئة المكونات
        self.password_manager = PasswordManager()
        self.jwt_manager = JWTManager(
            secret_key=config.jwt_secret,
            expiry_hours=config.jwt_expiry_hours,
            absolute_hours=config.jwt_absolute_hours,
        )
        self.rate_limiter = RateLimiter(RateLimitConfig(
            max_attempts=config.max_login_attempts,
            window_seconds=config.login_window_seconds,
            lockout_seconds=config.login_lockout_seconds,
        ))
        self.audit_logger = AuditLogger()
        self.ip_whitelist = IPWhitelist(config.dashboard_allowed_ips)

        logger.success("✅ AuthManager initialized successfully")

    def get_client_ip(self, request: Request) -> str:
        """الحصول على IP العميل (مع مراعاة Proxy headers)"""
        # إذا خلف reverse proxy
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        return request.client.host if request.client else "unknown"

    async def authenticate(
        self,
        username: str,
        password: str,
        request: Request
    ) -> Tuple[bool, str, Optional[str]]:
        """
        محاولة تسجيل الدخول
        Returns: (success, message, token)
        """
        ip = self.get_client_ip(request)

        # 1. فحص Rate Limit
        is_locked, remaining = self.rate_limiter.is_locked(ip)
        if is_locked:
            msg = f"⛔ محظور مؤقتاً. حاول بعد {remaining} ثانية"
            self.audit_logger.log_attempt(username, ip, False, "rate_limited")
            return False, msg, None

        # 2. فحص IP Whitelist
        if not self.ip_whitelist.is_allowed(ip):
            msg = "⛔ الوصول مرفوض من هذا الـ IP"
            self.audit_logger.log_attempt(username, ip, False, "ip_not_allowed")
            logger.warning(f"🚫 Blocked IP: {ip}")
            return False, msg, None

        # 3. التحقق من اسم المستخدم
        if not secrets.compare_digest(username, config.dashboard_username):
            self.rate_limiter.record_attempt(ip, False)
            self.audit_logger.log_attempt(username, ip, False, "invalid_username")
            return False, "❌ اسم المستخدم أو كلمة المرور غير صحيحة", None

        # 4. التحقق من كلمة المرور (bcrypt)
        if not self.password_manager.verify_password(
            password, config.dashboard_password_hash
        ):
            self.rate_limiter.record_attempt(ip, False)
            remaining = self.rate_limiter.get_remaining_attempts(ip)
            self.audit_logger.log_attempt(username, ip, False, "invalid_password")
            msg = "❌ اسم المستخدم أو كلمة المرور غير صحيحة"
            if remaining > 0 and remaining <= 2:
                msg += f" (متبقي {remaining} محاولة)"
            return False, msg, None

        # 5. نجاح! إنشاء token
        token = self.jwt_manager.create_token(username, ip)
        self.rate_limiter.reset(ip)
        self.audit_logger.log_attempt(username, ip, True)

        return True, "✅ تم تسجيل الدخول بنجاح", token

    async def verify_session(self, request: Request) -> Optional[Dict]:
        """
        التحقق من session العميل
        Returns: token payload if valid, None otherwise
        """
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            return None
        ip = self.get_client_ip(request)
        return self.jwt_manager.verify_token(token, expected_ip=ip)

    def create_session_cookie(
        self,
        response: Response,
        token: str,
        secure: bool = False
    ) -> None:
        """
        إنشاء Cookie للجلسة
        - HttpOnly: لا يمكن قراءته من JavaScript (يمنع XSS)
        - Secure: HTTPS only (في الإنتاج)
        - SameSite: Strict (يمنع CSRF)
        """
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=self.jwt_manager.expiry_seconds,
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/",
        )

    def clear_session_cookie(self, response: Response) -> None:
        """مسح Cookie الجلسة"""
        response.delete_cookie(COOKIE_NAME, path="/")

    def get_session_status(self, payload: Dict) -> Dict:
        """معلومات عن حالة الجلسة"""
        return {
            "username": payload.get("sub"),
            "issued_at": payload.get("iat"),
            "expires_at": payload.get("exp"),
            "absolute_expires_at": payload.get("abs_exp"),
            "remaining_seconds": self.jwt_manager.get_remaining_seconds(payload),
        }


# ==============================================================================
# FastAPI Dependencies
# ==============================================================================

# Singleton instance
_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """الحصول على instance واحد من AuthManager"""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


async def require_auth(request: Request) -> Dict:
    """
    FastAPI dependency للتحقق من المصادقة
    Usage: @app.get("/api/protected", dependencies=[Depends(require_auth)])
    """
    auth = get_auth_manager()
    payload = await auth.verify_session(request)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="غير مصرح - يرجى تسجيل الدخول",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return payload


# ==============================================================================
# Startup Validation
# ==============================================================================

def validate_dashboard_security() -> Tuple[bool, List[str]]:
    """
    التحقق من إعدادات الأمان قبل البدء
    Returns: (is_valid, list_of_warnings)
    """
    warnings = []
    is_valid = True

    if not config.dashboard_username:
        warnings.append("❌ DASHBOARD_USERNAME not set in .env")
        is_valid = False

    if not config.dashboard_password_hash:
        warnings.append(
            "❌ DASHBOARD_PASSWORD_HASH not set in .env\n"
            "   Generate with: python generate_dashboard_password.py"
        )
        is_valid = False
    elif config.dashboard_password_hash.startswith("$2b$") is False and \
         config.dashboard_password_hash.startswith("$2a$") is False:
        warnings.append(
            "⚠️ DASHBOARD_PASSWORD_HASH doesn't look like a valid bcrypt hash"
        )

    if not config.jwt_secret or len(config.jwt_secret) < 32:
        warnings.append(
            "❌ JWT_SECRET must be set and at least 32 characters\n"
            "   Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
        is_valid = False

    return is_valid, warnings
