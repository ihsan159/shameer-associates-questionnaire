import sqlite3
import os
import json
import uuid
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shameer_questionnaire.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Sessions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT UNIQUE NOT NULL,
        client_name TEXT DEFAULT '',
        email TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        current_chapter INTEGER DEFAULT 0,
        progress_percent INTEGER DEFAULT 0,
        status TEXT DEFAULT 'in_progress',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        submitted_at TIMESTAMP
    )
    ''')

    # Answers table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_token TEXT NOT NULL,
        question_id TEXT NOT NULL,
        answer_json TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(session_token, question_id),
        FOREIGN KEY(session_token) REFERENCES sessions(token) ON DELETE CASCADE
    )
    ''')

    # Family members table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS family_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_token TEXT NOT NULL,
        member_index INTEGER NOT NULL,
        user_group TEXT NOT NULL,
        count INTEGER DEFAULT 1,
        gender TEXT DEFAULT '',
        age_range TEXT DEFAULT '',
        special_note TEXT DEFAULT '',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(session_token) REFERENCES sessions(token) ON DELETE CASCADE
    )
    ''')

    # Dynamic rooms table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS dynamic_rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_token TEXT NOT NULL,
        room_id TEXT NOT NULL,
        room_name TEXT NOT NULL,
        room_type TEXT NOT NULL,
        room_index INTEGER NOT NULL,
        answers_json TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(session_token, room_id),
        FOREIGN KEY(session_token) REFERENCES sessions(token) ON DELETE CASCADE
    )
    ''')

    # Selected visual references table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS selected_visuals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_token TEXT NOT NULL,
        category TEXT NOT NULL,
        style_id TEXT NOT NULL,
        style_name TEXT NOT NULL,
        style_number TEXT NOT NULL,
        image_url TEXT DEFAULT '',
        living_image_url TEXT DEFAULT '',
        dining_image_url TEXT DEFAULT '',
        bedroom_image_url TEXT DEFAULT '',
        wardrobe_image_url TEXT DEFAULT '',
        selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(session_token, category),
        FOREIGN KEY(session_token) REFERENCES sessions(token) ON DELETE CASCADE
    )
    ''')

    # File uploads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_token TEXT NOT NULL,
        file_id TEXT UNIQUE NOT NULL,
        original_filename TEXT NOT NULL,
        stored_filename TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        category TEXT DEFAULT 'general',
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(session_token) REFERENCES sessions(token) ON DELETE CASCADE
    )
    ''')

    # Consultations table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS consultations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_token TEXT NOT NULL,
        client_name TEXT NOT NULL,
        client_email TEXT NOT NULL,
        client_phone TEXT NOT NULL,
        preferred_date TEXT NOT NULL,
        preferred_time TEXT NOT NULL,
        meeting_type TEXT DEFAULT 'In-person / Studio Consultation',
        notes TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(session_token) REFERENCES sessions(token) ON DELETE CASCADE
    )
    ''')

    conn.commit()
    conn.close()
    print("Initialized database schema successfully.")

def create_session(token=None):
    if not token:
        token = str(uuid.uuid4())
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR IGNORE INTO sessions (token, created_at, updated_at)
    VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ''', (token,))
    conn.commit()
    conn.close()
    return token

def get_session_data(token):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM sessions WHERE token = ?', (token,))
    session = cursor.fetchone()
    if not session:
        conn.close()
        return None

    session_dict = dict(session)

    # Answers
    cursor.execute('SELECT question_id, answer_json FROM answers WHERE session_token = ?', (token,))
    answers = {}
    for row in cursor.fetchall():
        try:
            answers[row['question_id']] = json.loads(row['answer_json'])
        except Exception:
            answers[row['question_id']] = row['answer_json']
    session_dict['answers'] = answers

    # Family members
    cursor.execute('SELECT * FROM family_members WHERE session_token = ? ORDER BY member_index ASC', (token,))
    family_members = [dict(row) for row in cursor.fetchall()]
    session_dict['family_members'] = family_members

    # Dynamic rooms
    cursor.execute('SELECT * FROM dynamic_rooms WHERE session_token = ? ORDER BY room_index ASC', (token,))
    dynamic_rooms = []
    for row in cursor.fetchall():
        r = dict(row)
        try:
            r['answers'] = json.loads(r['answers_json'])
        except Exception:
            r['answers'] = {}
        dynamic_rooms.append(r)
    session_dict['dynamic_rooms'] = dynamic_rooms

    # Selected visuals
    cursor.execute('SELECT * FROM selected_visuals WHERE session_token = ?', (token,))
    visuals = {}
    for row in cursor.fetchall():
        visuals[row['category']] = dict(row)
    session_dict['selected_visuals'] = visuals

    # Uploads
    cursor.execute('SELECT * FROM uploads WHERE session_token = ? ORDER BY uploaded_at DESC', (token,))
    uploads = [dict(row) for row in cursor.fetchall()]
    session_dict['uploads'] = uploads

    # Consultation
    cursor.execute('SELECT * FROM consultations WHERE session_token = ? ORDER BY created_at DESC LIMIT 1', (token,))
    consultation = cursor.fetchone()
    session_dict['consultation'] = dict(consultation) if consultation else None

    conn.close()
    return session_dict

def save_answers(token, answers_dict, current_chapter=None, progress_percent=None):
    conn = get_db()
    cursor = conn.cursor()

    client_name = answers_dict.get('client_name')
    email = answers_dict.get('email_address')
    phone = answers_dict.get('contact_number')

    update_fields = ['updated_at = CURRENT_TIMESTAMP']
    update_vals = []

    if client_name:
        update_fields.append('client_name = ?')
        update_vals.append(client_name)
    if email:
        update_fields.append('email = ?')
        update_vals.append(email)
    if phone:
        update_fields.append('phone = ?')
        update_vals.append(phone)
    if current_chapter is not None:
        update_fields.append('current_chapter = ?')
        update_vals.append(current_chapter)
    if progress_percent is not None:
        update_fields.append('progress_percent = ?')
        update_vals.append(progress_percent)

    update_vals.append(token)
    cursor.execute(f"UPDATE sessions SET {', '.join(update_fields)} WHERE token = ?", update_vals)

    for qid, ans in answers_dict.items():
        ans_json = json.dumps(ans, ensure_ascii=False)
        cursor.execute('''
        INSERT INTO answers (session_token, question_id, answer_json, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(session_token, question_id) DO UPDATE SET
            answer_json = excluded.answer_json,
            updated_at = CURRENT_TIMESTAMP
        ''', (token, qid, ans_json))

    conn.commit()
    conn.close()

def save_family_members(token, members_list):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM family_members WHERE session_token = ?', (token,))
    for idx, m in enumerate(members_list):
        cursor.execute('''
        INSERT INTO family_members (session_token, member_index, user_group, count, gender, age_range, special_note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            token,
            idx,
            m.get('user_group', 'Adults'),
            int(m.get('count', 1)),
            m.get('gender', ''),
            m.get('age_range', ''),
            m.get('special_note', '')
        ))
    conn.commit()
    conn.close()

def save_dynamic_rooms(token, rooms_list):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM dynamic_rooms WHERE session_token = ?', (token,))
    for idx, r in enumerate(rooms_list):
        ans_json = json.dumps(r.get('answers', {}), ensure_ascii=False)
        cursor.execute('''
        INSERT INTO dynamic_rooms (session_token, room_id, room_name, room_type, room_index, answers_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            token,
            r.get('room_id', f"room_{idx+1}"),
            r.get('room_name', f"Additional Bedroom {idx+1}"),
            r.get('room_type', 'additional_bedroom'),
            idx,
            ans_json
        ))
    conn.commit()
    conn.close()

def save_visual_selection(token, category, style_obj):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO selected_visuals (
        session_token, category, style_id, style_name, style_number,
        image_url, living_image_url, dining_image_url, bedroom_image_url, wardrobe_image_url, selected_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(session_token, category) DO UPDATE SET
        style_id = excluded.style_id,
        style_name = excluded.style_name,
        style_number = excluded.style_number,
        image_url = excluded.image_url,
        living_image_url = excluded.living_image_url,
        dining_image_url = excluded.dining_image_url,
        bedroom_image_url = excluded.bedroom_image_url,
        wardrobe_image_url = excluded.wardrobe_image_url,
        selected_at = CURRENT_TIMESTAMP
    ''', (
        token,
        category,
        style_obj.get('id', ''),
        style_obj.get('styleName', ''),
        str(style_obj.get('styleNumber', '')),
        style_obj.get('image', ''),
        style_obj.get('livingImage', ''),
        style_obj.get('diningImage', ''),
        style_obj.get('bedroomImage', ''),
        style_obj.get('wardrobeImage', '')
    ))
    conn.commit()
    conn.close()

def record_upload(token, file_id, orig_name, stored_name, size, category='general'):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO uploads (session_token, file_id, original_filename, stored_filename, file_size, category)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (token, file_id, orig_name, stored_name, size, category))
    conn.commit()
    conn.close()

def submit_session(token):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE sessions
    SET status = 'submitted', submitted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, progress_percent = 100
    WHERE token = ?
    ''', (token,))
    conn.commit()
    conn.close()

def book_consultation(token, name, email, phone, date_str, time_str, meeting_type, notes):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO consultations (session_token, client_name, client_email, client_phone, preferred_date, preferred_time, meeting_type, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (token, name, email, phone, date_str, time_str, meeting_type, notes))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
