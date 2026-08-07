import sqlite3

conn = sqlite3.connect(r'C:\Users\apk_D7oomi\Desktop\new_hasad1\Hasad_Data\knowledge_db\hasad.db')
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in c.fetchall()]

print(f"Total tables: {len(tables)}\n")

empty = []
has_data = []

for t in tables:
    c.execute(f'SELECT COUNT(*) FROM [{t}]')
    count = c.fetchone()[0]
    if count == 0:
        empty.append(t)
        print(f"  EMPTY  | {t}")
    else:
        has_data.append((t, count))
        print(f"  {str(count).rjust(5)}  | {t}")

print(f"\n--- Summary ---")
print(f"Tables with data: {len(has_data)}")
print(f"Empty tables: {len(empty)}")
if empty:
    print(f"\nEmpty tables to consider deleting:")
    for t in empty:
        print(f"  - {t}")

conn.close()
