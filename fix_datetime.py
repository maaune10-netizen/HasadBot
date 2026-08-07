#!/usr/bin/env python3
"""
HasadBot DateTime Fixer
يصلح مشكلة datetime في كل المشروع automatically
"""
import os
import re
import shutil
from pathlib import Path
from hasad_bot.datetime_utils import datetime, now, now_timestamp
# ألوان للطباعة
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.END}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.END}")

def print_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.END}")

def print_info(msg):
    print(f"{Colors.BLUE}ℹ {msg}{Colors.END}")

class DateTimeFixer:
    def __init__(self, project_path):
        self.project_path = Path(project_path)
        self.backup_dir = self.project_path / f"backup_{now().strftime('%Y%m%d_%H%M%S')}"
        self.stats = {
            'files_processed': 0,
            'files_modified': 0,
            'replacements': 0,
            'errors': 0
        }
        
    def create_backup(self):
        """إنشاء backup قبل التعديل"""
        print_info(f"إنشاء backup في: {self.backup_dir}")
        try:
            shutil.copytree(
                self.project_path,
                self.backup_dir,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', 'venv', 'env', 'backup_*')
            )
            print_success("تم إنشاء backup بنجاح")
            return True
        except Exception as e:
            print_error(f"فشل إنشاء backup: {e}")
            return False
    
    def find_python_files(self):
        """البحث عن كل ملفات Python"""
        python_files = []
        for root, dirs, files in os.walk(self.project_path):
            # تجاهل المجلدات غير المهمة
            dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', 'venv', 'env', 'backup_*']]
            
            for file in files:
                if file.endswith('.py'):
                    file_path = Path(root) / file
                    # تجاهل ملفات backup
                    if 'backup_' not in str(file_path):
                        python_files.append(file_path)
        
        return python_files
    
    def fix_file(self, file_path):
        """إصلاح ملف واحد"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            replacements_made = 0
            
            # Pattern 1: استبدال import datetime
            pattern1 = r'^import\s+datetime\s*$'
            replacement1 = 'from hasad_bot.datetime_utils import now, now_timestamp, format_datetime, datetime, timedelta'
            if re.search(pattern1, content, re.MULTILINE):
                content = re.sub(pattern1, replacement1, content, flags=re.MULTILINE)
                replacements_made += 1
            
            # Pattern 2: استبدال from datetime import datetime
            pattern2 = r'^from\s+datetime\s+import\s+datetime\s*$'
            replacement2 = 'from hasad_bot.datetime_utils import datetime, now, now_timestamp'
            if re.search(pattern2, content, re.MULTILINE):
                content = re.sub(pattern2, replacement2, content, flags=re.MULTILINE)
                replacements_made += 1

            # Pattern 3: استبدال from datetime import datetime, ...
            pattern3 = r'^from\s+datetime\s+import\s+datetime,\s*(.+)$'
            def replacement3(match):
                other_imports = match.group(1).strip()
                return f'from hasad_bot.datetime_utils import datetime, now, now_timestamp, {other_imports}'
            if re.search(pattern3, content, re.MULTILINE):
                content = re.sub(pattern3, replacement3, content, flags=re.MULTILINE)
                replacements_made += 1
            
            # Pattern 4: استبدال now()
            pattern4 = r'\bdatetime\.datetime\.now\(\)'
            replacement4 = 'now()'
            count4 = len(re.findall(pattern4, content))
            if count4 > 0:
                content = re.sub(pattern4, replacement4, content)
                replacements_made += count4
            
            # Pattern 5: استبدال datetime.now() (بس مش في سطر الـ import)
            # نتأكد إنه مش جزء من import statement
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                if 'import' not in line and 'datetime.now()' in line:
                    line = line.replace('now()', 'now()')
                    replacements_made += 1
                new_lines.append(line)
            content = '\n'.join(new_lines)
            
            # Pattern 6: إضافة import now_timestamp إذا كان موجود في الكود
            if 'now_timestamp' in content and 'from hasad_bot.datetime_utils import' in content:
                # تأكد من وجود now_timestamp في الـ imports
                import_pattern = r'(from hasad_bot\.datetime_utils import [^)\n]+)'
                def add_now_timestamp(match):
                    import_line = match.group(1)
                    if 'now_timestamp' not in import_line:
                        # أضف now_timestamp قبل نهاية الـ import
                        return import_line + ', now_timestamp'
                    return import_line
                content = re.sub(import_pattern, add_now_timestamp, content)
            
            # حفظ الملف إذا تم التعديل
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.stats['files_modified'] += 1
                self.stats['replacements'] += replacements_made
                return True, replacements_made
            
            return False, 0
            
        except Exception as e:
            print_error(f"خطأ في معالجة {file_path}: {e}")
            self.stats['errors'] += 1
            return False, 0
    
    def create_datetime_utils_in_project(self):
        """إنشاء ملف datetime_utils.py في مجلد hasad_bot"""
        hasad_bot_dir = self.project_path / 'hasad_bot'
        
        # تأكد من وجود المجلد
        if not hasad_bot_dir.exists():
            print_error(f"مجلد hasad_bot غير موجود في: {self.project_path}")
            print_info("جرب تحدد مسار المشروع الصحيح")
            return False
        
        datetime_utils_path = hasad_bot_dir / 'datetime_utils.py'
        
        # اقرأ محتوى الملف اللي أنشأناه
        source_file = Path(__file__).parent / 'datetime_utils.py'
        
        if not source_file.exists():
            print_error("ملف datetime_utils.py مش موجود!")
            return False
        
        try:
            shutil.copy(source_file, datetime_utils_path)
            print_success(f"تم إنشاء {datetime_utils_path}")
            return True
        except Exception as e:
            print_error(f"فشل نسخ datetime_utils.py: {e}")
            return False
    
    def update_utils_file(self):
        """تحديث ملف utils.py لإعادة تصدير الـ functions"""
        utils_path = self.project_path / 'hasad_bot' / 'utils.py'
        
        if not utils_path.exists():
            print_warning("ملف utils.py غير موجود")
            return False
        
        try:
            with open(utils_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # تحقق إذا كان التحديث موجود
            if 'from hasad_bot.datetime_utils import' in content:
                print_info("utils.py محدّث مسبقاً")
                return True
            
            # أضف في أول الملف
            export_code = '''
# Re-export datetime utilities
from hasad_bot.datetime_utils import (
    now,
    now_riyadh,
    now_timestamp,
    format_datetime,
    parse_datetime,
    datetime,
    timedelta
)

'''
            content = export_code + content
            
            with open(utils_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print_success("تم تحديث utils.py")
            return True
            
        except Exception as e:
            print_error(f"فشل تحديث utils.py: {e}")
            return False
    
    def run(self):
        """تشغيل عملية الإصلاح الكاملة"""
        print_info("=" * 60)
        print_info("HasadBot DateTime Fixer - بسم الله نبدأ!")
        print_info("=" * 60)
        print()
        
        # 1. إنشاء backup
        if not self.create_backup():
            print_error("توقف البرنامج - فشل إنشاء backup")
            return
        print()
        
        # 2. إنشاء datetime_utils.py
        print_info("الخطوة 2: إنشاء datetime_utils.py...")
        if not self.create_datetime_utils_in_project():
            print_error("توقف البرنامج - فشل إنشاء datetime_utils.py")
            return
        print()
        
        # 3. تحديث utils.py
        print_info("الخطوة 3: تحديث utils.py...")
        self.update_utils_file()
        print()
        
        # 4. البحث عن الملفات
        print_info("الخطوة 4: البحث عن ملفات Python...")
        python_files = self.find_python_files()
        print_info(f"تم العثور على {len(python_files)} ملف")
        print()
        
        # 5. إصلاح الملفات
        print_info("الخطوة 5: إصلاح الملفات...")
        for file_path in python_files:
            self.stats['files_processed'] += 1
            modified, count = self.fix_file(file_path)
            
            if modified:
                relative_path = file_path.relative_to(self.project_path)
                print_success(f"{relative_path} - تم ({count} تعديل)")
        
        print()
        print_info("=" * 60)
        print_info("النتائج النهائية:")
        print_info("=" * 60)
        print_success(f"الملفات المعالجة: {self.stats['files_processed']}")
        print_success(f"الملفات المعدلة: {self.stats['files_modified']}")
        print_success(f"عدد التعديلات: {self.stats['replacements']}")
        if self.stats['errors'] > 0:
            print_error(f"الأخطاء: {self.stats['errors']}")
        print()
        print_success("تم الانتهاء بنجاح! 🎉")
        print_info(f"Backup موجود في: {self.backup_dir}")
        print()

def main():
    print()
    print_info("مرحباً! هذا البرنامج راح يصلح مشكلة datetime في مشروع HasadBot")
    print()
    
    # اطلب مسار المشروع
    project_path = input("أدخل مسار المشروع (اتركه فاضي إذا كنت في مجلد المشروع): ").strip()
    
    if not project_path:
        project_path = os.getcwd()
    
    project_path = Path(project_path).resolve()
    
    if not project_path.exists():
        print_error(f"المسار غير موجود: {project_path}")
        return
    
    print_info(f"مسار المشروع: {project_path}")
    print()
    
    # تأكيد
    confirm = input("هل أنت متأكد من المتابعة؟ (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y', 'نعم']:
        print_warning("تم الإلغاء")
        return
    
    print()
    
    # تشغيل الإصلاح
    fixer = DateTimeFixer(project_path)
    fixer.run()

if __name__ == "__main__":
    main()