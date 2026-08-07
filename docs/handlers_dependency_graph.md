# hasad_bot/handlers/ — Internal Dependency Graph

```
                    ┌────────────────┐
                    │ constants.py   │  ← Layer 0
                    │ (no imports)   │
                    └────────────────┘
                            ↑ import
                    ┌────────────────┐
                    │infrastructure.py│  ← Layer 0
                    │ (no handler    │
                    │  imports)      │
                    └────────────────┘
                            ↑ import
       ┌────────────────────┼────────────────────┐
       │                    │                    │
┌──────────────┐  ┌──────────────────┐  ┌────────────────┐
│   user.py    │  │   homework.py    │  │    exam.py     │  ← Layer 1
└──────────────┘  └──────────────────┘  └────────────────┘
       │
       ↓
┌──────────────┐  ┌──────────────────┐  ┌────────────────┐
│  login.py    │  │   payment.py     │  │subscriptions.py│  ← Layer 2
└──────────────┘  └──────────────────┘  └────────────────┘
                            ↓
              ┌─────────────────────┐
              │     support.py      │
              └─────────────────────┘

       ┌──────────────┐  ┌──────────────────┐  ┌────────────────┐
       │  admin.py    │  │   unlock.py      │  │   reports.py   │  ← Layer 3
       └──────────────┘  └──────────────────┘  └────────────────┘

       ┌──────────────┐
       │  tunnel.py   │  ← Layer 3 (standalone)
       └──────────────┘

                    ┌────────────────┐
                    │  __init__.py   │  ← imports all
                    └────────────────┘
```

## Critical rules:

1. **constants.py + infrastructure.py** = Layer 0, لا يستوردان من handlers.
2. **Cross-layer imports** مسموحة فقط من الأسفل للأعلى (L0 ← L1 ← L2 ← L3).
3. **Type hints** مع `TYPE_CHECKING` لتجنب circular imports.
4. **No re-exports** ضمنياً — كل ملف يستورد صراحة.

## Specific cross-references:

- `admin.py` يستورد من: constants, infrastructure, subscriptions, unlock, support, payment, user, login, homework, exam
- `payment.py` يستورد من: constants, infrastructure, subscriptions, user
- `subscriptions.py` يستورد من: constants, infrastructure, payment
- `support.py` يستورد من: constants, infrastructure, user
- `unlock.py` يستورد من: constants, infrastructure, user, subscriptions
