# run.ps1 - تشغيل أوامر HASAD في Windows Terminal
#
# ✅ Auto-detect: هذا السكربت يعمل من أي مكان — يكتشف مسار المشروع تلقائياً
#    بناءً على موقعه (لا حاجة لتعديل المسار يدوياً).

# اكتشاف مسار المشروع تلقائياً (المجلد الذي يحتوي هذا السكربت)
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# اكتشاف Python تلقائياً
# نبحث في عدة مسارات محتملة ثم نستخدم `py` launcher كـ fallback
$PythonExe = $null
$PythonCandidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
)
foreach ($candidate in $PythonCandidates) {
    if (Test-Path $candidate) {
        $PythonExe = $candidate
        break
    }
}
if (-not $PythonExe) {
    # Fallback: استخدم py launcher
    $PythonExe = "py"
}

$env:PYTHONPATH = $ProjectRoot

Set-Location $ProjectRoot
$Host.UI.RawUI.WindowTitle = "🖥️ HASAD BOT - CONTROL CENTER"
$Host.UI.RawUI.BackgroundColor = "Black"
$Host.UI.RawUI.ForegroundColor = "Cyan"
Clear-Host

function Show-Menu {
    Write-Host @"
╔══════════════════════════════════════════════════════════════════════════════╗
║                         🖥️  HASAD BOT - CONTROL CENTER                       ║
║                          🤖 Enterprise Edition v2.5                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"@ -ForegroundColor Cyan
    Write-Host ""
    Write-Host "┌─────────────────────────────────────────────────────────────────────────────┐" -ForegroundColor Yellow
    Write-Host "│  📟 الأوامر المتاحة:                                                        │" -ForegroundColor Yellow
    Write-Host "│                                                                             │" -ForegroundColor Yellow
    Write-Host "│    db   - نسخة احتياطية (ترسل للقناة)                                       │" -ForegroundColor Green
    Write-Host "│    cv   - تصدير بيانات الطلاب (ترسل للقناة)                                 │" -ForegroundColor Green
    Write-Host "│    ex   - استخراج بيانات المنصة (ترسل للقناة)                               │" -ForegroundColor Green
    Write-Host "│    web  - فتح لوحة التحكم (Dashboard)                                       │" -ForegroundColor Green
    Write-Host "│    log  - مراقبة اللوج المباشر                                              │" -ForegroundColor Green
    Write-Host "│    help - عرض هذه القائمة                                                   │" -ForegroundColor Green
    Write-Host "│    exit - إغلاق التيرمينال                                                  │" -ForegroundColor Green
    Write-Host "│                                                                             │" -ForegroundColor Yellow
    Write-Host "└─────────────────────────────────────────────────────────────────────────────┘" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkCyan
    Write-Host "✅ البوت شغال في الخلفية | اكتب الأمر واضغط Enter" -ForegroundColor Green
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkCyan
    Write-Host ""
    Write-Host "📁 Project: $ProjectRoot" -ForegroundColor DarkGray
    Write-Host "🐍 Python:  $PythonExe" -ForegroundColor DarkGray
    Write-Host ""
}

function Run-DB {
    Write-Host "📦 جاري النسخ الاحتياطي..." -ForegroundColor Yellow
    & $PythonExe main.py backup
    Write-Host "✅ تم" -ForegroundColor Green
}

function Run-CV {
    Write-Host "📊 جاري تصدير بيانات الطلاب..." -ForegroundColor Yellow
    & $PythonExe main.py export-cv
    Write-Host "✅ تم" -ForegroundColor Green
}

function Run-EX {
    Write-Host "🔑 جاري استخراج بيانات المنصة..." -ForegroundColor Yellow
    & $PythonExe main.py extract-credentials
    Write-Host "✅ تم" -ForegroundColor Green
}

function Run-WEB {
    Write-Host "🌐 جاري فتح لوحة التحكم..." -ForegroundColor Yellow
    # web_dashboard.py الحقيقي في hasad_bot/
    Start-Process $PythonExe -ArgumentList "-m", "hasad_bot.web_dashboard" -WindowStyle Hidden
    Start-Sleep -Seconds 2
    Start-Process "http://127.0.0.1:9000"
    Write-Host "✅ تم فتح لوحة التحكم في المتصفح" -ForegroundColor Green
}

function Run-LOG {
    Write-Host "📝 مراقبة اللوج المباشر..." -ForegroundColor Yellow
    Write-Host "   (اضغط CTRL+C للخروج من المراقبة)" -ForegroundColor Cyan
    Write-Host ""
    # مراقبة أحدث ملف لوج في مجلد الـ logs
    $logDir = Join-Path $ProjectRoot "Hasad_Data\logers"
    if (-not (Test-Path $logDir)) {
        Write-Host "❌ مجلد اللوج غير موجود: $logDir" -ForegroundColor Red
        return
    }
    $latestLog = Get-ChildItem -Path $logDir -Filter "*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestLog) {
        Get-Content $latestLog.FullName -Wait
    } else {
        Write-Host "❌ لا توجد ملفات لوج في: $logDir" -ForegroundColor Red
    }
}

# عرض القائمة
Show-Menu

# الحلقة الرئيسية
while ($true) {
    Write-Host "`n📟 " -NoNewline -ForegroundColor Cyan
    $cmd = Read-Host

    switch ($cmd.ToLower()) {
        "db"   { Run-DB }
        "cv"   { Run-CV }
        "ex"   { Run-EX }
        "web"  { Run-WEB }
        "log"  { Run-LOG }
        "help" { Show-Menu }
        "exit" { Write-Host "👋 وداعاً!" -ForegroundColor Magenta; break }
        default {
            if ($cmd) {
                Write-Host "❌ أمر غير معروف: $cmd" -ForegroundColor Red
                Write-Host "💡 الأوامر: db, cv, ex, web, log, help, exit" -ForegroundColor Yellow
            }
        }
    }
}
