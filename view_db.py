import sqlite3
from datetime import datetime
from excel_export import export_to_excel

DB_PATH = "data/inventory.db"

def view_records():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM inventory ORDER BY id DESC LIMIT 20")
    records = cursor.fetchall()

    print(f"\n{'='*80}")
    print(f"{'ВСЕГО ЗАПИСЕЙ':^80}")
    print(f"{'='*80}\n")

    for i, row in enumerate(records, 1):
        print(f"{i}. ИНВ № {row['inv_number']}")
        print(f"   Поликлиника: {row['clinic']}")
        print(f"   Кабинет: {row['cabinet']}")
        print(f"   Техника: {row['tech']}")
        print(f"   Сер. номер: {row['serial']}")
        print(f"   Добавлено: {row['created_at']}")
        print("-" * 80)

    conn.close()

if __name__ == "__main__":
    print("1. Просмотреть последние записи")
    print("2. Выгрузить в Excel")
    choice = input("\nВыберите действие (1/2): ").strip()
    
    if choice == "1":
        view_records()
        input("\nНажмите Enter для выхода...")
    elif choice == "2":
        excel_path = export_to_excel()
        if excel_path:
            print(f"\n✅ Файл создан: {excel_path}")
        input("\nНажмите Enter для выхода...")
    else:
        print("❌ Неверный выбор")