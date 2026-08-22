"""
architect_db.py
Phase 2 database layer — all Phase 2 tables and query functions.
Extends Phase 1 database.py without modifying it.
"""
import sqlite3
import json
import uuid
import os
from datetime import datetime

from database import get_db, DB_PATH


# ============================================================
# PHASE 2 TABLE INITIALISATION
# ============================================================

def init_phase2_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")

    # ----------------------------------------------------------
    # users — architect / admin accounts
    # ----------------------------------------------------------
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT 'architect',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_at TIMESTAMP
    )
    ''')

    # ----------------------------------------------------------
    # projects — canonical project record wrapping a session
    # ----------------------------------------------------------
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_uid TEXT UNIQUE NOT NULL,
        session_token TEXT NOT NULL,
        client_name TEXT DEFAULT '',
        location TEXT DEFAULT '',
        project_type TEXT DEFAULT '',
        assigned_architect_id INTEGER,
        status TEXT NOT NULL DEFAULT 'new_submission',
        archived INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(session_token) REFERENCES sessions(token),
        FOREIGN KEY(assigned_architect_id) REFERENCES users(id)
    )
    ''')

    # ----------------------------------------------------------
    # architect_notes — private internal notes
    # ----------------------------------------------------------
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS architect_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        author_id INTEGER NOT NULL,
        note_type TEXT NOT NULL DEFAULT 'general',
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(author_id) REFERENCES users(id)
    )
    ''')

    # ----------------------------------------------------------
    # answer_edit_history — every architect answer change
    # ----------------------------------------------------------
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS answer_edit_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        editor_id INTEGER NOT NULL,
        question_id TEXT NOT NULL,
        original_value_json TEXT NOT NULL,
        new_value_json TEXT NOT NULL,
        reason TEXT DEFAULT '',
        edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(editor_id) REFERENCES users(id)
    )
    ''')

    # ----------------------------------------------------------
    # project_status_history — status transition audit
    # ----------------------------------------------------------
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS project_status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        changed_by_id INTEGER NOT NULL,
        from_status TEXT NOT NULL,
        to_status TEXT NOT NULL,
        note TEXT DEFAULT '',
        changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(changed_by_id) REFERENCES users(id)
    )
    ''')

    # ----------------------------------------------------------
    # pdf_versions — versioned PDF archive
    # ----------------------------------------------------------
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pdf_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        version_number INTEGER NOT NULL,
        generated_by_id INTEGER,
        pdf_data BLOB NOT NULL,
        label TEXT NOT NULL DEFAULT 'original_submission',
        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(generated_by_id) REFERENCES users(id)
    )
    ''')

    # ----------------------------------------------------------
    # project_activity — full audit timeline
    # ----------------------------------------------------------
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS project_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        actor_id INTEGER,
        action_type TEXT NOT NULL,
        detail_json TEXT DEFAULT '{}',
        occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(actor_id) REFERENCES users(id)
    )
    ''')

    # ----------------------------------------------------------
    # notifications — new submission alerts for architects
    # ----------------------------------------------------------
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        notification_type TEXT NOT NULL DEFAULT 'new_submission',
        project_id INTEGER,
        recipient_id INTEGER,
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(recipient_id) REFERENCES users(id)
    )
    ''')

    conn.commit()
    conn.close()


# ============================================================
# PROJECT UID GENERATION
# ============================================================

def _generate_project_uid():
    conn = get_db()
    cursor = conn.cursor()
    year = datetime.now().year
    cursor.execute("SELECT COUNT(*) as cnt FROM projects WHERE project_uid LIKE ?", (f'SA-{year}-%',))
    count = cursor.fetchone()['cnt']
    conn.close()
    return f"SA-{year}-{(count + 1):04d}"


# ============================================================
# PROJECT MANAGEMENT
# ============================================================

def get_or_create_project(session_token, client_name='', location='', project_type=''):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE session_token = ?", (session_token,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return dict(row)

    uid = _generate_project_uid()
    cursor.execute('''
    INSERT INTO projects (project_uid, session_token, client_name, location, project_type)
    VALUES (?, ?, ?, ?, ?)
    ''', (uid, session_token, client_name, location, project_type))
    conn.commit()
    project_id = cursor.lastrowid
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    project = dict(cursor.fetchone())
    conn.close()
    return project


def get_project_by_id(project_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_project_by_uid(project_uid):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE project_uid = ?", (project_uid,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_dashboard_stats():
    conn = get_db()
    cursor = conn.cursor()

    stats = {}
    status_groups = {
        'new_submissions': ['new_submission'],
        'in_review': ['in_review', 'client_contacted'],
        'consultations': ['consultation_pending', 'consultation_completed'],
        'completed': ['design_brief_ready', 'completed']
    }
    for key, statuses in status_groups.items():
        placeholders = ','.join('?' * len(statuses))
        cursor.execute(
            f"SELECT COUNT(*) as cnt FROM projects WHERE status IN ({placeholders}) AND archived = 0",
            statuses
        )
        stats[key] = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) as cnt FROM projects WHERE archived = 0")
    stats['total'] = cursor.fetchone()['cnt']

    # Unread notifications count
    cursor.execute("SELECT COUNT(*) as cnt FROM notifications WHERE is_read = 0")
    stats['unread_notifications'] = cursor.fetchone()['cnt']

    conn.close()
    return stats


def get_project_list(status_filter=None, search=None, include_archived=False):
    conn = get_db()
    cursor = conn.cursor()

    sql = '''
    SELECT p.*, u.full_name as assigned_architect_name,
           s.progress_percent, s.submitted_at
    FROM projects p
    LEFT JOIN users u ON p.assigned_architect_id = u.id
    LEFT JOIN sessions s ON p.session_token = s.token
    WHERE 1=1
    '''
    params = []

    if not include_archived:
        sql += " AND p.archived = 0"

    STATUS_FILTER_MAP = {
        'new_submission': ['new_submission'],
        'in_review': ['in_review', 'client_contacted'],
        'consultation': ['consultation_pending', 'consultation_completed'],
        'completed': ['design_brief_ready', 'completed'],
        'archived': None  # handled by include_archived
    }

    if status_filter and status_filter != 'all':
        if status_filter == 'archived':
            sql = sql.replace("AND p.archived = 0", "AND p.archived = 1")
        elif status_filter in STATUS_FILTER_MAP:
            statuses = STATUS_FILTER_MAP[status_filter]
            placeholders = ','.join('?' * len(statuses))
            sql += f" AND p.status IN ({placeholders})"
            params.extend(statuses)

    if search:
        sql += " AND (p.client_name LIKE ? OR p.location LIKE ? OR p.project_uid LIKE ? OR p.project_type LIKE ?)"
        s = f'%{search}%'
        params.extend([s, s, s, s])

    sql += " ORDER BY p.updated_at DESC"

    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def sync_project_metadata(session_token):
    """Pull latest client name/location from answers and sync to projects table."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT answer_json FROM answers WHERE session_token = ? AND question_id = 'client_name'", (session_token,))
    row = cursor.fetchone()
    client_name = json.loads(row['answer_json']) if row else ''

    cursor.execute("SELECT answer_json FROM answers WHERE session_token = ? AND question_id = 'project_location'", (session_token,))
    row = cursor.fetchone()
    location = json.loads(row['answer_json']) if row else ''

    cursor.execute("SELECT answer_json FROM answers WHERE session_token = ? AND question_id = 'project_type'", (session_token,))
    row = cursor.fetchone()
    project_type = json.loads(row['answer_json']) if row else ''

    cursor.execute('''
    UPDATE projects SET client_name = ?, location = ?, project_type = ?, updated_at = CURRENT_TIMESTAMP
    WHERE session_token = ?
    ''', (client_name, location, project_type, session_token))
    conn.commit()
    conn.close()


def archive_project(project_id, user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE projects SET archived = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()
    log_activity(project_id, user_id, 'project_archived', {})


def assign_architect(project_id, architect_id, assigner_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE projects SET assigned_architect_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                   (architect_id, project_id))
    conn.commit()
    conn.close()
    log_activity(project_id, assigner_id, 'architect_assigned', {'architect_id': architect_id})


# ============================================================
# ANSWER EDITING
# ============================================================

def edit_answer(project_id, session_token, editor_id, question_id, new_value, reason=''):
    conn = get_db()
    cursor = conn.cursor()

    # Fetch current value
    cursor.execute("SELECT answer_json FROM answers WHERE session_token = ? AND question_id = ?",
                   (session_token, question_id))
    row = cursor.fetchone()
    original_json = row['answer_json'] if row else 'null'

    new_json = json.dumps(new_value, ensure_ascii=False)

    # Upsert into answers
    cursor.execute('''
    INSERT INTO answers (session_token, question_id, answer_json, updated_at)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(session_token, question_id) DO UPDATE SET
        answer_json = excluded.answer_json,
        updated_at = CURRENT_TIMESTAMP
    ''', (session_token, question_id, new_json))

    # Record edit history
    cursor.execute('''
    INSERT INTO answer_edit_history (project_id, editor_id, question_id, original_value_json, new_value_json, reason)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (project_id, editor_id, question_id, original_json, new_json, reason))

    # Update project updated_at
    cursor.execute("UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (project_id,))

    conn.commit()
    conn.close()

    log_activity(project_id, editor_id, 'answer_edited', {
        'question_id': question_id,
        'reason': reason
    })


def get_edit_history(project_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT aeh.*, u.full_name as editor_name, u.email as editor_email
    FROM answer_edit_history aeh
    JOIN users u ON aeh.editor_id = u.id
    WHERE aeh.project_id = ?
    ORDER BY aeh.edited_at DESC
    ''', (project_id,))
    rows = []
    for row in cursor.fetchall():
        r = dict(row)
        try:
            r['original_value'] = json.loads(r['original_value_json'])
            r['new_value'] = json.loads(r['new_value_json'])
        except Exception:
            r['original_value'] = r['original_value_json']
            r['new_value'] = r['new_value_json']
        rows.append(r)
    conn.close()
    return rows


# ============================================================
# PROJECT STATUS
# ============================================================

STATUS_LABELS = {
    'new_submission': 'New Submission',
    'in_review': 'In Review',
    'client_contacted': 'Client Contacted',
    'consultation_pending': 'Consultation Pending',
    'consultation_completed': 'Consultation Completed',
    'design_brief_ready': 'Design Brief Ready',
    'completed': 'Completed',
    'archived': 'Archived'
}

def change_project_status(project_id, user_id, new_status, note=''):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    from_status = row['status']
    cursor.execute("UPDATE projects SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                   (new_status, project_id))
    cursor.execute('''
    INSERT INTO project_status_history (project_id, changed_by_id, from_status, to_status, note)
    VALUES (?, ?, ?, ?, ?)
    ''', (project_id, user_id, from_status, new_status, note))
    conn.commit()
    conn.close()

    log_activity(project_id, user_id, 'status_changed', {
        'from': from_status,
        'to': new_status,
        'note': note
    })
    return True


def get_status_history(project_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT psh.*, u.full_name as changed_by_name
    FROM project_status_history psh
    JOIN users u ON psh.changed_by_id = u.id
    WHERE psh.project_id = ?
    ORDER BY psh.changed_at DESC
    ''', (project_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ============================================================
# ARCHITECT NOTES
# ============================================================

NOTE_TYPES = ['general', 'design', 'client', 'site', 'budget', 'consultation', 'follow_up']

def get_project_notes(project_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT n.*, u.full_name as author_name
    FROM architect_notes n
    JOIN users u ON n.author_id = u.id
    WHERE n.project_id = ? AND n.deleted_at IS NULL
    ORDER BY n.created_at DESC
    ''', (project_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def add_note(project_id, author_id, content, note_type='general'):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO architect_notes (project_id, author_id, note_type, content)
    VALUES (?, ?, ?, ?)
    ''', (project_id, author_id, note_type, content))
    note_id = cursor.lastrowid
    conn.commit()
    conn.close()
    log_activity(project_id, author_id, 'note_added', {'note_id': note_id, 'note_type': note_type})
    return note_id


def edit_note(note_id, editor_id, content, note_type=None):
    conn = get_db()
    cursor = conn.cursor()
    if note_type:
        cursor.execute("UPDATE architect_notes SET content = ?, note_type = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND deleted_at IS NULL",
                       (content, note_type, note_id))
    else:
        cursor.execute("UPDATE architect_notes SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND deleted_at IS NULL",
                       (content, note_id))
    conn.commit()

    # Get project_id for activity log
    cursor.execute("SELECT project_id FROM architect_notes WHERE id = ?", (note_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        log_activity(row['project_id'], editor_id, 'note_edited', {'note_id': note_id})


def delete_note(note_id, deleter_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT project_id FROM architect_notes WHERE id = ?", (note_id,))
    row = cursor.fetchone()
    cursor.execute("UPDATE architect_notes SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()
    if row:
        log_activity(row['project_id'], deleter_id, 'note_deleted', {'note_id': note_id})


# ============================================================
# PDF VERSIONING
# ============================================================

def store_pdf_version(project_id, pdf_bytes, label='original_submission', generated_by_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(MAX(version_number), 0) as max_v FROM pdf_versions WHERE project_id = ?", (project_id,))
    max_v = cursor.fetchone()['max_v']
    new_version = max_v + 1
    cursor.execute('''
    INSERT INTO pdf_versions (project_id, version_number, generated_by_id, pdf_data, label)
    VALUES (?, ?, ?, ?, ?)
    ''', (project_id, new_version, generated_by_id, pdf_bytes, label))
    conn.commit()
    version_id = cursor.lastrowid
    conn.close()
    log_activity(project_id, generated_by_id, 'pdf_generated', {
        'version': new_version,
        'label': label
    })
    return version_id, new_version


def get_pdf_versions(project_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT pv.id, pv.version_number, pv.label, pv.generated_at,
           u.full_name as generated_by_name
    FROM pdf_versions pv
    LEFT JOIN users u ON pv.generated_by_id = u.id
    WHERE pv.project_id = ?
    ORDER BY pv.version_number DESC
    ''', (project_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_pdf_version_bytes(version_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT pdf_data, version_number, project_id FROM pdf_versions WHERE id = ?", (version_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None, None, None
    return bytes(row['pdf_data']), row['version_number'], row['project_id']


def get_latest_pdf_version(project_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT id, version_number FROM pdf_versions
    WHERE project_id = ?
    ORDER BY version_number DESC LIMIT 1
    ''', (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ============================================================
# ACTIVITY LOG
# ============================================================

def log_activity(project_id, actor_id, action_type, detail_dict):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO project_activity (project_id, actor_id, action_type, detail_json)
    VALUES (?, ?, ?, ?)
    ''', (project_id, actor_id, action_type, json.dumps(detail_dict, ensure_ascii=False)))
    conn.commit()
    conn.close()


def get_activity_log(project_id, limit=50):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT pa.*, u.full_name as actor_name
    FROM project_activity pa
    LEFT JOIN users u ON pa.actor_id = u.id
    WHERE pa.project_id = ?
    ORDER BY pa.occurred_at DESC
    LIMIT ?
    ''', (project_id, limit))
    rows = []
    for row in cursor.fetchall():
        r = dict(row)
        try:
            r['detail'] = json.loads(r['detail_json'])
        except Exception:
            r['detail'] = {}
        rows.append(r)
    conn.close()
    return rows


# ============================================================
# NOTIFICATIONS
# ============================================================

def create_notification(project_id, notification_type='new_submission', recipient_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO notifications (notification_type, project_id, recipient_id)
    VALUES (?, ?, ?)
    ''', (notification_type, project_id, recipient_id))
    conn.commit()
    conn.close()


def get_notifications(user_id=None, unread_only=True, limit=20):
    conn = get_db()
    cursor = conn.cursor()
    sql = '''
    SELECT n.*, p.project_uid, p.client_name, p.location
    FROM notifications n
    LEFT JOIN projects p ON n.project_id = p.id
    WHERE (n.recipient_id IS NULL OR n.recipient_id = ?)
    '''
    params = [user_id]
    if unread_only:
        sql += ' AND n.is_read = 0'
    sql += ' ORDER BY n.created_at DESC LIMIT ?'
    params.append(limit)
    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def mark_notification_read(notification_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
    conn.commit()
    conn.close()


# ============================================================
# USER MANAGEMENT
# ============================================================

def get_user_by_id(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_email(email):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ? AND is_active = 1", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(email, password_hash, full_name, role='architect'):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO users (email, password_hash, full_name, role)
    VALUES (?, ?, ?, ?)
    ''', (email, password_hash, full_name, role))
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id


def update_last_login(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_all_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, full_name, role, is_active, created_at, last_login_at FROM users ORDER BY full_name")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def update_user(user_id, full_name=None, role=None, is_active=None):
    conn = get_db()
    cursor = conn.cursor()
    fields = []
    params = []
    if full_name is not None:
        fields.append("full_name = ?")
        params.append(full_name)
    if role is not None:
        fields.append("role = ?")
        params.append(role)
    if is_active is not None:
        fields.append("is_active = ?")
        params.append(1 if is_active else 0)
    if not fields:
        conn.close()
        return
    params.append(user_id)
    cursor.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    conn.close()


# ============================================================
# FULL PROJECT DETAIL (architect view)
# ============================================================

def get_full_project_detail(project_id):
    """Return everything needed for architect project detail view."""
    import database as db

    project = get_project_by_id(project_id)
    if not project:
        return None

    token = project['session_token']
    session = db.get_session_data(token)
    if not session:
        return None

    project['session'] = session
    project['answers'] = session.get('answers', {})
    project['family_members'] = session.get('family_members', [])
    project['dynamic_rooms'] = session.get('dynamic_rooms', [])
    project['selected_visuals'] = session.get('selected_visuals', {})
    project['uploads'] = session.get('uploads', [])
    project['consultation'] = session.get('consultation')
    project['notes'] = get_project_notes(project_id)
    project['edit_history'] = get_edit_history(project_id)
    project['status_history'] = get_status_history(project_id)
    project['activity'] = get_activity_log(project_id)
    project['pdf_versions'] = get_pdf_versions(project_id)

    if project.get('assigned_architect_id'):
        user = get_user_by_id(project['assigned_architect_id'])
        project['assigned_architect'] = user
    else:
        project['assigned_architect'] = None

    return project


if __name__ == '__main__':
    init_phase2_db()
    print("Phase 2 DB initialized.")
