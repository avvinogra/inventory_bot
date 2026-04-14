# diagnostic.py
import sqlite3

conn = sqlite3.connect("data/inventory.db")
conn.row_factory = sqlite3.Row

# Показываем ВСЕ записи
rows = conn.execute("SELECT id, clinic, inv_number, tech FROM inventory").fetchall()

print("ВСЕ ЗАПИСИ В БАЗЕ:")
print("=" * 60)
for row in rows:
    print(f"ID: {row['id']} | Клиника: '{row['clinic']}' | ИНВ: {row['inv_number']} | Техника: {row['tech']}")

conn.close()