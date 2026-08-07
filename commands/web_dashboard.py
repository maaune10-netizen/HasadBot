# commands/web_dashboard.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import subprocess
import webbrowser
import time

print("🌐 جاري تشغيل لوحة التحكم...")
print("   انتظر لحظات حتى يتم التشغيل")

# تشغيل الداشبورد في الخلفية
process = subprocess.Popen(
    [sys.executable, "hasad_bot/web_dashboard.py"],
    cwd=Path(__file__).parent.parent,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

# انتظر ثواني ثم افتح المتصفح
time.sleep(3)

# فتح المتصفح
webbrowser.open("http://127.0.0.1:8000")

print("✅ تم تشغيل لوحة التحكم!")
print("   الرابط: http://127.0.0.1:8000")
print("   اضغط CTRL+C في التيرمينال لإيقاف الداشبورد")
print("   أو أغلق نافذة المتصفح")

# استمر في التشغيل حتى يضغط المستخدم Enter
input("\nاضغط Enter لإغلاق الداشبورد...")

# إغلاق الداشبورد
process.terminate()
print("✅ تم إغلاق لوحة التحكم")