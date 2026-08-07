# AGENTS.md — HASAD Bot

Guidance for AI coding agents working in this repository. Read this before changing code.

---

## Operating Rules

**Before editing**
1. Read the target file and its direct dependencies first (including the facade it is exported from — see rule 2).
2. Before changing any public function, find all callers. Re-exports hide callers here: `handlers/__init__.py` (~100 symbols), `database/__init__.py` (`__all__`), `ai_engine/__init__.py` (module `__getattr__` lazy imports), plus widespread in-function imports for circular-dependency avoidance.
3. Check existing tests for the affected subsystem — but note the suite is mostly source-inspection regression tests; handlers, solvers, dashboard routes, login_manager, and logger have **no behavioral coverage**, so plan a live smoke test for those.
4. Do not refactor unrelated code.

**While editing**
5. Prefer the smallest correct change.
6. Preserve existing architecture (handler layers, module singletons, lazy-import pattern) unless the task explicitly requires redesign.
7. Never silently change public APIs, DB schema, callback prefixes, conversation states, or env names. When the task explicitly requires such a change: migrate every caller, update the facades/`__all__` and `main.py` registrations in the same change, update `ai_engine/selectors.py` if Dars360-related, and update this file's affected sections. No shims, aliases, or deprecated paths left behind.
8. Do not fix unrelated known issues during another task — the known-issues list in §12 exists so they can be scheduled, not bundled opportunistically.

**After editing**
9. Run targeted tests first (`python -m pytest tests/<file> -q`) from `P:/HasadBot` — the suite reads the real `.env` relative to CWD and fails without it.
10. Run the full suite (`python -m pytest tests/ -q`) when the change crosses module boundaries (handler ↔ database ↔ ai_engine ↔ main.py).
11. Inspect the change with `git diff`/`git status` before committing — the repo is under git (`main` branch, no remote). Keep commits small and message them clearly (e.g. `fix(database): correct idx_exam_cache column`).
12. Report exactly what changed, tests run, and unresolved risks.

---

## 1. Project Overview

HASAD Bot is a **Telegram bot that automatically solves homework and exams on the Dars360 e-learning platform** (a network of 11 school sites), with a full subscription economy, a reseller system, an admin panel, a secure web dashboard, and Playwright browser automation that mimics human interaction to avoid detection.

- **Language:** Python 3.14+ (also runs under 3.12), async throughout (`asyncio` + `python-telegram-bot` v20+).
- **Scale:** ~29,000 Python LOC across `main.py`, the `hasad_bot/` package (≈60 modules), and `tests/` (157 tests).
- **Platform:** Windows 10/11 primary (tested), Linux possible. `run.ps1` is the Windows control center.
- **Version:** `hasad_bot/__init__.py` → `2.5.0`. UI/banners say "V230".
- **User-facing language is Arabic (RTL).** All Telegram UI strings, menu buttons, and most docstrings/comments are Arabic. Never translate or transliterate them; keep new UI strings Arabic. Machine files stay in logical order.
- **Private project** — closed source, no external contributors. Do not commit `.env`, keys, or data.

## 2. Stack

| Concern | Technology |
|---|---|
| Telegram | `python-telegram-bot[job-queue] >=20.7,<22.0` (v20-style `Application`/`ConversationHandler`) |
| DB | `aiosqlite` (async) + stdlib `sqlite3` (knowledge base, sync) |
| Browser | `playwright` (Chromium, anti-detection, per-user fingerprinting) |
| AI | Groq (`llama-3.3-70b-versatile`) + Gemini (`google-genai`) + Qwen (`qwen/qwen3-32b` via Groq endpoint) — multi-key rotation |
| Dashboard | `fastapi` + `uvicorn` + `pydantic`, `bcrypt`, `PyJWT`, in-memory rate limiting |
| Misc | `loguru`, `tenacity`, `openpyxl`, `pyzipper`, `msoffcrypto-tool`, `httpx`, `aiohttp`, `psutil`, `hijri-converter`, `Pillow` |
| Tests | `pytest` + `pytest-asyncio` (strict mode) |

`requirements.txt` is lower-bounded, no pins. **Known gap:** `colorama` is imported by `hasad_bot/logger.py` but missing from `requirements.txt` — install it manually on a fresh machine.

## 3. Repository Layout

```
P:/HasadBot/
├── main.py                        # Entry point: CLI mode, Application builder, all handler registrations,
│                                  #   terminal listener, backup-channel remote control, encrypted exports
├── run.ps1                        # Windows control-center menu (db/cv/ex/web/log/help/exit)
├── generate_dashboard_password.py # bcrypt hash + JWT secret generator
├── fix_datetime.py                # HISTORICAL one-off migration tool — not runtime code
├── check_tables.py                # One-off inspector, hardcoded Desktop path — dead
├── commands/                      # 5 legacy scripts (ex_export, db_backup, live_log, web_dashboard,
│                                  #   cv_export) — DEAD, zero importers, superseded by main.py CLI
├── requirements.txt / .env / .env.dashboard.example / .gitignore
├── docs/
│   ├── AUDIT_2026-06-07.md        # Full codebase audit — many file paths now STALE (see §12)
│   ├── handlers_dependency_graph.md  # STALE: covers only 13 of 18 handler modules
│   └── superpowers/specs/         # Design docs from refactors
├── tests/                         # 157 pytest tests, package with conftest.py
└── hasad_bot/
    ├── config.py                  # .env loader, Config singleton, 26 conversation states, hard validation
    ├── models.py                  # UserSession dataclass (UI + session stats + persistence)
    ├── database/                  # Data layer package (facade __init__ re-exports ~80 functions)
    │   ├── pool.py                #   DatabasePool singleton + ALL 28-table schema + dead pooled-conn infra
    │   ├── init.py                #   db_init() lifecycle (pool, seeds), auto_cleanup_db()
    │   ├── users.py subscriptions.py attempts.py sessions.py notifications.py
    │   ├── unlock.py analytics.py exams.py files.py auth.py
    ├── handlers/                  # Telegram interaction layer, 18 modules (see §6)
    │   ├── constants.py infrastructure.py  # Layer 0
    │   ├── user.py homework.py exam.py onboarding.py   # Layer 1
    │   ├── login.py payment.py subscriptions.py support.py reseller.py  # Layer 2
    │   ├── admin.py admin_reseller.py unlock.py reports.py tunnel.py user_log.py announcements.py  # Layer 3
    │   └── __init__.py            # Re-exports the whole public surface (~100 symbols)
    ├── ai_engine/                 # Solving engine package (see §7)
    │   ├── selectors.py           # ★ Dars360 DOM selectors + URLs — single source of truth
    │   ├── ai_manager.py          #   AIManager: Groq/Gemini/Qwen calls + key rotation + ensemble vote
    │   ├── homework_solver.py exam_solver.py  #   God-functions (826/837 LOC each)
    │   ├── knowledge.py connection_pool.py api_clients.py exam_finish.py reports.py
    │   ├── ui.py state.py metrics.py logging.py button_helpers.py
    │   └── __init__.py            # Lazy __getattr__ imports to break circular deps
    ├── playwright_engine.py       # BrowserPool singleton + all Dars360 DOM automation (1,173 LOC)
    ├── playwright_engine/         # Shim: exec-loads the .py above (old modular files consolidated)
    │   └── diagnostics/           # Old extract-failure artifacts (current code writes to repo root /diagnostics)
    ├── login_manager.py           # Human-like multi-school login flow, CV scraping, storage_state
    ├── radar_engine.py            # Daily 20:00 VIP homework scanner (disabled by default)
    ├── web_dashboard.py           # FastAPI app, embedded HTML, 15 routes, /ws, L1 cache (2,305 LOC)
    ├── web_dashboard_auth.py      # bcrypt/JWT/rate-limit/IP-whitelist/audit auth stack
    ├── resilience.py              # CircuitBreaker + tenacity retry decorators
    ├── logger.py                  # loguru sinks (6 files), AdvancedLogger, DB event logging
    ├── utils.py                   # admin_trace, XOR password crypto, Hijri dates, error mappers, banners
    └── datetime_utils.py          # Centralized datetime (Riyadh TZ), explicit __all__
```

## 4. Architecture & Key Flows

```
Telegram Users ⇄ handlers/ (PTB v20) ⇄ database/ (aiosqlite ⇄ SQLite files)
                        ⇄ ai_engine/ (solvers ⇄ AIManager ⇄ Groq/Gemini/Qwen, key rotation)
                        ⇄ playwright_engine.py (BrowserPool ⇄ Dars360 DOM via selectors.py)
                        ⇄ login_manager.py (school login) / radar_engine.py (VIP scanner)
                        ⇄ web_dashboard.py (FastAPI subprocess, JWT auth, /ws live stats)
```

### Boot sequence (`main.py:main()` → `post_init`)
1. `init_advanced_logging()` (loguru sinks; `sys.stdout` hijacked to logger).
2. CLI gate: `python main.py backup|export-cv|extract-credentials` runs without the bot.
3. `Application.builder().token(...).post_init(post_init).build()`.
4. Register one big `ConversationHandler` (states from `config.py`), ~40 `CallbackQueryHandler`s, `PreCheckoutQueryHandler`, `SUCCESSFUL_PAYMENT`/`WEB_APP_DATA`, backup-channel `MessageHandler` (group −1), then ~17 `CommandHandler`s. **All registration lives in `main()` — never add a handler anywhere else.**
5. `post_init`: job_queue (3s dashboard stats + 6 daily announcement jobs) → `db_init()` → `init_logger(_db_pool)` → `_browser_pool.initialize()` → optional radar → admin bootstrap (owner row) → `platform_url` column migration → **dashboard launched as a detached subprocess** (`python hasad_bot/web_dashboard.py`) → success log.

### Homework solve flow (the core product)
1. User taps `🤖 حل الواجبات` → `handlers/homework.py:solve_homework` → access/credit checks (`check_access`, `get_user_remaining_homeworks`) → builds a `UserSession` (`models.py`) → `asyncio.create_task(solve_homework_logic_async(session))` (fire-and-forget; session tracked in `ai_engine.state.active_sessions[uid]`).
2. Solver: browser context per user (`_browser_pool.get_context(uid)`) → `login()` → `extract_homeworks()` (cached, re-extract every 10) → per question:
   - skip already-checked; essay → `get_gemini_answer_essay`;
   - MCQ fallback chain — **homework: Knowledge Base → Groq → Gemini(image) → Random**; **exam: exam-vote cache → Knowledge Base → Ensemble (parallel Gemini+Groq+Qwen vote) → Gemini(image) → Random**;
   - click with humanized 800–1500 ms delay; optimistic "solved = correct" counters; `solved_questions` INSERT; progress bar UI edit (3s/3q throttle).
3. Submit (JS `saveBtn`/`#confirmYes`), read platform results widget (single source of truth for correctness), deduct attempt, learn answers into knowledge DB (`scrape_answer_key`), `add_completed_homework`.

### Other flows
- **Login**: `/login` → school list (`selectors.URLS.SCHOOLS`, 11 schools) → `login_manager.unified_login` (3 retries, human typing, success heuristics) → credentials stored XOR-encrypted (`utils.encrypt_password`), per-user `storage_{uid}_{school}.json` persisted.
- **Payment**: `/shop` → plan (`PLANS` in `handlers/constants.py`: weekly 7d/25hw/10 SAR/150⭐, monthly 30d/100hw/25 SAR/350⭐, semester 120d/200hw/60 SAR/1000⭐) → Telegram Stars invoice (`PreCheckoutQueryHandler` → `successful_payment_handler` activates) or bank/STC manual transfer → admin approval flow in `handlers/subscriptions.py`.
- **Radar**: disabled unless `RADAR_ENABLED=true`; daily 20:00 scans VIP users' homework lists, sends notifications with `radar_solve:`/`radar_ignore:` buttons.
- **Backup channel**: admin posts `DB / CV / EX / LOG / STATS / FREEZE / RESTART / ...` into the backup channel to trigger encrypted exports / remote control (handler is a closure inside `main()`).

## 5. Configuration & Environment

`config.py` loads `.env` **relative to CWD** (run everything from `P:/HasadBot`), exposes a `config` singleton imported by ~every module, and **`sys.exit(1)`s** if critical vars are missing: `BOT_TOKEN`, `ADMIN_ID`, `BACKUP_PASSWORD`, `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD_HASH` (bcrypt `$2b$12$…`), `JWT_SECRET` (≥32 chars).

| Var | Purpose | Required |
|---|---|---|
| `BOT_TOKEN`, `ADMIN_ID`, `BACKUP_CHANNEL_ID` | Telegram identity | yes |
| `BACKUP_PASSWORD` | AES/zip backup encryption | yes |
| `DEFAULT_USER`, `DEFAULT_PASS` | Admin's Dars360 account | yes |
| `ADMIN_PASSWORD` | `/admin` panel password (default `hasad2026` — change it) | no |
| `MAX_FULL_ADMINS` | Cap on full admins (default 5) | no |
| `GROQ_KEY_1..N`, `GEMINI_KEY_1..N` | AI key pools (auto-discovered by prefix; rotation loops assume ≥6 Groq for Qwen) | ≥3 each in prod |
| `DASHBOARD_*` | Port (default 9000), JWT expiries (8h/24h), brute-force (5/300s→900s lockout), `DASHBOARD_ALLOWED_IPS`, `DASHBOARD_COOKIE_SECURE` | username/hash/secret yes |
| `DASHBOARD_CACHE_TTL` | L1 dashboard cache seconds (default 15) | no |
| `HASAD_DATA_DIR` | Data dir override; resolution: env → `P:\Hasad_Data` → `<project>/Hasad_Data` | no |
| `PLAYWRIGHT_HEADLESS` | `false` by default (visible browser) | no |
| `RADAR_ENABLED` | `false` by default | no |

**Never print, log, or commit real secret values.** `.env` is gitignored; only `.env.example`-style templates are whitelisted.

## 6. Telegram Layer (`handlers/`)

- **18 modules** in 4 layers; rules (from `docs/handlers_dependency_graph.md`, now stale on module count): Layer 0 (`constants.py`, `infrastructure.py`) imports nothing from handlers; cross-layer imports only bottom-up; use `TYPE_CHECKING` for type hints; no implicit re-exports.
- `handlers/__init__.py` re-exports the entire public API (~100 symbols) — **new handlers must be added there** so `from hasad_bot.handlers import X` keeps working.
- **26 conversation states** live in `config.py` (tuple unpacking `= range(26)`), re-exported via `handlers/constants.py`. The single `ConversationHandler` in `main.py` maps states → handlers.
- Command surface (all registered in `main.py`): `/start /login /admin /activate /unlock_request /help /shop /webadmin /settings /art (tunnel start) /top (tunnel stop) /ts (status) /web /dashboard /userlog /ulog /announce /cancel` + menu-button text entries (`🤖 حل الواجبات`, `🔗 ربط المنصة`, `👑 لوحة الإدارة`, `🏪 إدارة الموزعين`, `🆘 الدعم الفني`, `🎁 شارك واربح`, `📢 رسالة للكل`, `➕ إضافة واجبات`).
- Callback prefixes: `engine_`, `radar_`, `select_school:`, `request_unlock:`, `unlock_*:`, `ud:`, `ulk:`, `del:`, `back`, `link_help`, `link_nudge_back`, `view_history:`, `show_reports_list`, `view_day_report:`, `back_to_account`, `back_to_main`, `res_activate:`, `res_sel_cust:`, `res_ban:`, `shop_plan:`, `shop_pay:`, `shop_back`, `activate_request:`, `reject_request:`, `show_all_requests`, `set_days:`, `reject_reason:`, `view_request:`, `back_to_request:`, `custom_days:`, `broadcast_target:`.
- **Adding a new command**: handler function in the right layer module → export from `handlers/__init__.py` → register in `main.py` → (optionally) new state in `config.py`.
- **Known dead handler code** (exported but never registered/consumed): `exam_approve_callback`/`exam_reject_callback`, `handle_pay_stars_callback`, `handle_custom_days`, `safe_playwright_execute`, `AWAIT_ADD_HW_CHOICE` + `admin_add_hw_choice_callback` (add-homework choice branch unreachable), `add_hw_free`/`add_hw_sub` buttons produced but unhandled.

## 7. AI Engine & Browser Automation

- **`ai_engine/selectors.py` is the contract hub**: ALL Dars360 DOM selectors, URLs, the 11-school `SCHOOLS` dict, anti-detection scripts, Chromium args. Docstring mandate: *if the platform changes its UI, update only this file.*
- **`playwright_engine.py`** (module, not the shim package) owns the `BrowserPool` singleton: per-user isolated contexts, random fingerprints (18 UAs, 15 viewports), `Asia/Riyadh` timezone, storage-state persistence, anti-bot init scripts, idle cleanup (30 min idle / 6 h max), and all page helpers (`login`, `extract_homeworks`, `get_all_questions`, `submit_homework`, `extract_results`, `scrape_answer_key`).
- **Key rotation**: `AIManager` loops `config.groq_keys`/`config.gemini_keys`; 429/401/timeout → next key; first valid `Answer: N` parse wins. Qwen uses only `groq_keys[5:10]` (hard-coded). Every attempt emits `admin_trace` tags (`GROQ_TRY`, `GROQ_RATE_LIMIT`, `GEMINI_*_RATE`, …).
- **Knowledge base**: `ai_engine/knowledge.py` — lookup by image UUID then question text; option matching exact → substring → `difflib` ≥ 0.80. Learning writes `FROM_GREEN_MODEL`/`FROM_GRAY_STUDENT` rows.
- **Circular-import discipline**: `ai_engine/__init__.py` lazy-imports the solvers via module `__getattr__`; `playwright_engine._cleanup_idle_contexts` imports `active_sessions` lazily. Preserve this pattern — do not add top-level cross-imports between `ai_engine` ↔ `playwright_engine`.
- **Known bug [INFERENCE, high confidence]**: `exam_solver` calls `login(page, user, pass, school_id)` passing the school string where `playwright_engine.login` expects a numeric `user_id` for the platform-URL lookup — non-alamjad1 schools' exams may log into the wrong platform. Homework solver passes `session.user_id` correctly.

## 8. Database Layer

- **Three SQLite files** under `DATA_DIR/knowledge_db/` (default `P:\Hasad_Data`): `hasad.db` (main, 28 tables, WAL), `harvest_cv.db` (student CVs, 1 table), `hasad_knowledge_base123.db` (knowledge/answers). A stale copy of the KB db also sits inside the repo (`hasad_bot/hasad_knowledge_base123.db`) — never referenced, do not use.
- **`DatabasePool` (`database/pool.py`) is a singleton** (`__new__` guard) holding one shared aiosqlite connection per DB. The pooled-connection machinery (`get_pooled_connection`/`release_pooled_connection`, POOL_SIZE=5) is fully implemented but has **zero callers** — all ~80 data functions use `get_connection()` → the single shared handle → all writes serialize. Don't "fix" this casually; changing it is a project-scale concurrency change.
- Data functions return safe defaults on error (`False`/`{}`/`0`) — failures are swallowed by design. Every write uses `?` placeholders; timestamps are Unix floats; Hijri dates are strings.
- **Schema duplication (drift risk)**: `payment_requests` DDL exists in 3 places (pool.py, init.py, handlers/subscriptions.py); `all_messages`, `stored_images/files`, `knowledge`, and announcement tables are created outside `pool.py` too. If you change a table, check all creation sites.
- Subscriptions dual-maintain `users.expiry_ts/expiry_hijri` AND `user_subscriptions`; `is_subscribed()` checks only `users.expiry_ts`.
- Public surface is `database/__init__.py` (~80 names, `db_*` prefixed). Handlers sometimes bypass the API with raw `_db_pool.get_connection()` SQL — an established pattern.

## 9. Web Dashboard

- Single-file FastAPI app (`web_dashboard.py`), launched as a **detached subprocess** by `post_init` (port auto-find: 9000 → 8765 → 9876 → 9999 → 15000 → 18000; binds `127.0.0.1`; exposed via Cloudflare tunnel commands).
- **Auth** (`web_dashboard_auth.py`): bcrypt (cost 12) → JWT HS256 (idle 8h, absolute 24h, IP-bound) in HttpOnly cookie `hasad_session`; in-memory RateLimiter (5 fails/300 s → 900 s lockout); optional IP whitelist; AuditLogger. Middleware gates everything except public paths — **including `/ws`, which skips auth entirely** (leaks aggregated + per-user data; known issue).
- **L1 cache**: module-global `_DASHBOARD_CACHE`/`_DASHBOARD_TTL` (15 s) in front of ~20 inline SQL queries; `/ws` pushes `get_dashboard_data()` every 3 s.
- **Known issues (do not rely on)**: `/api/me` reads `exp_abs` but JWT payload key is `abs_exp` (always None); `/api/user/{id}` returns decrypted platform passwords over the wire; 500s leak `str(e)`; duplicate `set_cookie` paths (`web_dashboard.py` vs `auth.create_session_cookie`); `IPWhitelist([])` explicit-empty list fails open.

## 10. Logging & Observability

- `loguru` global `logger`; 6 sinks: stderr (INFO colorized), `hasad_main.log` (DEBUG, 100 MB rot/30 d), `hasad_errors.log`, `hasad_events.log`, `hasad_security.log`, `hasad_performance.log` — all under `DATA_DIR/logers/`.
- **`utils.admin_trace(step, detail, uid)`** is the audit trail: appends `[gregorian] [hijri] [id] [STEP] >> detail` to `logers/admin/admin_accounts_details.log` — used pervasively by the AI engine and radar. `STEP` tokens are uppercase English.
- `logger.log_event`/`update_user_stats` write DB events (`event_logs`, `user_stats`); `log_button_click` is the canonical DB button-logger.
- `init_advanced_logging()` replaces `sys.stdout/stderr` with a loguru bridge — stray `print()`s in production code land in logs.

## 11. Testing

```bash
cd P:/HasadBot
python -m pytest tests/ -q      # 157 tests; needs the real .env present
python -m pytest tests/test_resilience.py -q
```

- **CWD matters**: `config.py` reads `.env` relative to CWD — always run from `P:/HasadBot`.
- **`.env`-dependent**: `test_config.py` asserts real keys exist (BOT_TOKEN, ADMIN_ID, BACKUP_PASSWORD, ≥3 Groq/Gemini keys, dashboard security). A fresh clone without `.env` fails those 4 tests.
- Strict `@pytest.mark.asyncio` (no `asyncio_mode` config); session-scoped `event_loop` fixture in `conftest.py`.
- Two test strategies: (a) behavioral unit tests for pure modules (datetime_utils, web_dashboard_auth, resilience, ai_engine submodules, connection_pool, ui), (b) **source-inspection regression tests** (regex/AST reading production files — e.g. `test_database.py`, `test_imports_clean.py`) that pin historical bugs. Handlers, solvers, dashboard routes, login_manager, and logger have **no behavioral coverage** — when you touch them, verify by running the bot, not by leaning on the suite.
- Never mock/`patch` module-level singletons without restoring them (state leaks across tests).

## 12. Known Issues & Landmines (verified 2026-08-07)

**Fixed in the A-series (2026-08-07, commit A-series):** `idx_exam_cache` line removed — the `UNIQUE(exam_id, question_number)` constraint already auto-indexes it; `/api/me` `exp_abs` → `abs_exp`; dashboard stats job 3s → 15s; `tunnel.py` hard-coded `ADMIN_ID` deleted (was dead); `colorama` + `starlette` pin added to `requirements.txt`; `send_encrypted_file` caption fixed; `row_factory` set once at connection creation.

**Still broken / open (from `docs/AUDIT_2026-06-07.md`, re-verified):**
- `web_dashboard.py`: `/ws` unauthenticated (H9); `str(e)` leaked to clients (H7); decrypted passwords to browser (H8); two `set_cookie` paths (H2).
- `handlers/tunnel.py:32`: hard-coded `ADMIN_ID = 7606170063` — **overrides env** `ADMIN_ID` (7286004246) as "the admin" in tunnel handlers; 3 sources of truth for admin ID.
- `utils.encrypt_password` = XOR + base64 with a separate 32-byte key file — obfuscation, not encryption.
- `colorama` missing from `requirements.txt`; `send_encrypted_file` caption f-string truncated; CLI `send_db_backup` uses plain zip while channel `DB` command uses AES zip.
- `main.py`: `global_error_handler` never registered; `terminal_input_listener` + `auto_open_dashboard` are created on an event loop that is **never run** (stranded tasks — TASKS.md flags the listener for deletion); `channel_message_handler` is a non-importable closure duplicating CLI export logic.

**Stale docs (do not trust):** `docs/AUDIT_2026-06-07.md` cites `database.py`/`ai_engine.py` as monoliths — both are now packages (audit lines about them are path-stale, findings above re-verified in the new layout). `docs/handlers_dependency_graph.md` lists 13 handler modules, not 18. `README.md` describes the pre-refactor layout (no `handlers/`, `database/`, `ai_engine/` packages) and pre-dates resellers/announcements. `TASKS.md` is a historical phase log. `commands/` is dead. `fix_datetime.py`/`check_tables.py` are historical one-offs.

**Landmines:**
- **Singletons everywhere**: `config`, `_db_pool`, `_browser_pool`, `radar_engine`, `advanced_logger`, `tunnel_manager`, `CircuitBreakerRegistry`, `ai_engine.state.stats/active_sessions`. Module import order matters; add imports lazily inside functions to avoid cycles.
- **`playwright_engine/` is a shim**: the real code is `playwright_engine.py`; the package just exec-re-exports it. Don't split the module into the package without updating both.
- Two divergent AI fallback chains (homework vs exam) — intentional-looking, undocumented.
- Optimistic correctness counters inflate interim reports; only the platform results widget is authoritative.
- Two `get_total_questions_count`, two login implementations, two UI updaters (`UIManager.safe_update` vs `UserSession.update_ui`) — pick the one in the file you're editing and don't "unify" without a plan.
- Version strings disagree (V230 / v2.5 / 2.5.0).
- Arabic UI strings use emoji prefixes and RTL; keep them byte-for-byte compatible when editing (no reordering).

## 13. Change Checklist

| Change | Touches |
|---|---|
| New Telegram command/menu flow | handler module → `handlers/__init__.py` → `main.py` registration (+ state in `config.py` if conversation) |
| Dars360 platform UI changed | `ai_engine/selectors.py` ONLY |
| New DB table/column | `database/pool.py` `_create_tables` (+ check duplicate DDL sites in init.py / handlers) |
| New DB function | module in `database/` → export in `database/__init__.py` `__all__` |
| New AI provider / model | `ai_engine/ai_manager.py` (+ key env `*_KEY_n` loading in `config.py`) |
| Dashboard page/route | `web_dashboard.py` (+ auth dependency; keep `/ws` in mind) |
| New admin stat/panel | `handlers/admin.py` + `database/analytics.py` |
| New scheduled job | `post_init` in `main.py` (`job_queue.run_daily`) |
| Env var | `config.py` (+ `.env.dashboard.example` if dashboard; + `tests/test_config.py` if critical) |

After any change: run `python -m pytest tests/ -q` from `P:/HasadBot`, then smoke-test the affected flow with the live bot (`python main.py`) — the suite does not cover handlers, solvers, or dashboard routes behaviorally.
