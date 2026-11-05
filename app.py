from flask import Flask, request, jsonify, render_template
import sqlite3
import os
import json
from datetime import datetime

app = Flask(__name__)
DATABASE = os.path.join(os.path.dirname(__file__), 'devices.db')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            model TEXT,
            brand TEXT,
            android_version TEXT,
            sdk_int TEXT,
            app_version TEXT,
            protected INTEGER DEFAULT 0,
            has_root INTEGER DEFAULT 0,
            has_accessibility INTEGER DEFAULT 0,
            last_seen TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS protection_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            action TEXT,  -- "protect" or "restore"
            steps_json TEXT,  -- JSON array of step results
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            skip_count INTEGER DEFAULT 0,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/')
def admin_panel():
    return render_template('admin.html')

@app.route('/api/report', methods=['POST'])
def report_device():
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'No data'}), 400

    device_id = data.get('device_id')
    if not device_id:
        return jsonify({'status': 'error', 'message': 'No device_id'}), 400

    conn = get_db()
    conn.execute('''
        INSERT INTO devices 
        (device_id, model, brand, android_version, sdk_int, app_version, 
         protected, has_root, has_accessibility, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(device_id) DO UPDATE SET
            model=excluded.model,
            brand=excluded.brand,
            android_version=excluded.android_version,
            sdk_int=excluded.sdk_int,
            app_version=excluded.app_version,
            protected=excluded.protected,
            has_root=excluded.has_root,
            has_accessibility=excluded.has_accessibility,
            last_seen=excluded.last_seen
    ''', (
        device_id,
        data.get('model', ''),
        data.get('brand', ''),
        data.get('android_version', ''),
        data.get('sdk_int', ''),
        data.get('app_version', ''),
        1 if data.get('protected') else 0,
        1 if data.get('has_root') else 0,
        1 if data.get('has_accessibility') else 0,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ))
    conn.commit()
    conn.close()

    return jsonify({'status': 'ok'})

@app.route('/api/protection-details', methods=['POST'])
def report_protection_details():
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'No data'}), 400

    device_id = data.get('device_id')
    action = data.get('action', 'protect')
    steps = data.get('steps', [])
    
    success_count = sum(1 for s in steps if s.get('success'))
    skip_count = sum(1 for s in steps if s.get('note', '').lower() in ('пропуск', 'skipped'))
    fail_count = len(steps) - success_count

    conn = get_db()
    conn.execute('''
        INSERT INTO protection_history (device_id, action, steps_json, success_count, fail_count, skip_count)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        device_id,
        action,
        json.dumps(steps, ensure_ascii=False),
        success_count,
        fail_count - skip_count,
        skip_count
    ))
    conn.commit()
    conn.close()

    return jsonify({'status': 'ok'})

@app.route('/api/devices', methods=['GET'])
def get_devices():
    conn = get_db()
    devices = conn.execute('SELECT * FROM devices ORDER BY last_seen DESC').fetchall()
    conn.close()

    result = []
    for d in devices:
        result.append({
            'id': d['id'],
            'device_id': d['device_id'],
            'model': d['model'],
            'brand': d['brand'],
            'android_version': d['android_version'],
            'sdk_int': d['sdk_int'],
            'app_version': d['app_version'],
            'protected': bool(d['protected']),
            'has_root': bool(d['has_root']),
            'has_accessibility': bool(d['has_accessibility']),
            'last_seen': d['last_seen'],
            'created_at': d['created_at']
        })
    return jsonify(result)

@app.route('/api/devices/<device_id>', methods=['GET'])
def get_device_details(device_id):
    conn = get_db()
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
    if not device:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    history = conn.execute(
        'SELECT * FROM protection_history WHERE device_id = ? ORDER BY timestamp DESC LIMIT 20',
        (device_id,)
    ).fetchall()
    conn.close()

    device_data = {
        'device_id': device['device_id'],
        'model': device['model'],
        'brand': device['brand'],
        'android_version': device['android_version'],
        'sdk_int': device['sdk_int'],
        'app_version': device['app_version'],
        'protected': bool(device['protected']),
        'has_root': bool(device['has_root']),
        'has_accessibility': bool(device['has_accessibility']),
        'last_seen': device['last_seen'],
        'created_at': device['created_at'],
        'history': []
    }

    for h in history:
        steps = json.loads(h['steps_json']) if h['steps_json'] else []
        device_data['history'].append({
            'id': h['id'],
            'action': h['action'],
            'steps': steps,
            'success_count': h['success_count'],
            'fail_count': h['fail_count'],
            'skip_count': h['skip_count'],
            'timestamp': h['timestamp']
        })

    return jsonify(device_data)

@app.route('/api/devices/<device_id>', methods=['DELETE'])
def delete_device(device_id):
    conn = get_db()
    conn.execute('DELETE FROM devices WHERE device_id = ?', (device_id,))
    conn.execute('DELETE FROM protection_history WHERE device_id = ?', (device_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})

# Инициализация БД при импорте (для Gunicorn на Render)
init_db()

if __name__ == '__main__':
    # Локальный запуск (для разработки)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
