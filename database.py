import sqlite3
import os
import json
import uuid
from datetime import datetime

DATABASE_URL = os.environ.get('DATABASE_URL', '')
DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shameer_questionnaire.db'))

def is_postgres():
    """Check if PostgreSQL (Supabase) is configured via DATABASE_URL."""
    url = os.environ.get('DATABASE_URL', '')
    return bool(url and (url.startswith('postgres://') or url.startswith('postgresql://')))

class DBConnection:
    """Unified database connection wrapper providing standard interface for SQLite and PostgreSQL with context management."""
    def __init__(self, conn, is_pg=False, pool=None):
        self._conn = conn
        self.is_pg = is_pg
        self.pool = pool

    def cursor(self):
        return DBCursor(self._conn.cursor(), self.is_pg)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            pass

    def close(self):
        try:
            if self.pool is not None:
                self.pool.putconn(self._conn)
            else:
                self._conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        self.close()

class DBCursor:
    """Unified database cursor wrapper with automatic dictionary row formatting and placeholder normalization."""
    def __init__(self, cursor, is_pg=False):
        self._cursor = cursor
        self.is_pg = is_pg

    def execute(self, query, params=None):
        if not self.is_pg and params is not None:
            # Normalize PostgreSQL %s to SQLite ? parameter placeholder
            query = query.replace('%s', '?')
        if params is None:
            return self._cursor.execute(query)
        return self._cursor.execute(query, params)

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        if hasattr(row, 'keys'):
            return dict(row)
        if isinstance(row, dict):
            return row
        cols = [d[0] for d in self._cursor.description]
        return dict(zip(cols, row))

    def fetchall(self):
        rows = self._cursor.fetchall()
        if not rows:
            return []
        first = rows[0]
        if hasattr(first, 'keys') or isinstance(first, dict):
            return [dict(r) for r in rows]
        cols = [d[0] for d in self._cursor.description]
        return [dict(zip(cols, r)) for r in rows]

    @property
    def description(self):
        return self._cursor.description

    @property
    def lastrowid(self):
        return getattr(self._cursor, 'lastrowid', None)

def db_binary(data):
    """Normalize binary data for storage across SQLite and PostgreSQL."""
    if is_postgres():
        import psycopg2
        return psycopg2.Binary(data)
    return sqlite3.Binary(data)

_pg_pool = None

def get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        import psycopg2.pool
        from psycopg2.extras import RealDictCursor
        url = os.environ.get('DATABASE_URL', '')
        if url.startswith('postgres://'):
            url = 'postgresql://' + url[len('postgres://'):]
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=url,
            connect_timeout=10,
            cursor_factory=RealDictCursor
        )
    return _pg_pool

def get_db():
    """Factory function returning a unified DBConnection with context management."""
    if is_postgres():
        pool = get_pg_pool()
        conn = None
        for _ in range(2):
            try:
                conn = pool.getconn()
                if conn.closed:
                    pool.putconn(conn, close=True)
                    conn = None
                    continue
                conn.autocommit = False
                return DBConnection(conn, is_pg=True, pool=pool)
            except Exception:
                if conn:
                    try:
                        pool.putconn(conn, close=True)
                    except Exception:
                        pass
                    conn = None
        # Fallback to direct connect if pool is exhausted or reconnecting
        import psycopg2
        from psycopg2.extras import RealDictCursor
        url = os.environ.get('DATABASE_URL', '')
        if url.startswith('postgres://'):
            url = 'postgresql://' + url[len('postgres://'):]
        conn = psycopg2.connect(url, connect_timeout=10, cursor_factory=RealDictCursor)
        conn.autocommit = False
        return DBConnection(conn, is_pg=True, pool=None)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return DBConnection(conn, is_pg=False)

def init_db():
    """Initialize database schema. In PostgreSQL, schema is managed via Supabase migrations."""
    if is_postgres():
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1 as alive")
                cur.fetchone()
                print("[DB] Connected to PostgreSQL (Supabase) successfully.")
        except Exception as e:
            print(f"[DB] PostgreSQL connectivity check warning: {e}")
        return

    with get_db() as conn:
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
    print("Initialized database schema successfully.")

def create_session(token=None):
    if not token:
        token = str(uuid.uuid4())
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO sessions (token, created_at, updated_at)
        VALUES (%s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (token) DO NOTHING
        ''', (token,))
        conn.commit()
    return token

def get_session_data(token):
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM sessions WHERE token = %s', (token,))
        session = cursor.fetchone()
        if not session:
            return None

        session_dict = dict(session)

        # Answers
        cursor.execute('SELECT question_id, answer_json FROM answers WHERE session_token = %s', (token,))
        answers = {}
        for row in cursor.fetchall():
            try:
                answers[row['question_id']] = json.loads(row['answer_json'])
            except Exception:
                answers[row['question_id']] = row['answer_json']
        session_dict['answers'] = answers

        # Family members
        cursor.execute('SELECT * FROM family_members WHERE session_token = %s ORDER BY member_index ASC', (token,))
        family_members = [dict(row) for row in cursor.fetchall()]
        session_dict['family_members'] = family_members

        # Dynamic rooms
        cursor.execute('SELECT * FROM dynamic_rooms WHERE session_token = %s ORDER BY room_index ASC', (token,))
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
        cursor.execute('SELECT * FROM selected_visuals WHERE session_token = %s', (token,))
        visuals = {}
        for row in cursor.fetchall():
            visuals[row['category']] = dict(row)
        session_dict['selected_visuals'] = visuals

        # Uploads
        cursor.execute('SELECT * FROM uploads WHERE session_token = %s ORDER BY uploaded_at DESC', (token,))
        uploads = [dict(row) for row in cursor.fetchall()]
        session_dict['uploads'] = uploads

        # Consultation
        cursor.execute('SELECT * FROM consultations WHERE session_token = %s ORDER BY created_at DESC LIMIT 1', (token,))
        consultation = cursor.fetchone()
        session_dict['consultation'] = dict(consultation) if consultation else None

        return session_dict

def save_answers(token, answers_dict, current_chapter=None, progress_percent=None):
    with get_db() as conn:
        cursor = conn.cursor()

        client_name = answers_dict.get('client_name')
        email = answers_dict.get('email_address')
        phone = answers_dict.get('contact_number')

        update_fields = ['updated_at = CURRENT_TIMESTAMP']
        update_vals = []

        if client_name:
            update_fields.append('client_name = %s')
            update_vals.append(client_name)
        if email:
            update_fields.append('email = %s')
            update_vals.append(email)
        if phone:
            update_fields.append('phone = %s')
            update_vals.append(phone)
        if current_chapter is not None:
            update_fields.append('current_chapter = %s')
            update_vals.append(current_chapter)
        if progress_percent is not None:
            update_fields.append('progress_percent = %s')
            update_vals.append(progress_percent)

        update_vals.append(token)
        cursor.execute(f"UPDATE sessions SET {', '.join(update_fields)} WHERE token = %s", update_vals)

        for qid, ans in answers_dict.items():
            ans_json = json.dumps(ans, ensure_ascii=False)
            cursor.execute('''
            INSERT INTO answers (session_token, question_id, answer_json, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT(session_token, question_id) DO UPDATE SET
                answer_json = excluded.answer_json,
                updated_at = CURRENT_TIMESTAMP
            ''', (token, qid, ans_json))

        conn.commit()

def save_family_members(token, members_list):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM family_members WHERE session_token = %s', (token,))
        for idx, m in enumerate(members_list):
            cursor.execute('''
            INSERT INTO family_members (session_token, member_index, user_group, count, gender, age_range, special_note)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
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

def save_dynamic_rooms(token, rooms_list):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM dynamic_rooms WHERE session_token = %s', (token,))
        for idx, r in enumerate(rooms_list):
            ans_json = json.dumps(r.get('answers', {}), ensure_ascii=False)
            cursor.execute('''
            INSERT INTO dynamic_rooms (session_token, room_id, room_name, room_type, room_index, answers_json)
            VALUES (%s, %s, %s, %s, %s, %s)
            ''', (
                token,
                r.get('room_id', f"room_{idx+1}"),
                r.get('room_name', f"Additional Bedroom {idx+1}"),
                r.get('room_type', 'additional_bedroom'),
                idx,
                ans_json
            ))
        conn.commit()

def save_visual_selection(token, category, style_obj):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO selected_visuals (
            session_token, category, style_id, style_name, style_number,
            image_url, living_image_url, dining_image_url, bedroom_image_url, wardrobe_image_url, selected_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
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

def record_upload(token, file_id, orig_name, stored_name, size, category='general'):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO uploads (session_token, file_id, original_filename, stored_filename, file_size, category)
        VALUES (%s, %s, %s, %s, %s, %s)
        ''', (token, file_id, orig_name, stored_name, size, category))
        conn.commit()

def submit_session(token):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        UPDATE sessions
        SET status = 'submitted', submitted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, progress_percent = 100
        WHERE token = %s
        ''', (token,))
        conn.commit()

def book_consultation(token, name, email, phone, date_str, time_str, meeting_type, notes):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO consultations (session_token, client_name, client_email, client_phone, preferred_date, preferred_time, meeting_type, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (token, name, email, phone, date_str, time_str, meeting_type, notes))
        conn.commit()

if __name__ == '__main__':
    init_db()
