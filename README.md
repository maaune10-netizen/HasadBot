# 🤖 HASAD Bot V230

> **Enterprise Telegram Bot** لحل واجبات منصة Dars360 بالذكاء الاصطناعي، مع نظام اشتراكات متكامل ولوحة تحكم ويب آمنة.

[![Python](https://img.shields.io/badge/Python-3.14+-blue.svg)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg)](https://core.telegram.org/bots)
[![Tests](https://img.shields.io/badge/Tests-85%20passed-brightgreen.svg)](./tests)
[![Version](https://img.shields.io/badge/Version-2.5.0-orange.svg)](./CHANGELOG)

---

## 📋 نظرة عامة

HASAD Bot هو بوت تليجرام متكامل يقوم بـ:

- ✅ **حل الواجبات تلقائياً** عبر سلسلة Fallback ذكية: Knowledge Base → Groq AI → Gemini AI → Random
- 💳 **نظام اشتراكات** (أسبوعي، شهري، ترم) مع بوابة دفع Telegram Stars
- 🛰️ **رادار مراقبة** للواجبات الجديدة مع إشعارات فورية
- 📊 **لوحة تحكم ويب** آمنة (JWT + bcrypt + Rate Limiting)
- 🔐 **تشفير AES-256** للنسخ الاحتياطية
- 🌐 **دعم اللغة العربية** كاملاً مع التاريخ الهجري

---

## 🏗️ البنية التقنية

```
┌─────────────────┐
│  Telegram Users │ ← واجهة المستخدم
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│         HASAD Bot (main.py)            │ ← المنسق الرئيسي
│  ┌──────────┐  ┌──────────┐  ┌────────┐│
│  │ bot_     │  │ ai_      │  │ radar_ ││
│  │ handlers │  │ engine   │  │ engine ││
│  └──────────┘  └──────────┘  └────────┘│
│  ┌──────────┐  ┌──────────┐  ┌────────┐│
│  │ database │  │ config   │  │ utils  ││
│  └──────────┘  └──────────┘  └────────┘│
└─────────────────────────────────────────┘
         │
         ├─→ Dars360 (Playwright) ─┐
         ├─→ Groq API (3+ keys)   │ ← AI Fallback Chain
         ├─→ Gemini API (3+ keys) │
         └─→ Knowledge Base (SQLite)┘
```

---

## 🚀 التثبيت والتشغيل

### 1. المتطلبات الأساسية

- **Python 3.14+** ([تحميل](https://www.python.org/downloads/))
- **Windows 10/11** (تم اختباره) أو Linux
- حساب Telegram Bot من [@BotFather](https://t.me/BotFather)

### 2. تثبيت المشروع

```bash
# استنساخ المشروع
git clone <repository_url>
cd HasadBot

# إنشاء بيئة افتراضية (اختياري لكن موصى به)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# تثبيت المتطلبات
pip install -r requirements.txt
```

### 3. إعداد متغيرات البيئة

```bash
# نسخ قالب البيئة
cp .env.example .env

# تحرير .env وملء القيم المطلوبة
notepad .env  # Windows
```

**المتغيرات الإجبارية**:

| المتغير | الوصف | مثال |
|---------|-------|------|
| `BOT_TOKEN` | Token من @BotFather | `123456:ABC-DEF...` |
| `ADMIN_ID` | Telegram User ID للأدمن | `7286004246` |
| `BACKUP_PASSWORD` | كلمة مرور النسخ الاحتياطي | `StrongP@ss123` |
| `BACKUP_CHANNEL_ID` | ID قناة النسخ الاحتياطي | `-1001234567890` |
| `GROQ_KEY_1..3` | مفاتيح Groq API (3 على الأقل) | `gsk_...` |
| `GEMINI_KEY_1..3` | مفاتيح Gemini API (3 على الأقل) | `AIza...` |
| `DASHBOARD_USERNAME` | اسم مستخدم لوحة التحكم | `admin` |
| `DASHBOARD_PASSWORD_HASH` | bcrypt hash لكلمة المرور | `$2b$12$...` |
| `JWT_SECRET` | سر JWT (32+ char) | `<random hex>` |

**المتغيرات الاختيارية**:

| المتغير | الوصف | الافتراضي |
|---------|-------|-----------|
| `HASAD_DATA_DIR` | مسار مجلد البيانات (لـ portability) | `P:\Hasad_Data` أو sibling |
| `DASHBOARD_CACHE_TTL` | TTL لـ dashboard cache (ثوانٍ) | `15` |
| `DASHBOARD_ALLOWED_IPS` | قائمة IPs مسموح لها بالوصول | (فارغ = الكل) |
| `DASHBOARD_COOKIE_SECURE` | `true` لـ HTTPS فقط | `false` |

### 4. توليد كلمات المرور الآمنة

```bash
# توليد DASHBOARD_PASSWORD_HASH و JWT_SECRET
python generate_dashboard_password.py
```

**المخرجات**:
- `DASHBOARD_PASSWORD_HASH`: bcrypt hash للتسجيل في `.env`
- `JWT_SECRET`: 32+ حرف عشوائي للتسجيل في `.env`

### 5. تشغيل البوت

```bash
# تشغيل البوت الكامل
python main.py
```

**أوامر CLI (تعمل بدون بدء البوت)**:

```bash
python main.py backup             # نسخة احتياطية تُرسل للقناة
python main.py export-cv          # تصدير بيانات الطلاب
python main.py extract-credentials # استخراج بيانات المنصة
```

**سكريبت Windows (portable)**:

```powershell
.\run.ps1 db    # = python main.py backup
.\run.ps1 cv    # = python main.py export-cv
.\run.ps1 ex    # = python main.py extract-credentials
.\run.ps1 web   # تشغيل لوحة التحكم
.\run.ps1 log   # متابعة أحدث ملف لوج
.\run.ps1 help  # عرض المساعدة
```

> ملاحظة: `run.ps1` يكتشف Python تلقائياً و `$ProjectRoot` تلقائياً، فيعمل على أي جهاز دون تعديل.

### 6. مجلد البيانات (portable)

`config.py` يبحث عن مجلد البيانات بالترتيب:

1. `HASAD_DATA_DIR` في البيئة (override صريح).
2. `P:\Hasad_Data` (backward compat).
3. `<project_root>/Hasad_Data` (sibling portable — يُنشأ تلقائياً).

```bash
# نقل البيانات إلى مجلد آخر
export HASAD_DATA_DIR=/mnt/data/hasad   # Linux
$env:HASAD_DATA_DIR = "D:\HasadData"    # Windows
```

---

## 🧪 الاختبارات

```bash
# تشغيل جميع الاختبارات
python -m pytest tests/ -v

# تشغيل اختبارات ملف محدد
python -m pytest tests/test_datetime_utils.py -v

# تشغيل اختبار واحد
python -m pytest tests/test_web_dashboard_auth.py::TestPasswordManager -v
```

**النتائج الحالية**: `85 passed, 1 skipped` ✅

### بنية الاختبارات

```
tests/
├── __init__.py
├── conftest.py                  # Fixtures مشتركة
├── test_datetime_utils.py       # اختبارات الـ timezone
├── test_web_dashboard_auth.py   # اختبارات المصادقة
├── test_database.py             # regression للـ schema
├── test_radar_engine.py         # regression للـ Bug #1
├── test_imports_clean.py        # regression للـ imports
└── test_config.py               # اختبارات .env
```

---

## 🔒 الأمان

### نظام المصادقة (Dashboard)

| الميزة | التقنية |
|--------|---------|
| **تشفير كلمات المرور** | bcrypt (cost factor 12) |
| **Session Tokens** | JWT HS256 مع IP binding |
| **Cookie Security** | HttpOnly + SameSite=Strict |
| **Brute Force Protection** | Rate Limiting (5/300s) + Lockout (900s) |
| **IP Whitelist** | اختياري مع wildcard `*` |
| **Audit Logging** | كل محاولة دخول تُسجَّل |

### تشفير النسخ الاحتياطية

- **AES-256** عبر مكتبة `msoffcrypto` (Excel) و `pyzipper` (ZIP)
- كلمة المرور من `BACKUP_PASSWORD` في `.env`

### ⚠️ تنبيهات أمنية

1. **لا تشارك ملف `.env`** مع أي شخص
2. **غيّر جميع المفاتيح** قبل الإنتاج (BOT_TOKEN, GROQ_KEY, GEMINI_KEY)
3. **استخدم HTTPS** للوحة التحكم في الإنتاج
4. **فعّل IP Whitelist** في الإنتاج (لا تستخدم `*`)

---

## 📊 البنية التقنية التفصيلية

### هيكل الملفات

```
HasadBot/
├── main.py                        # البوت الرئيسي (2,059 سطر)
├── generate_dashboard_password.py # مولّد كلمات المرور
├── fix_datetime.py                # أداة إصلاح التواريخ
├── requirements.txt               # المتطلبات
├── run.ps1                        # سكريبت تشغيل Windows
├── .env                           # متغيرات البيئة (لا يُرفع)
├── .env.example                   # قالب البيئة
├── .env.dashboard.example         # قالب أمان الداشبورد
├── .gitignore                     # ملفات مستبعدة
├── README.md                      # هذا الملف
│
├── hasad_bot/                     # الحزمة الرئيسية
│   ├── __init__.py
│   ├── config.py                  # إعدادات المشروع
│   ├── database.py                # إدارة قاعدة البيانات
│   ├── datetime_utils.py          # أدوات التاريخ والوقت
│   ├── bot_handlers.py            # معالجات أوامر البوت
│   ├── ai_engine.py               # محرك الذكاء الاصطناعي
│   ├── radar_engine.py            # محرك الرادار
│   ├── playwright_engine.py       # محرك المتصفح
│   ├── web_dashboard.py           # لوحة التحكم
│   ├── web_dashboard_auth.py      # مصادقة الداشبورد
│   ├── logger.py                  # إعداد اللوج
│   └── utils.py                   # أدوات مساعدة
│
└── tests/                         # اختبارات pytest (85 اختبار)
    ├── conftest.py
    ├── test_datetime_utils.py
    ├── test_web_dashboard_auth.py
    ├── test_database.py
    ├── test_radar_engine.py
    ├── test_imports_clean.py
    └── test_config.py
```

### الـ Fallback Chain (حل الواجبات)

```python
1. Knowledge Base (SQLite)
   ↓ (إذا لم يُوجد)
2. Groq AI (Llama models)
   ↓ (إذا فشلت كل المفاتيح)
3. Gemini AI (Gemini models)
   ↓ (إذا فشلت كل المفاتيح)
4. Random Selection
```

### Database Schema

- `users` — معلومات المستخدمين والاشتراكات
- `homework_sessions` — جلسات حل الواجبات
- `logs` — لوج العمليات (بـ `telegram_id` كمعرّف)
- `knowledge_base` — قاعدة المعرفة للحلول المخزنة

---

## 🐛 الأخطاء المعروفة والحلول

| الخطأ | السبب | الحل |
|-------|-------|------|
| `BACKUP_PASSWORD not set` | متغير البيئة مفقود | أضفه إلى `.env` |
| `no such column: user_id` | خطأ في schema | ✅ مُصلَح (يستخدم `telegram_id`) |
| `cannot access local variable 'now'` | scope conflict | ✅ مُصلَح في radar loop |
| `DASHBOARD_PASSWORD_HASH not set` | لم يُولَّد بعد | شغّل `generate_dashboard_password.py` |

---

## 🛠️ التطوير

### إضافة معالج أمر جديد

```python
# 1. أضف المعالج في hasad_bot/bot_handlers.py
async def my_new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello!")

# 2. سجّل المعالج في main.py
app.add_handler(CommandHandler("mycmd", my_new_command))
```

### إضافة اختبار جديد

```python
# tests/test_my_feature.py
def test_my_feature():
    assert my_function() == expected_value
```

### معايير الكود

- **Type hints** للدوال العامة
- **Docstrings** بالعربية أو الإنجليزية
- **لا تكرار imports** في نفس الملف
- **معالجة الأخطاء** مع `logger.error()` بدلاً من `pass`
- **اختبارات** لكل ميزة جديدة

---

## 📜 الترخيص

مشروع خاص — جميع الحقوق محفوظة.

## 🤝 المساهمة

المشروع مغلق للمساهمات الخارجية حالياً.

## 📞 الدعم

- **Telegram**: [@hasad_support](https://t.me/hasad_support)
- **Issues**: [GitHub Issues](https://github.com/your-repo/issues)

---

## 🎯 خارطة الطريق

- [ ] تقسيم `bot_handlers.py` (6,217 سطر) إلى modules
- [ ] Circuit Breaker للـ APIs (Groq/Gemini)
- [ ] Connection retry logic مع exponential backoff
- [ ] Redis-based rate limiting (بدلاً من in-memory)
- [ ] WebSocket live updates للداشبورد
- [ ] Multi-language support (English/Arabic toggle)

---

**صنع بـ ❤️ بواسطة فريق HASAD**
