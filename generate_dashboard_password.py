#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HASAD Bot - Dashboard Password Hash Generator
أداة توليد كلمات مرور مشفرة للداشبورد

Usage:
    python generate_dashboard_password.py
    python generate_dashboard_password.py --password "MyStrongPass123!"
    python generate_dashboard_password.py --username "admin"
"""

import sys
import secrets
import argparse
import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    import bcrypt
except ImportError:
    print("❌ ERROR: bcrypt is not installed!")
    print("Install with: pip install bcrypt")
    sys.exit(1)


# ==============================================================================
# Banner
# ==============================================================================

BANNER = """
╔════════════════════════════════════════════════════════════╗
║  🔐 HASAD Bot - Dashboard Security Setup                  ║
║     مولّد كلمات المرور المشفرة                            ║
╚════════════════════════════════════════════════════════════╝
"""


def check_password_strength(password: str) -> tuple:
    """
    التحقق من قوة كلمة المرور
    Returns: (is_strong, score, feedback)
    """
    score = 0
    feedback = []

    if len(password) >= 8:
        score += 1
    else:
        feedback.append("يجب أن تكون 8 أحرف على الأقل")

    if len(password) >= 12:
        score += 1

    if any(c.islower() for c in password):
        score += 1
    else:
        feedback.append("أضف حروف صغيرة (a-z)")

    if any(c.isupper() for c in password):
        score += 1
    else:
        feedback.append("أضف حروف كبيرة (A-Z)")

    if any(c.isdigit() for c in password):
        score += 1
    else:
        feedback.append("أضف أرقام (0-9)")

    if any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        score += 1
    else:
        feedback.append("أضف رموز خاصة (!@#$%^&*)")

    # فحص القواسم المشتركة
    common = ["password", "123456", "admin", "hasad", "qwerty", "abc123"]
    if any(c in password.lower() for c in common):
        score -= 1
        feedback.append("تجنب الكلمات الشائعة")

    is_strong = score >= 5
    return is_strong, score, feedback


def generate_jwt_secret() -> str:
    """توليد JWT secret key قوي"""
    return secrets.token_hex(32)  # 64 حرف hex


def hash_password(password: str) -> str:
    """تشفير كلمة المرور بـ bcrypt"""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_hash(plain: str, hashed: str) -> bool:
    """التحقق من كلمة المرور"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def main():
    print(BANNER)

    parser = argparse.ArgumentParser(
        description="توليد كلمات مرور مشفرة للداشبورد"
    )
    parser.add_argument(
        "--username",
        help="اسم المستخدم للداشبورد",
        default=None,
    )
    parser.add_argument(
        "--password",
        help="كلمة المرور (غير آمن - يظهر في الـ history)",
        default=None,
    )
    parser.add_argument(
        "--generate-jwt",
        action="store_true",
        help="توليد JWT secret فقط",
    )
    parser.add_argument(
        "--verify",
        metavar="HASH",
        help="التحقق من كلمة مرور مقابل hash",
    )
    args = parser.parse_args()

    # =================================================================
    # توليد JWT Secret فقط
    # =================================================================
    if args.generate_jwt:
        print("🔑 JWT Secret (انسخه إلى .env):")
        print("=" * 60)
        print(f"JWT_SECRET={generate_jwt_secret()}")
        print("=" * 60)
        return

    # =================================================================
    # التحقق من hash
    # =================================================================
    if args.verify:
        print("🔍 التحقق من كلمة المرور...")
        if args.password:
            plain = args.password
        else:
            plain = getpass.getpass("أدخل كلمة المرور: ")

        if verify_hash(plain, args.verify):
            print("✅ كلمة المرور صحيحة!")
        else:
            print("❌ كلمة المرور غير صحيحة")
        return

    # =================================================================
    # توليد hash جديد
    # =================================================================

    # اسم المستخدم
    if args.username:
        username = args.username
    else:
        default_user = "admin"
        username = input(f"👤 اسم المستخدم [{default_user}]: ").strip() or default_user

    # كلمة المرور
    if args.password:
        password = args.password
        print("⚠️ تحذير: تمرير كلمة المرور كـ argument غير آمن!")
    else:
        password = getpass.getpass("🔒 كلمة المرور (لن تظهر): ").strip()
        if not password:
            print("❌ كلمة المرور لا يمكن أن تكون فارغة")
            return

    # تأكيد كلمة المرور
    if not args.password:
        password_confirm = getpass.getpass("🔒 أكد كلمة المرور: ").strip()
        if password != password_confirm:
            print("❌ كلمات المرور غير متطابقة")
            return

    # فحص القوة
    is_strong, score, feedback = check_password_strength(password)
    print(f"\n📊 قوة كلمة المرور: {score}/6", end="")
    if is_strong:
        print(" - ✅ قوية")
    else:
        print(" - ⚠️ ضعيفة")
        for f in feedback:
            print(f"   - {f}")

    if not is_strong:
        proceed = input("\nهل تريد المتابعة رغم ذلك؟ (y/N): ").strip().lower()
        if proceed not in ("y", "yes", "نعم"):
            print("❌ تم الإلغاء")
            return

    # توليد الـ hash
    print("\n⏳ جاري التشفير...")
    password_hash = hash_password(password)

    # توليد JWT secret
    jwt_secret = generate_jwt_secret()

    # عرض النتائج
    print("\n" + "=" * 60)
    print("✅ تم بنجاح! انسخ ما يلي إلى ملف .env:")
    print("=" * 60)
    print()
    print(f'DASHBOARD_USERNAME={username}')
    print(f'DASHBOARD_PASSWORD_HASH={password_hash}')
    print(f'JWT_SECRET={jwt_secret}')
    print()
    print("=" * 60)

    # اختبار سريع
    print("\n🧪 اختبار سريع...")
    if verify_hash(password, password_hash):
        print("✅ Hash verification: OK")
    else:
        print("❌ Hash verification: FAILED!")

    # إنشاء ملف .env.dashboard إذا لم يكن موجوداً
    env_file = Path(__file__).parent / ".env.dashboard.example"
    if not env_file.exists():
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(f"""# ==============================================================================
# Dashboard Security Settings
# انسخ هذه القيم إلى .env الرئيسي
# ==============================================================================

DASHBOARD_USERNAME={username}
DASHBOARD_PASSWORD_HASH=$2b$12$REPLACE_WITH_GENERATED_HASH
JWT_SECRET=REPLACE_WITH_64_CHAR_HEX_SECRET

# Session Duration (ساعات)
DASHBOARD_JWT_EXPIRY_HOURS=8
DASHBOARD_JWT_ABSOLUTE_HOURS=24

# Brute Force Protection
DASHBOARD_MAX_LOGIN_ATTEMPTS=5
DASHBOARD_LOGIN_WINDOW_SECONDS=300
DASHBOARD_LOGIN_LOCKOUT_SECONDS=900

# IP Whitelist (comma-separated, اتركها فارغة للسماح للجميع)
# DASHBOARD_ALLOWED_IPS=127.0.0.1,::1,localhost

# Session Cookie Security (true في الإنتاج مع HTTPS)
DASHBOARD_COOKIE_SECURE=false
""")
        print(f"\n📄 تم إنشاء ملف مثال: {env_file}")

    print("\n💡 نصائح:")
    print("   1. احفظ JWT_SECRET في مكان آمن")
    print("   2. لا تشارك DASHBOARD_PASSWORD_HASH مع أحد")
    print("   3. غيّر DASHBOARD_COOKIE_SECURE=true عند استخدام HTTPS")
    print("   4. لا تحفظ القيم في git - أضفها إلى .gitignore")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ تم الإلغاء بواسطة المستخدم")
        sys.exit(0)
