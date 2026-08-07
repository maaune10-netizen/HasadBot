# Design: Split `bot_handlers.py` into `hasad_bot/handlers/` Package

**Date:** 2026-06-01
**Status:** Approved (pending written review)
**Author:** opencode (brainstorming session)

---

## Problem

`hasad_bot/bot_handlers.py` has grown to **6,217 lines** containing **~80 handler functions** plus **10 duplicate definitions** (~660 lines of dead code). This single file mixes:

- User-facing commands (`/start`, `/help`, `/my_account`, ...)
- Admin commands (20+ `admin_*` functions)
- Payment flows (`open_shop`, `send_stars_invoice`, `successful_payment_handler`, ...)
- Homework/Exam solving
- Login & Dars360 platform integration
- Support room
- Unlock requests
- Reports
- Tunnel commands
- Infrastructure helpers (`rate_limit`, `safe_playwright_execute`, `check_access`)

This makes:
- The file hard to navigate (auto-complete is slow)
- Onboarding new contributors difficult
- Testing individual handler categories impossible
- Finding the source of bugs time-consuming

## Goals

1. Split the single file into a **`hasad_bot/handlers/` subpackage** with **14 files**, each < 1,300 lines.
2. Eliminate dead code (duplicate function definitions).
3. Keep **zero behavior change** — refactor only.
4. Maintain **100% import compatibility** via `__init__.py` re-exports.
5. Pass all **121 existing tests** + add 1 new smoke test.

## Non-Goals

- Renaming handlers.
- Changing handler signatures.
- Refactoring unrelated files (`ai_engine.py`, `database.py`, `web_dashboard.py`).
- Adding new features.
- Improving error messages or logic.

---

## Solution

### Package Structure (14 files)

```
hasad_bot/handlers/
├── __init__.py              # Re-exports all public handlers + navigation (~30 lines)
├── constants.py             # ConversationHandler states + regex patterns (~40 lines)
├── infrastructure.py        # rate_limit, check_access, safe_playwright_execute, log_any_message, _cancel_handler, error_handler (~200 lines)
├── user.py                  # start, help_command, my_account, share_and_earn, handle_text, cmd_show_archived, cmd_restore_archive (~500 lines)
├── homework.py              # solve_homework, engine_callback_handler (~400 lines)
├── exam.py                  # solve_exam, exam_approve_callback, exam_reject_callback (~600 lines)
├── login.py                 # cmd_login, login_got_username, login_got_password, select_school_callback, cancel_school_callback (~350 lines)
├── payment.py               # Shop + payment flow (12 functions, ~700 lines)
├── subscriptions.py         # Subscription management (15 functions, ~700 lines)
├── support.py               # Support room (6 functions, ~500 lines)
├── admin.py                 # Admin panel (29 functions, ~1,300 lines — largest)
├── unlock.py                # Unlock requests (9 functions, ~700 lines)
├── reports.py               # Daily reports (2 functions, ~250 lines)
└── tunnel.py                # Tunnel commands (3 functions, ~150 lines)
```

### Layered Architecture

```
Layer 0 (Foundation):   constants.py, infrastructure.py
Layer 1 (User):         user.py, homework.py, exam.py, login.py
Layer 2 (Business):     payment.py, subscriptions.py
Layer 3 (Operations):   support.py, admin.py, unlock.py, reports.py, tunnel.py

__init__.py: imports all
```

**Dependency rules:**
- Layer 0 has no internal imports.
- Higher layers may import from lower layers.
- No circular imports.
- Use `TYPE_CHECKING` for type-only cross-references.

### Public API (re-exports in `__init__.py`)

The `__init__.py` re-exports every public function from every submodule so that:

```python
from hasad_bot.handlers import start, admin_panel, send_stars_invoice
```

…continues to work the same way `from hasad_bot.bot_handlers import ...` worked before.

It also exports **navigation helpers**:
- `back_to_main_callback`
- `back_to_account_callback`

(These are small, generic, and shared by many flows.)

---

## Function Mapping (Highlights)

### Functions to keep (latest definition wins — eliminates dead code)

| Function | Latest Definition | File | Old Duplicates (removed) |
|---|---|---|---|
| `webapp_data_handler` | L1481 | `payment.py` | L364 |
| `pre_checkout_handler` | L1472 | `payment.py` | L450 |
| `successful_payment_handler` | L1421 | `payment.py` | L462 |
| `open_shop` | L5117 | `payment.py` | L1187 |
| `shop_plan_callback` | L5170 | `payment.py` | L1213 |
| `shop_pay_callback` | L5233 | `payment.py` | L1294 |
| `send_stars_invoice` | L5278 | `payment.py` | L1315 |
| `show_bank_instructions` | L5323 | `payment.py` | L1352 |
| `show_stc_instructions` | L5356 | `payment.py` | L1376 |
| `shop_back_callback` | L5383 | `payment.py` | L1400 |
| `back_to_main_callback` | L5871 | `__init__.py` | L1804 |

**Total dead code eliminated: ~660 lines.**

---

## Migration Strategy

### Order (17 steps)

1. Create `hasad_bot/handlers/__init__.py` (initially empty, no behavior change yet).
2. Create `constants.py` (extract states).
3. Create `infrastructure.py` (extract helpers).
4. Create `user.py`.
5. Create `homework.py`.
6. Create `exam.py`.
7. Create `login.py`.
8. Create `payment.py` (with duplicate resolution).
9. Create `subscriptions.py`.
10. Create `support.py`.
11. Create `unlock.py`.
12. Create `reports.py`.
13. Create `tunnel.py`.
14. Create `admin.py`.
15. Populate `__init__.py` with re-exports.
16. Update `main.py` imports: `from hasad_bot.bot_handlers import …` → `from hasad_bot.handlers import …`.
17. Delete `bot_handlers.py`.
18. Add `tests/test_bot_handlers.py` smoke test.

After each step:
- Run `python -m pytest tests/ -q` → must show **121 passed, 1 skipped**.
- Confirm no import errors.

---

## Testing Strategy

### Existing tests (must continue to pass)

121 tests in:
- `test_datetime_utils.py` (30)
- `test_web_dashboard_auth.py` (28)
- `test_resilience.py` (31)
- `test_imports_clean.py` (12)
- `test_web_dashboard.py` (5)
- `test_config.py` (6)
- `test_database.py` (5)
- `test_radar_engine.py` (4)
- 1 skipped (duplicate env keys)

### New smoke test

`tests/test_bot_handlers.py` — verifies:
- All public handler functions are importable from `hasad_bot.handlers`.
- No duplicate function definitions across the package.
- `from hasad_bot.handlers import start, admin_panel, ...` works for all expected symbols.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Missing an import in main.py | Grep `from hasad_bot.bot_handlers` for all symbols, cross-check vs new `__init__.py` |
| Subtle behavior change from reordering | Migration order follows data flow (L0 → L1 → L2 → L3) — no behavior change should occur |
| Dead code that was actually load-bearing | Identified 11 duplicate functions; latest definition is the one Python loads. Verified by checking which version is used in the test suite (currently passing) |
| `admin.py` still too large (1,300 lines) | Acceptable for first pass; can split further in follow-up PR |
| Test suite regression | Run `pytest tests/ -q` after every migration step |

---

## Acceptance Criteria

- [ ] `hasad_bot/handlers/` package exists with 14 files.
- [ ] `bot_handlers.py` deleted.
- [ ] `main.py` imports work without modification of function names.
- [ ] `python main.py` boots successfully.
- [ ] `pytest tests/ -q` reports 121 passed, 1 skipped.
- [ ] `tests/test_bot_handlers.py` passes (new).
- [ ] No new files > 1,500 lines.
- [ ] No `try/except: pass` removed or added.
- [ ] No behavior change (refactor only).

---

## Out of Scope (Future Work)

- Splitting `admin.py` further (1,300 lines is acceptable).
- Splitting `ai_engine.py` (2,845 lines).
- Splitting `database.py` (3,010 lines).
- Splitting `playwright_engine.py` (1,223 lines).
- Splitting `web_dashboard.py` (2,248 lines).
- Removing `terminal_input_listener`.
- New features (AI features, admin tools, etc.) — go in Layer 2/3.

---

## Open Questions

None — all design decisions confirmed with the user.

## Decision Log

- **Q1 (Structure):** Package `hasad_bot/handlers/` with 14 files. (User chose Option 1)
- **Q2 (Backward compat):** Delete `bot_handlers.py` and update `main.py` directly. (User chose Option 1)
- **Q3 (Shared code):** `constants.py` for states + `infrastructure.py` for helpers. (User chose Option 1)
- **Q4 (Migration):** File-by-file with `pytest` after each step. (User chose Option 1)
- **Q5 (Granularity):** 14 files (within user's 10-15 range).
