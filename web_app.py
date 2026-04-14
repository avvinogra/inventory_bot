import os
import sqlite3
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
import config
import database as db
from excel_export import export_to_excel
from collections import Counter

app = Flask(__name__)
app.secret_key = os.urandom(24)
DB_PATH = config.DB_PATH

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _yes_no_counts_py(conn: sqlite3.Connection, column: str) -> tuple[int, int]:
    """
    Считает Да/Нет для поля, игнорируя пустые/прочие значения.

    Почему в Python: SQLite LOWER()/LIKE по умолчанию плохо работают с кириллицей.
    """
    yes_set = {"да", "yes", "y", "true", "1", "+", "установлен", "установлено", "есть"}
    no_set = {"нет", "no", "n", "false", "0", "-", "не установлен", "неустановлен"}

    yes = 0
    no = 0

    cur = conn.execute(f"SELECT {column} FROM inventory")
    for (v,) in cur.fetchall():
        if v is None:
            continue
        s = str(v).strip().lower()
        if not s:
            continue
        if s in yes_set or ("установ" in s and "не установлен" not in s and "неустанов" not in s):
            yes += 1
            continue
        if s in no_set or ("не установлен" in s) or ("неустанов" in s):
            no += 1
            continue
        # всё остальное (включая "не везде нужно указывать") не учитываем
    return yes, no

@app.route('/')
def dashboard():
    conn = get_db_connection()
    
    # Общая статистика
    total_items = conn.execute('SELECT COUNT(*) FROM inventory').fetchone()[0]
    
    # Статистика по поликлиникам
    clinic_stats = conn.execute(
        'SELECT clinic, COUNT(*) as count FROM inventory GROUP BY clinic ORDER BY count DESC'
    ).fetchall()
    
    # Статистика по типам техники
    tech_types = conn.execute(
        '''SELECT 
            CASE 
                WHEN LOWER(tech) LIKE '%системный блок%' OR LOWER(tech) LIKE '%компьютер%' THEN 'ПК'
                WHEN LOWER(tech) LIKE '%монитор%' THEN 'Монитор'
                WHEN LOWER(tech) LIKE '%ноутбук%' THEN 'Ноутбук'
                WHEN LOWER(tech) LIKE '%принтер%' OR LOWER(tech) LIKE '%мфу%' THEN 'Принтер/МФУ'
                ELSE 'Другое'
            END as tech_type,
            COUNT(*) as count
        FROM inventory 
        GROUP BY tech_type
        ORDER BY count DESC'''
    ).fetchall()
    
    drweb_yes, drweb_no = _yes_no_counts_py(conn, "drweb")
    office_yes, office_no = _yes_no_counts_py(conn, "office")
    
    # Статистика по ОС
    os_stats = conn.execute(
        '''SELECT 
            CASE 
                WHEN LOWER(os) LIKE '%windows 10%' OR LOWER(os) LIKE '%win 10%' THEN 'Windows 10'
                WHEN LOWER(os) LIKE '%windows 11%' OR LOWER(os) LIKE '%win 11%' THEN 'Windows 11'
                WHEN LOWER(os) LIKE '%windows 7%' OR LOWER(os) LIKE '%win 7%' THEN 'Windows 7'
                WHEN LOWER(os) LIKE '%linux%' THEN 'Linux'
                WHEN LOWER(os) LIKE '%mac%' THEN 'macOS'
                ELSE COALESCE(os, 'Не указано')
            END as os_name,
            COUNT(*) as count
        FROM inventory 
        GROUP BY os_name
        ORDER BY count DESC'''
    ).fetchall()
    
    # Статистика с IP и MAC
    with_network = conn.execute(
        "SELECT COUNT(*) FROM inventory WHERE ip IS NOT NULL AND ip != ''"
    ).fetchone()[0]
    
    with_mac = conn.execute(
        "SELECT COUNT(*) FROM inventory WHERE mac IS NOT NULL AND mac != ''"
    ).fetchone()[0]
    
    # Последние записи
    recent_items = conn.execute(
        'SELECT * FROM inventory ORDER BY id DESC LIMIT 10'
    ).fetchall()
    
    conn.close()
    
    # Подготовка данных для графиков
    return render_template('dashboard.html', 
                         total_items=total_items,
                         clinic_labels=[row['clinic'] for row in clinic_stats],
                         clinic_data=[row['count'] for row in clinic_stats],
                         tech_type_labels=[row['tech_type'] for row in tech_types],
                         tech_type_data=[row['count'] for row in tech_types],
                         drweb_yes=drweb_yes,
                         drweb_no=drweb_no,
                         office_yes=office_yes,
                         office_no=office_no,
                         os_labels=[row['os_name'] for row in os_stats],
                         os_data=[row['count'] for row in os_stats],
                         with_network=with_network,
                         with_mac=with_mac,
                         recent_items=recent_items,
                         clinics=config.CLINICS)

@app.route('/inventory')
def inventory():
    conn = get_db_connection()
    
    search = request.args.get('search', '')
    clinic_filter = request.args.get('clinic', '')
    
    query = "SELECT * FROM inventory WHERE 1=1"
    params = []
    
    if search:
        query += " AND (inv_number LIKE ? OR tech LIKE ? OR cabinet LIKE ? OR serial LIKE ?)"
        params.extend([f'%{search}%'] * 4)
    
    if clinic_filter:
        query += " AND clinic = ?"
        params.append(clinic_filter)
    
    query += " ORDER BY id DESC LIMIT 100"
    
    items = conn.execute(query, params).fetchall()
    conn.close()
    
    return render_template('inventory.html', 
                         items=items, 
                         clinics=config.CLINICS,
                         search=search,
                         clinic_filter=clinic_filter)

@app.route('/export')
def export():
    try:
        path = export_to_excel()
        if path:
            return send_file(path, as_attachment=True)
        else:
            return "Ошибка генерации", 400
    except Exception as e:
        return f"Ошибка: {e}", 500

@app.route('/delete/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    db.delete_item(item_id)
    return redirect(url_for('inventory'))

@app.route('/api/stats')
def api_stats():
    """API для получения статистики (можно использовать для AJAX)"""
    conn = get_db_connection()
    stats = db.get_db_stats()
    conn.close()
    return jsonify(stats)

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)