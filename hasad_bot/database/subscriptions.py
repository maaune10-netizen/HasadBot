#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Subscription plans, user subscriptions, license keys, and active-subscription lookup.

Upgrades over v1:
  - Plan caching: plans are static data, cached in-memory (invalidated on db_init_plans)
  - Subscription caching: per-user dict with 30s TTL (invalidated on create/activate)
  - Atomic key activation: UPDATE WHERE used=0 + affected_rows check (race-safe)
  - Transaction safety: db_activate_key uses aiosqlite transaction context
  - Secure key generation: secrets module (CSPRNG) instead of random.choices
  - Legacy fallback preserved with deprecation warning
"""
import time
import secrets
import string
from typing import Optional, Dict, List
from datetime import datetime

import aiosqlite
from loguru import logger

from hasad_bot.config import config
from hasad_bot.utils import now_hijri, gregorian_to_hijri
from hasad_bot.datetime_utils import now_timestamp
from .pool import db_pool


# ==============================================================================
# Plan cache (plans are static — they never change after db_init_plans)
# ==============================================================================

_plan_cache: Dict[str, Dict] = {}
_plan_cache_loaded: bool = False

PLAN_TTL = 3600  # 1 hour, but invalidated immediately on db_init_plans


def _invalidate_plan_cache():
    """Clear plan cache (called after db_init_plans or plan changes)."""
    global _plan_cache, _plan_cache_loaded
    _plan_cache.clear()
    _plan_cache_loaded = False


def _set_plan_cache(plan_id: str, plan: Dict):
    global _plan_cache, _plan_cache_loaded
    _plan_cache[plan_id] = plan
    _plan_cache_loaded = True


# ==============================================================================
# Subscription cache (per-user, 30s TTL — subscriptions change infrequently)
# ==============================================================================

_sub_cache: Dict[int, Dict] = {}
_sub_cache_ts: Dict[int, float] = {}

SUB_CACHE_TTL = 30.0  # seconds


def _invalidate_sub_cache(uid: int = None):
    """Clear subscription cache for one user, or all users if uid is None."""
    if uid is None:
        _sub_cache.clear()
        _sub_cache_ts.clear()
    else:
        _sub_cache.pop(uid, None)
        _sub_cache_ts.pop(uid, None)


def _get_sub_cache(uid: int) -> Optional[Dict]:
    """Return cached subscription if fresh, else None."""
    ts = _sub_cache_ts.get(uid)
    if ts and (time.time() - ts) < SUB_CACHE_TTL:
        return _sub_cache.get(uid)
    return None


def _set_sub_cache(uid: int, result: Optional[Dict]):
    """Cache a subscription result (including None — to avoid repeated misses)."""
    _sub_cache[uid] = result
    _sub_cache_ts[uid] = time.time()


# ==============================================================================
# Plans
# ==============================================================================

async def db_init_plans():
    """إدخال خطط الاشتراك الأساسية + cache invalidation"""
    conn = await db_pool.get_connection()

    plans = [
        ("weekly", "اسبوعي", 10, 7, 25, "7 أيام + 25 واجب"),
        ("monthly", "شهري", 25, 30, 100, "30 يوم + 100 واجب"),
        ("semester", "ترم", 60, 90, 200, "3 شهور + 200 واجب")
    ]

    for plan in plans:
        await conn.execute("""
            INSERT OR IGNORE INTO subscription_plans
            (plan_id, name, price, days, max_homeworks, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, plan)

    await conn.commit()
    _invalidate_plan_cache()
    logger.info("✅ خطط الاشتراك تم إدخالها")


async def get_plan_by_id(plan_id: str) -> Optional[Dict]:
    """جلب خطة بالمعرف (with plan cache)"""
    # Check cache first
    if plan_id in _plan_cache:
        return _plan_cache[plan_id]

    conn = await db_pool.get_connection()
    conn.row_factory = aiosqlite.Row
    async with conn.execute(
        "SELECT * FROM subscription_plans WHERE plan_id = ? AND is_active = 1",
        (plan_id,)
    ) as c:
        row = await c.fetchone()
        plan = dict(row) if row else None

    if plan:
        _set_plan_cache(plan_id, plan)

    return plan


async def get_all_plans() -> List[Dict]:
    """جلب كل الخطط النشطة"""
    conn = await db_pool.get_connection()
    conn.row_factory = aiosqlite.Row
    async with conn.execute(
        "SELECT * FROM subscription_plans WHERE is_active = 1 ORDER BY price"
    ) as c:
        plans = [dict(row) for row in await c.fetchall()]

    # Populate plan cache while we're at it
    for plan in plans:
        _set_plan_cache(plan['plan_id'], plan)

    return plans


def _get_plan_name_from_days(days_left: float) -> str:
    """الحصول على اسم الخطة من عدد الأيام المتبقية"""
    if days_left <= 7:
        return "⚡ اسبوعي"
    elif days_left <= 30:
        return "👑 شهري"
    else:
        return "🚀 ترم"


# ==============================================================================
# User subscription
# ==============================================================================

async def create_user_subscription(uid: int, plan_id: str, start_date: float, end_date: float) -> bool:
    """إنشاء اشتراك جديد للمستخدم في جدول user_subscriptions"""
    try:
        plan = await get_plan_by_id(plan_id)
        if not plan:
            logger.warning(f"⚠️ الخطة {plan_id} غير موجودة، استخدام قيم افتراضية")
            _plan_defaults = {"weekly": 25, "monthly": 100, "semester": 200}
            max_homeworks = _plan_defaults.get(plan_id, 25)
        else:
            max_homeworks = plan['max_homeworks']

        conn = await db_pool.get_connection()

        await conn.execute("""
            UPDATE user_subscriptions SET is_active = 0
            WHERE user_id = ? AND is_active = 1
        """, (uid,))

        await conn.execute("""
            INSERT INTO user_subscriptions
            (user_id, plan_id, start_date, end_date, max_homeworks, homeworks_used, is_active)
            VALUES (?, ?, ?, ?, ?, 0, 1)
        """, (uid, plan_id, start_date, end_date, max_homeworks))

        await conn.commit()

        # Invalidate subscription cache (subscription just changed)
        _invalidate_sub_cache(uid)

        logger.info(f"✅ تم إنشاء اشتراك للمستخدم {uid}: {plan_id}, {max_homeworks} واجب")
        return True

    except Exception as e:
        logger.error(f"❌ فشل إنشاء اشتراك للمستخدم {uid}: {e}")
        return False


async def get_user_subscription(uid: int) -> Optional[Dict]:
    """الحصول على تفاصيل اشتراك المستخدم (with subscription cache)"""

    # 1. Check cache
    cached = _get_sub_cache(uid)
    if cached is not None:
        # Re-check expiry against cached result (it may have expired since cache was set)
        if 'expiry_ts' in cached and cached['expiry_ts'] > time.time():
            return cached
        elif 'expiry_ts' not in cached:
            return cached
        else:
            _invalidate_sub_cache(uid)
            # Fall through to DB query

    # 2. Query DB
    result = await _get_user_subscription_from_db(uid)

    # 3. Cache result (including None to avoid repeated misses)
    _set_sub_cache(uid, result)

    return result


async def _get_user_subscription_from_db(uid: int) -> Optional[Dict]:
    """Actual DB query for subscription (called by cached get_user_subscription)."""
    try:
        conn = await db_pool.get_connection()
        conn.row_factory = aiosqlite.Row

        async with conn.execute("""
            SELECT
                us.plan_id,
                us.start_date,
                us.end_date,
                us.max_homeworks,
                us.homeworks_used,
                us.is_active,
                sp.name as plan_name
            FROM user_subscriptions us
            LEFT JOIN subscription_plans sp ON us.plan_id = sp.plan_id
            WHERE us.user_id = ? AND us.is_active = 1
            ORDER BY us.end_date DESC
            LIMIT 1
        """, (uid,)) as c:
            row = await c.fetchone()

            now_ts = time.time()

            if row:
                end_date = row['end_date']

                if end_date < now_ts:
                    return None

                days_left = (end_date - now_ts) / 86400
                expiry_datetime = datetime.fromtimestamp(end_date)
                expiry_hijri = gregorian_to_hijri(expiry_datetime)

                return {
                    'plan_id': row['plan_id'],
                    'plan_name': row['plan_name'] or _get_plan_name_from_days(days_left),
                    'start_date': row['start_date'],
                    'end_date': end_date,
                    'expiry_ts': end_date,
                    'expiry_hijri': expiry_hijri,
                    'days_left': int(days_left),
                    'max_homeworks': row['max_homeworks'],
                    'homeworks_used': row['homeworks_used'] or 0,
                    'remaining': row['max_homeworks'] - (row['homeworks_used'] or 0)
                }

    except Exception as e:
        logger.error(f"Error getting user subscription: {e}")

    # Legacy fallback (users with old expiry_ts in users table, no user_subscriptions row)
    from .users import db_get_user
    u = await db_get_user(uid)
    if not u:
        return None

    now_ts = now_timestamp()
    expiry_ts = u.get('expiry_ts', 0)

    if expiry_ts > now_ts:
        days_left = (expiry_ts - now_ts) / 86400
        plan_name = _get_plan_name_from_days(days_left)
        max_homeworks = {"⚡ اسبوعي": 25, "👑 شهري": 100, "🚀 ترم": 200}.get(plan_name, 25)

        return {
            'plan_id': 'legacy',
            'plan_name': plan_name,
            'expiry_ts': expiry_ts,
            'expiry_hijri': u.get('expiry_hijri', '—'),
            'days_left': int(days_left),
            'max_homeworks': max_homeworks,
            'homeworks_used': u.get('homeworks_used', 0)
        }

    return None


# ==============================================================================
# License keys (CSPRNG + atomic activation)
# ==============================================================================

_CHARS = string.ascii_uppercase + string.digits

async def db_create_keys(count: int, days: int) -> List[str]:
    """Generate license keys using cryptographically secure randomness."""
    new_keys = []
    conn = await db_pool.get_connection()
    now_h = now_hijri()

    for _ in range(count):
        # CSPRNG: secrets.choice instead of random.choices
        seg = lambda: ''.join(secrets.choice(_CHARS) for _ in range(5))
        k = f"HASAD-{seg()}-{seg()}-{seg()}"
        await conn.execute(
            "INSERT OR IGNORE INTO license_keys(key_code,days,created_hijri) VALUES(?,?,?)",
            (k, days, now_h)
        )
        new_keys.append(k)

    await conn.commit()
    logger.info(f"🔑 Generated {len(new_keys)} keys ({days}d)")
    return new_keys


async def db_activate_key(uid: int, key: str, name: str) -> Dict:
    """
    Activate a license key with transaction safety.

    Upgrades:
      - Atomic claim: UPDATE WHERE used=0 + check affected_rows (race-safe)
      - Full transaction: all DB writes in one transaction, rolled back on failure
      - No separate db_get_user / db_set_user calls inside the transaction
    """
    key = key.upper()
    conn = await db_pool.get_connection()
    now = time.time()

    # --- 1. Atomically claim the key (race-safe: only one winner) ---
    async with conn.execute(
        "SELECT days FROM license_keys WHERE key_code=? AND used=0",
        (key,)
    ) as c:
        row = await c.fetchone()

    if not row:
        return {"success": False, "msg": "❌ المفتاح غير موجود أو مستخدم مسبقاً."}

    days = row[0]

    # Try to claim atomically
    async with conn.execute(
        "UPDATE license_keys SET used=1, used_by=?, used_hijri=? WHERE key_code=? AND used=0",
        (uid, now_hijri(), key)
    ) as c:
        affected = c.rowcount

    if affected == 0:
        # Race: another user claimed it between SELECT and UPDATE
        return {"success": False, "msg": "❌ المفتاح غير موجود أو مستخدم مسبقاً."}

    # --- 2. Calculate new expiry (add to existing if still active) ---
    async with conn.execute(
        "SELECT expiry_ts FROM users WHERE telegram_id=?", (uid,)
    ) as c:
        u = await c.fetchone()

    cur_exp = u[0] if u and u[0] else 0
    if cur_exp < now:
        cur_exp = now

    new_exp = cur_exp + days * 86400
    exp_h = gregorian_to_hijri(datetime.fromtimestamp(new_exp))

    # --- 3. Update user + create subscription in one transaction ---
    try:
        await conn.execute(
            "UPDATE users SET name=?, expiry_ts=?, expiry_hijri=?, vip_status=1 WHERE telegram_id=?",
            (name, new_exp, exp_h, uid)
        )

        # Deactivate old subscriptions
        await conn.execute(
            "UPDATE user_subscriptions SET is_active=0 WHERE user_id=? AND is_active=1",
            (uid,)
        )

        # Determine plan_id
        if days <= 7:
            plan_id = "weekly"
        elif days <= 30:
            plan_id = "monthly"
        else:
            plan_id = "semester"

        # Get max_homeworks from plan (cached)
        plan = await get_plan_by_id(plan_id)
        max_hw = plan['max_homeworks'] if plan else 25

        # Insert new subscription
        await conn.execute("""
            INSERT INTO user_subscriptions
            (user_id, plan_id, start_date, end_date, max_homeworks, homeworks_used, is_active)
            VALUES (?, ?, ?, ?, ?, 0, 1)
        """, (uid, plan_id, cur_exp, new_exp, max_hw))

        await conn.commit()
    except Exception as e:
        await conn.rollback()
        logger.error(f"❌ Key activation failed during DB write: {e}")
        return {"success": False, "msg": f"❌ فشل التفعيل: {e}"}

    # Invalidate caches
    _invalidate_sub_cache(uid)

    logger.info(f"🔑 Key {key} activated for user {uid} ({days}d)")
    return {"success": True, "msg": f"✅ تم التفعيل لمدة {days} يوم.\nالانتهاء: {exp_h}"}


# ==============================================================================
# Reseller keys
# ==============================================================================

import secrets
import string


def _generate_reseller_key_code() -> str:
    """Generate a reseller key in format RES-XXXXX-XXXXX-XXXXX"""
    chars = string.ascii_uppercase + string.digits
    parts = [''.join(secrets.choice(chars) for _ in range(5)) for _ in range(3)]
    return f"RES-{parts[0]}-{parts[1]}-{parts[2]}"


async def generate_reseller_key(reseller_id: int, plan_type: str) -> dict:
    """
    Generate a reseller key. Deducts credit from reseller's wallet.
    Returns: {success, key_code, msg}
    """
    from .attempts import get_reseller_credit, deduct_reseller_credit, get_reseller_credit_price
    from .users import db_get_user

    # Get plan details
    plan = await get_plan_by_id(plan_type)
    if not plan:
        return {"success": False, "key_code": None, "msg": "❌ خطة غير موجودة"}

    # Get credit cost
    credit_cost = await get_reseller_credit_price(plan_type)
    if credit_cost <= 0:
        return {"success": False, "key_code": None, "msg": "❌ سعر الخطة غير محدد"}

    # Check reseller credit
    credit = await get_reseller_credit(reseller_id)
    if credit < credit_cost:
        return {
            "success": False,
            "key_code": None,
            "msg": f"❌ رصيدك غير كافٍ!\n💳 لديك: {credit} credit\n💰 تحتاج: {credit_cost} credit"
        }

    # Deduct credit
    ok = await deduct_reseller_credit(
        reseller_id, credit_cost,
        details=f"Generated key for {plan_type} ({plan['name']})"
    )
    if not ok:
        return {"success": False, "key_code": None, "msg": "❌ فشل خصم الرصيد"}

    # Generate key
    key_code = _generate_reseller_key_code()
    from .pool import db_pool
    conn = await db_pool.get_connection()

    try:
        await conn.execute(
            """INSERT INTO reseller_keys
               (key_code, reseller_id, plan_type, homeworks, days, used)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (key_code, reseller_id, plan_type, plan['max_homeworks'], plan['days'])
        )
        await conn.commit()

        return {
            "success": True,
            "key_code": key_code,
            "msg": f"✅ تم توليد المفتاح!\n\n🔑 `{key_code}`\n📦 الخطة: {plan['name']}\n💳 تم خصم: {credit_cost} credit\n💰 متبقي: {credit - credit_cost} credit"
        }
    except Exception as e:
        return {"success": False, "key_code": None, "msg": f"❌ خطأ في إنشاء المفتاح: {e}"}


async def activate_reseller_key(user_id: int, key_code: str, user_name: str = "") -> dict:
    """
    Activate a reseller key for a user.
    Returns: {success, msg}
    """
    from .pool import db_pool
    from .attempts import get_remaining_homeworks

    conn = await db_pool.get_connection()

    # Find the key
    cursor = await conn.execute(
        "SELECT reseller_id, plan_type, homeworks, days, used FROM reseller_keys WHERE key_code = ?",
        (key_code,)
    )
    row = await cursor.fetchone()

    if not row:
        return {"success": False, "msg": "❌ المفتاح غير موجود"}

    reseller_id, plan_type, homeworks, days, used = row

    if used:
        return {"success": False, "msg": "❌ المفتاح مستخدم بالفعل"}

    # Activate subscription (reuse existing logic)
    result = await db_activate_key(user_id, key_code, user_name)

    if result['success']:
        # Mark key as used
        now = time.time()
        await conn.execute(
            "UPDATE reseller_keys SET used = 1, used_by = ?, used_at = ? WHERE key_code = ?",
            (user_id, now, key_code)
        )
        await conn.commit()

        # Update user's referred_by_reseller
        await conn.execute(
            "UPDATE users SET referred_by_reseller = ? WHERE telegram_id = ? AND referred_by_reseller IS NULL",
            (reseller_id, user_id)
        )
        await conn.commit()

    return result


async def get_reseller_keys(reseller_id: int, used: int = None) -> list:
    """Get reseller's keys. If used is None, return all."""
    conn = await db_pool.get_connection()
    if used is not None:
        cursor = await conn.execute(
            """SELECT key_code, plan_type, homeworks, days, used, used_by, created_at, used_at
               FROM reseller_keys WHERE reseller_id = ? AND used = ?
               ORDER BY created_at DESC""",
            (reseller_id, used)
        )
    else:
        cursor = await conn.execute(
            """SELECT key_code, plan_type, homeworks, days, used, used_by, created_at, used_at
               FROM reseller_keys WHERE reseller_id = ?
               ORDER BY created_at DESC""",
            (reseller_id,)
        )
    return await cursor.fetchall()
