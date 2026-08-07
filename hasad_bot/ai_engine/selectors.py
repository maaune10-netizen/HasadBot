"""
Centralized selectors, URLs, and CSS patterns for the Dars360 platform.

IF THE PLATFORM CHANGES ITS UI, UPDATE ONLY THIS FILE.

Usage:
    from hasad_bot.ai_engine.selectors import LOGIN, HOMEWORK, QUESTIONS, URLS
    page.locator(LOGIN.USERNAME)
    page.goto(URLS.LOGIN.format(base_url=base_url))
"""


# =============================================================================
# URLS — Platform base URLs and endpoints
# =============================================================================

class URLS:
    DEFAULT_BASE = "https://alamjad1.dars360.com"

    # Navigation endpoints (relative to base_url)
    LOGIN_PAGE = "/Common/Account/Login"
    HOMEWORK_LIST = "/Homework/Homework/StudentHomework"
    EXAM_LIST = "/Exams/Exams/StudentExams"
    PROFILE = "/Account/setting"

    # Login success patterns (URLs that indicate successful login)
    SUCCESS_URLS = ["/home", "/home/index", "/home/index2"]
    SUCCESS_URL_PATTERN = "{base}/Home/**"

    # AI API endpoints
    GROQ_API = "https://api.groq.com/openai/v1/chat/completions"
    GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    # School-specific URLs — key = school slug
    SCHOOLS = {
        "alamjad1":       {"name": "🏫 مدرسة الأمجاد 1",     "base": "https://alamjad1.dars360.com",       "login": "https://alamjad1.dars360.com/Common/Account/Login",      "profile": "https://alamjad1.dars360.com/Account/setting"},
        "alamjad2":       {"name": "🏫 مدرسة الأمجاد 2",     "base": "https://alamjad2.dars360.com",       "login": "https://alamjad2.dars360.com/Common/Account/Login",      "profile": "https://alamjad2.dars360.com/Account/setting"},
        "riyadahschool":  {"name": "🏫 مدرسة الرياض",        "base": "https://riyadahschool.dars360.com",  "login": "https://riyadahschool.dars360.com/Common/Account/Login", "profile": "https://riyadahschool.dars360.com/Account/setting"},
        "bloom":          {"name": "🏫 مدرسة bloom",         "base": "https://bloom.dars360.com",          "login": "https://bloom.dars360.com/Common/Account/Login",         "profile": "https://bloom.dars360.com/Account/setting"},
        "althuraya":      {"name": "🏫 مدرسة الثريا",        "base": "https://althuraya.dars360.com",      "login": "https://althuraya.dars360.com/Common/Account/Login",     "profile": "https://althuraya.dars360.com/Account/setting"},
        "alkhloud":       {"name": "🏫 مدرسة الخلود",        "base": "https://alkhloud.dars360.com",       "login": "https://alkhloud.dars360.com/Common/Account/Login",      "profile": "https://alkhloud.dars360.com/Account/setting"},
        "fl":             {"name": "🏫 مدرسة fl",            "base": "https://fl.dars360.com",             "login": "https://fl.dars360.com/Common/Account/Login",             "profile": "https://fl.dars360.com/Account/setting"},
        "albushra":       {"name": "🏫 مدرسة البشري",        "base": "https://albushra.dars360.com",       "login": "https://albushra.dars360.com/Common/Account/Login",      "profile": "https://albushra.dars360.com/Account/setting"},
        "alshima":        {"name": "🏫 مدرسة الشيماء",       "base": "https://alshima.dars360.com",        "login": "https://alshima.dars360.com/Common/Account/Login",       "profile": "https://alshima.dars360.com/Account/setting"},
        "atyab":          {"name": "🏫 مدرسة أطياب",         "base": "https://atyab.dars360.com",          "login": "https://atyab.dars360.com/Common/Account/Login",         "profile": "https://atyab.dars360.com/Account/setting"},
        "qyem-q":         {"name": "🏫 مدرسة قيم",           "base": "https://qyem-q.dars360.com",         "login": "https://qyem-q.dars360.com/Common/Account/Login",        "profile": "https://qyem-q.dars360.com/Account/setting"},
    }


# =============================================================================
# LOGIN — Form fields and buttons
# =============================================================================

class LOGIN:
    USERNAME = "#UserName"
    PASSWORD = "#Password"
    SUBMIT = "#BtnLogin"
    ERROR_MSG = "#loginFailmessage"
    ERROR_VISIBLE = "#loginFailmessage:visible"

    # Success verification
    SUCCESS_SELECTORS = ["#menu_ele_77", ".sitemap-wrapper", ".cardsLink"]
    SUCCESS_TEXTS = ["الرئيسية", "الواجبات الالكترونية"]


# =============================================================================
# PROFILE — Student profile page
# =============================================================================

class PROFILE:
    NAME_AR = "LocalName"
    NAME_EN = "LatinName"
    ID_NUMBER = "IdentityNo"
    PHONE = "MobileNo"
    NATIONALITY = "NationName"
    STAGE = "StudnetStage"
    GRADE = "StudnetGrade"
    CLASS = "StudnetClass"
    IMAGE = "profileImg"

    # All profile element IDs for batch extraction via page.evaluate()
    ALL_IDS = [NAME_AR, NAME_EN, ID_NUMBER, PHONE, NATIONALITY, STAGE, GRADE, CLASS]


# =============================================================================
# HOMEWORK — Card listing and extraction
# =============================================================================

class HOMEWORK:
    # Card container
    CARD = ".waiting.cmd"

    # Card inner elements (CSS selectors for page.evaluate)
    CARD_SUBJECT = "span.text-theme"          # nth(0) = subject, nth(1) = homework name
    CARD_QUESTION_COUNT = "span.text-orange"  # question count text
    CARD_START_BTN = "button[onclick*='ExecuteQuiz']"
    CARD_START_BTN_TEXT = "button:has-text('ابدأ الحل')"

    # Combined selector for start button click
    CARD_START_BTN_COMBINED = "button:has-text('ابدأ الحل'), button[onclick*='ExecuteQuiz']"

    # ID extraction from onclick attribute
    ONCLICK_ID_REGEX = r"ID=(\d+)"


# =============================================================================
# QUESTIONS — Question display and interaction
# =============================================================================

class QUESTIONS:
    # Question container
    CONTAINER = ".question:visible"
    CONTAINER_ANY = ".question"

    # Question content
    TEXT = ".question-text"
    IMAGE = "img"

    # Options
    OPTION_TEXT = ".q-option-text"
    OPTION = ".q-option"
    OPTION_CHECKED = "input.q-option:checked"

    # Essay detection
    ESSAY_INPUT = "input.form-control, input[type='text'], input[type='number'], textarea"
    ESSAY_TYPE_ID = "data-type-id"
    ESSAY_TYPE_VALUE = "4"
    ESSAY_READONLY = "input.form-control[readonly], input[readonly]"

    # Total question count
    TOTAL_COUNT = "#totalQuestionsCount"


# =============================================================================
# NAVIGATION — Page navigation buttons
# =============================================================================

class NAVIGATION:
    NEXT_PAGE = "#nextBtn:visible"
    NEXT_PAGE_TEXT = "button:has-text('التالي')"
    NEXT_PAGE_COMBINED = "#nextBtn:visible, button:has-text('التالي')"


# =============================================================================
# SUBMIT — Finish and confirm buttons
# =============================================================================

class SUBMIT:
    FINISH = "button:has-text('انهاء')"
    FINISH_HAMZA = "button:has-text('إنهاء')"
    SUBMIT = "button:has-text('تسليم')"
    FINISH_COMBINED = "button:has-text('انهاء'), button:has-text('تسليم'), button:has-text('إنهاء')"

    # Confirmation dialog
    CONFIRM_YES = "#confirmYes"

    # JS button detection (inside page.evaluate)
    JS_FINISH_KEYWORDS = ["انهاء", "تسليم", "Submit", "Finish"]
    JS_SAVE_BTN_ID = "saveBtn"


# =============================================================================
# RESULTS — Score and result extraction
# =============================================================================

class RESULTS:
    WIDGET = ".widget-digit"
    WIDGET_ALT = "#questionsCount"
    GRADE_ALT = "#markCount"

    # Result labels (parent spans)
    LABEL_QUESTIONS = "span.text-muted:has-text('عدد الاسئلة')"
    LABEL_CORRECT = "span.text-muted:has-text('الإجابات الصحيحة')"
    LABEL_WRONG = "span.text-muted:has-text('الإجابات الخاطئة')"
    LABEL_GRADE = "span.text-muted:has-text('مجموع الدرجات')"

    # Composite selectors (label + value)
    CORRECT_COUNT = "span.text-muted:has-text('الإجابات الصحيحة') + span.widget-digit"
    WRONG_COUNT = "span.text-muted:has-text('الإجابات الخاطئة') + span.widget-digit"
    GRADE_COUNT = "span.text-muted:has-text('مجموع الدرجات') + span.widget-digit, #markCount"
    QUESTION_COUNT = "span.text-muted:has-text('عدد الاسئلة') + span.widget-digit, #questionsCount"


# =============================================================================
# ANSWER_KEY — JS selectors for answer key scraping
# =============================================================================

class ANSWER_KEY:
    # Question container in answer key view
    QUESTION_CONTAINER = ".col-md-12.my-1"
    QUESTION_CONTAINER_ALT = ".question"

    # Question content
    QUESTION_TEXT = ".question-text"

    # Correct answer detection
    CORRECT_SECTION = ".text-success"
    CORRECT_INPUT = "input[checked]"
    CORRECT_INPUT_ALT = "input.text-success"
    CORRECT_ICON = ".fa-check-circle.text-success"

    # Answer text
    ANSWER_TEXT = "span.d-inline-block"

    # Essay answer
    ESSAY_READONLY_INPUTS = "input.form-control[readonly], input[readonly]"
    ESSAY_CORRECT_SECTION = ".text-success, .correct-answer"


# =============================================================================
# BUTTON_KEYWORDS — Keywords for dynamic button detection (used in button_helpers.py)
# =============================================================================

class BUTTON_KEYWORDS:
    FINISH = ["انهاء", "تسليم", "إنهاء", "Submit", "Finish", "submit", "finish"]
    NEXT = ["التالي", "Next", "next"]


# =============================================================================
# SCROLL — JavaScript scroll snippets
# =============================================================================

class SCROLL:
    TO_BOTTOM = "window.scrollTo(0, document.body.scrollHeight)"
    HALF_DOWN = "window.scrollBy({top: window.innerHeight/2, behavior: 'smooth'})"

    @staticmethod
    def center_element_js():
        return """(el) => { el.scrollIntoView({behavior:'smooth',block:'center',inline:'center'}); }"""


# =============================================================================
# ANTI_DETECT — JavaScript snippets to bypass bot detection
# =============================================================================

ANTI_DETECT_SCRIPTS = [
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
    "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]})",
    "Object.defineProperty(navigator, 'languages', {get: () => ['ar','ar-SA','en']})",
    "window.chrome = {runtime:{}, loadTimes:function(){}, csi:function(){}, app:{}}",
    """
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.call(this, parameter);
    };
    """,
    "delete window.__playwright; delete window.__pwInitScripts;",
    "Object.defineProperty(navigator, 'userAgentData', {get: () => undefined})",
]

PERMISSIONS_OVERRIDE = """(parameters) => {
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
}"""


# =============================================================================
# BROWSER — Chromium launch arguments for anti-detection
# =============================================================================

CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-web-security",
    "--disable-features=IsolateOrigins,site-per-process",
    "--start-maximized",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
]
