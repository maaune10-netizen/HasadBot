# commands/live_log.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import time
import os
from datetime import datetime

log_file = Path(__file__).parent.parent / "hasad_main.log"

if not log_file.exists():
    print("❌ ملف السجل غير موجود!")
    sys.exit(1)

print("📝 مراقبة اللوج المباشر")
print("=" * 60)
print(f"📂 الملف: {log_file}")
print("🔄 يتم التحديث تلقائياً...")
print("❌ اضغط CTRL+C للخروج")
print("=" * 60)
print()

# قراءة آخر 20 سطر أولاً
with open(log_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for line in lines[-20:]:
        print(line.strip())

print()
print("=" * 60)
print("⏳ انتظار تحديثات جديدة...")
print()

# مراقبة الملف للتحديثات
last_size = log_file.stat().st_size
last_position = last_size

try:
    while True:
        time.sleep(1)
        current_size = log_file.stat().st_size
        
        if current_size > last_size:
            with open(log_file, 'r', encoding='utf-8') as f:
                f.seek(last_position)
                new_content = f.read()
                if new_content:
                    for line in new_content.splitlines():
                        if line.strip():
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            print(f"[{timestamp}] {line}")
            last_position = current_size
            last_size = current_size
            
except KeyboardInterrupt:
    print("\n\n✅ تم إيقاف المراقبة")