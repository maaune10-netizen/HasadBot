#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Payment settings + plan stars — single source of truth (database layer).

Seeds the `settings` KV store (INSERT OR IGNORE, admin values win) and the
subscription_plans.stars column (only fills missing/zero — never overwrites
admin-set values). Exposes read/update helpers used by the admin dashboard.

Defaults mirror hasad_bot.handlers.constants.PAYMENT_SETTINGS / PLANS.
"""
from typing import Dict, List, Optional

from .pool import db_pool
from .subscriptions import _invalidate_plan_cache
from .auth import db_setting, db_set_setting


# Defaults mirror hasad_bot.handlers.constants.PAYMENT_SETTINGS.
DEFAULT_PAYMENT_SETTINGS = {
    "bank_name": "الراجحي",
    "bank_account_name": "HASAD STORE",
    "bank_account_number": "SA1234567890123456789",
    "bank_iban": "SA1234567890123456789",
    "stc_phone": "05xxxxxxxx",
    "stc_notes": "أرسل المبلغ مع إرسال صورة الإيصال",
    "payment_method_bank": "1",
    "payment_method_stc": "1",
    "payment_method_stars": "1",
}

# Defaults mirror hasad_bot.handlers.constants.PLANS stars values.
DEFAULT_STARS = {"weekly": 150, "monthly": 350, "semester": 1000}

# Keys managed in the settings KV store, grouped for reads/updates.
_BANK_KEYS = ("bank_name", "bank_account_name", "bank_account_number", "bank_iban")
_STC_KEYS = ("stc_phone", "stc_notes")
_METHOD_KEYS = ("payment_method_bank", "payment_method_stc", "payment_method_stars")
_SETTING_KEYS = _BANK_KEYS + _STC_KEYS + _METHOD_KEYS

# Allowed plan columns for apply_plan_update.
_ALLOWED_PLAN_FIELDS = ("price", "days", "max_homeworks", "stars", "is_active", "name")


async def ensure_payment_settings() -> None:
    """Seed payment-settings KV + plan stars + semester reconciliation ONCE.

    Guarded by the 'payment_settings_seeded' marker: after the first successful
    seed, every later call returns immediately, so get_payment_config() stays a
    pure read on the hot path (no per-read writes → no lock collisions with the
    bot's own writes on the shared connection). On failure the transaction is
    rolled back and the marker is NOT set → the next call retries."""
    conn = await db_pool.get_connection()
    try:
        if await db_setting("payment_settings_seeded", "") == "1":
            return  # seeded already — reads only from here on

        from .subscriptions import db_init_plans
        await db_init_plans()  # INSERT OR IGNORE — لا يمسح تعديلات الأدمن

        # KV defaults — INSERT OR IGNORE (admin values win).
        for key, value in DEFAULT_PAYMENT_SETTINGS.items():
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )

        # Fill plan stars (first seed only — an admin-set 0 survives later calls).
        for plan_id, stars in DEFAULT_STARS.items():
            await conn.execute(
                "UPDATE subscription_plans SET stars = ? WHERE plan_id = ? AND (stars IS NULL OR stars = 0)",
                (stars, plan_id),
            )

        # ONE-TIME reconciliation for DBs seeded before the 90→120 semester fix.
        if (await db_setting("semester_days_reconciled", "")) == "":
            await conn.execute(
                "UPDATE subscription_plans SET days = 120 WHERE plan_id = 'semester' AND days = 90"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                ("semester_days_reconciled", "1"),
            )

        await conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            ("payment_settings_seeded", "1"),
        )
        await conn.commit()
    except Exception:
        # فشل كتابة على الاتصال المشترك يترك transaction مفتوح → قفل دائم
        try:
            await conn.rollback()
        except Exception:
            pass
        raise


async def get_payment_config() -> dict:
    """Return payment config: ALL plans (active + inactive, each with is_active),
    bank, stc, methods.

    Every value falls back to the defaults above when the DB row/key is missing.
    """
    if await db_setting("payment_settings_seeded", "") != "1":
        await ensure_payment_settings()  # first run only; afterwards pure reads
    conn = await db_pool.get_connection()
    async with conn.execute(
        "SELECT * FROM subscription_plans ORDER BY price"
    ) as c:
        plans_raw = [dict(row) for row in await c.fetchall()]
    plans: Dict[str, dict] = {}
    for p in plans_raw:
        plan_id = p["plan_id"]
        plans[plan_id] = {
            "plan_id": plan_id,
            "name": p.get("name"),
            "price": p.get("price"),
            "days": p.get("days"),
            "max_homeworks": p.get("max_homeworks"),
            "stars": p.get("stars") if p.get("stars") is not None else DEFAULT_STARS.get(plan_id, 0),
            "is_active": p.get("is_active"),
        }

    bank = {k: await db_setting(k, DEFAULT_PAYMENT_SETTINGS[k]) for k in _BANK_KEYS}
    stc = {k: await db_setting(k, DEFAULT_PAYMENT_SETTINGS[k]) for k in _STC_KEYS}
    methods = {
        "bank": (await db_setting("payment_method_bank", DEFAULT_PAYMENT_SETTINGS["payment_method_bank"])) == "1",
        "stc": (await db_setting("payment_method_stc", DEFAULT_PAYMENT_SETTINGS["payment_method_stc"])) == "1",
        "stars": (await db_setting("payment_method_stars", DEFAULT_PAYMENT_SETTINGS["payment_method_stars"])) == "1",
    }

    return {"plans": plans, "bank": bank, "stc": stc, "methods": methods}


async def apply_plan_update(plan_id: str, fields: dict) -> dict:
    """Update allowed plan fields; returns the updated row (or {} if missing)."""
    updates = {k: v for k, v in fields.items() if k in _ALLOWED_PLAN_FIELDS}

    conn = await db_pool.get_connection()
    try:
        if updates:
            assignments = ", ".join(f"{k} = ?" for k in updates)
            await conn.execute(
                f"UPDATE subscription_plans SET {assignments} WHERE plan_id = ?",
                (*updates.values(), plan_id),
            )
            await conn.commit()
            _invalidate_plan_cache()

        async with conn.execute(
            "SELECT * FROM subscription_plans WHERE plan_id = ?", (plan_id,)
        ) as c:
            row = await c.fetchone()
        return dict(row) if row else {}
    except Exception:
        try:
            await conn.rollback()
        except Exception:
            pass
        raise


async def apply_payment_settings_update(fields: dict) -> dict:
    """Apply payment-setting updates; returns {"old": ..., "new": ...} snapshots."""
    def _norm(v):
        # Method flags (payment_method_*) are stored as '1'/'0', never 'True'/'False'.
        if isinstance(v, bool):
            return "1" if v else "0"
        return str(v)

    updates = {k: _norm(v) for k, v in fields.items() if k in _SETTING_KEYS}

    conn = await db_pool.get_connection()
    try:
        old: Dict[str, str] = {}
        for key in updates:
            old[key] = await db_setting(key, DEFAULT_PAYMENT_SETTINGS.get(key, ""))
        for key, value in updates.items():
            await db_set_setting(key, value)
        new: Dict[str, str] = {}
        for key in updates:
            new[key] = await db_setting(key, DEFAULT_PAYMENT_SETTINGS.get(key, ""))

        return {"old": old, "new": new}
    except Exception:
        try:
            await conn.rollback()
        except Exception:
            pass
        raise
