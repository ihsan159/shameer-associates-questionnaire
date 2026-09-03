import os
import io
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template, send_from_directory, redirect, url_for
from werkzeug.utils import secure_filename
from flask_login import login_user, logout_user, login_required, current_user

import database
import architect_db
import auth
import notify
from pdf_generator import generate_pdf_bytes, generate_architect_pdf_bytes

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB max upload
app.secret_key = os.environ.get('SECRET_KEY', 'shameer_associates_secret_key_2026_architect')

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize DBs on start
database.init_db()
architect_db.init_phase2_db()

# Initialize Flask-Login
auth.login_manager.init_app(app)


def seed_default_architect():
    try:
        users = architect_db.get_all_users()
        if not users:
            default_email = "architect@shameerassociates.com"
            default_pass = "Architect123!"
            p_hash = auth.hash_password(default_pass)
            architect_db.create_user(default_email, p_hash, "Lead Architect", "admin")
            print(f"[SEED] Created default architect user: {default_email}")
    except Exception as e:
        print(f"[SEED] Error seeding architect user: {e}")


seed_default_architect()

# Load static schema & visuals into memory cache
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'questionnaire_schema.json')
VISUALS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'visual_references.json')

with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
    QUESTIONNAIRE_SCHEMA = json.load(f)

with open(VISUALS_PATH, 'r', encoding='utf-8') as f:
    VISUAL_REFERENCES = json.load(f)


# ============================================================
# PHASE 1 CLIENT ROUTES
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/schema', methods=['GET'])
def get_schema():
    return jsonify(QUESTIONNAIRE_SCHEMA)


@app.route('/api/visuals', methods=['GET'])
def get_visuals():
    return jsonify(VISUAL_REFERENCES)


@app.route('/api/session/new', methods=['POST'])
def new_session():
    data = request.get_json(silent=True) or {}
    token = data.get('token') or str(uuid.uuid4())
    token = database.create_session(token)
    session_data = database.get_session_data(token)
    return jsonify({
        'success': True,
        'token': token,
        'session': session_data
    })


@app.route('/api/session/<token>', methods=['GET'])
def get_session(token):
    session_data = database.get_session_data(token)
    if not session_data:
        database.create_session(token)
        session_data = database.get_session_data(token)
    return jsonify({
        'success': True,
        'session': session_data
    })


@app.route('/api/session/<token>/save', methods=['POST'])
def save_session_answers(token):
    data = request.get_json(silent=True) or {}
    answers = data.get('answers', {})
    current_chapter = data.get('current_chapter')
    progress_percent = data.get('progress_percent')

    database.save_answers(token, answers, current_chapter, progress_percent)
    architect_db.sync_project_metadata(token)

    return jsonify({'success': True, 'saved_at': datetime.now().isoformat()})


@app.route('/api/session/<token>/save_family', methods=['POST'])
def save_family(token):
    data = request.get_json(silent=True) or {}
    members = data.get('family_members', [])
    database.save_family_members(token, members)
    return jsonify({'success': True})


@app.route('/api/session/<token>/save_rooms', methods=['POST'])
def save_rooms(token):
    data = request.get_json(silent=True) or {}
    rooms = data.get('dynamic_rooms', [])
    database.save_dynamic_rooms(token, rooms)
    return jsonify({'success': True})


@app.route('/api/session/<token>/save_visual', methods=['POST'])
def save_visual(token):
    data = request.get_json(silent=True) or {}
    category = data.get('category')
    style_obj = data.get('style', {})
    if not category or not style_obj:
        return jsonify({'success': False, 'error': 'Missing category or style object'}), 400

    database.save_visual_selection(token, category, style_obj)
    return jsonify({'success': True})


@app.route('/api/session/<token>/upload', methods=['POST'])
def upload_file(token):
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Empty filename'}), 400

    orig_name = secure_filename(file.filename) or f"upload_{uuid.uuid4().hex[:8]}"
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(orig_name)[1]
    stored_name = f"{token}_{file_id}{ext}"
    stored_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
    file.save(stored_path)

    file_size = os.path.getsize(stored_path)
    category = request.form.get('category', 'site_document')

    database.record_upload(token, file_id, orig_name, stored_name, file_size, category)

    return jsonify({
        'success': True,
        'file_id': file_id,
        'filename': orig_name,
        'size': file_size
    })


@app.route('/api/session/<token>/submit', methods=['POST'])
def submit(token):
    session_data = database.get_session_data(token)
    if not session_data:
        return jsonify({'success': False, 'error': 'Invalid session token'}), 404

    database.submit_session(token)

    answers = session_data.get('answers', {})
    client_name = answers.get('client_name', 'Client')
    location = answers.get('project_location', '')
    project_type = answers.get('project_type', '')

    project = architect_db.get_or_create_project(token, client_name, location, project_type)
    architect_db.sync_project_metadata(token)
    architect_db.create_notification(project['id'], notification_type='new_submission')

    try:
        notify.notify_new_submission(project)
    except Exception as e:
        app.logger.error(f"Notification error: {e}")

    return jsonify({
        'success': True,
        'status': 'submitted',
        'message': 'Your residential design brief has been successfully submitted to Shameer Associates.'
    })


@app.route('/api/session/<token>/pdf', methods=['GET'])
def download_pdf(token):
    session_data = database.get_session_data(token)
    if not session_data:
        return "Session not found", 404

    pdf_bytes = generate_pdf_bytes(session_data, QUESTIONNAIRE_SCHEMA)
    
    client_name = session_data.get('answers', {}).get('client_name', 'Client')
    safe_name = "".join(c for c in client_name if c.isalnum() or c in (' ', '_', '-')).strip() or 'Client'
    filename = f"Shameer_Associates_Design_Brief_{safe_name.replace(' ', '_')}.pdf"

    is_download = request.args.get('download', '0') == '1'

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=is_download,
        download_name=filename
    )


@app.route('/api/session/<token>/consultation', methods=['POST'])
def book_consultation(token):
    data = request.get_json(silent=True) or {}
    session_data = database.get_session_data(token) or {}
    answers = session_data.get('answers', {})

    name = data.get('name') or answers.get('client_name', 'Client')
    email = data.get('email') or answers.get('email_address', '')
    phone = data.get('phone') or answers.get('contact_number', '')
    date_str = data.get('date', '')
    time_str = data.get('time', '')
    meeting_type = data.get('meeting_type', 'In-person / Studio Consultation')
    notes = data.get('notes', '')

    if not date_str or not time_str:
        return jsonify({'success': False, 'error': 'Date and time are required'}), 400

    database.book_consultation(token, name, email, phone, date_str, time_str, meeting_type, notes)

    return jsonify({
        'success': True,
        'message': 'Consultation booked successfully. Shameer Associates team will reach out to confirm.'
    })


# ============================================================
# PHASE 2 ARCHITECT AUTH & DASHBOARD ROUTES
# ============================================================

@app.route('/architect/login', methods=['GET', 'POST'])
def architect_login():
    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''

        user_dict = architect_db.get_user_by_email(email)
        if user_dict and auth.verify_password(password, user_dict['password_hash']):
            user_obj = auth.User(user_dict)
            login_user(user_obj)
            architect_db.update_last_login(user_obj.id)

            if request.is_json:
                return jsonify({'success': True, 'redirect': '/architect'})
            return redirect('/architect')

        if request.is_json:
            return jsonify({'success': False, 'error': 'Invalid email address or password'}), 401
        return render_template('architect_login.html', error='Invalid email address or password')

    if current_user.is_authenticated:
        return redirect('/architect')
    return render_template('architect_login.html')


@app.route('/architect/logout', methods=['GET', 'POST'])
def architect_logout():
    logout_user()
    if request.is_json:
        return jsonify({'success': True, 'redirect': '/architect/login'})
    return redirect('/architect/login')


@app.route('/architect')
@app.route('/architect/dashboard')
@app.route('/architect/project/<int:project_id>')
@login_required
@auth.require_role('architect', 'admin')
def architect_dashboard(project_id=None):
    return render_template('architect.html', active_project_id=project_id)


# ============================================================
# PHASE 2 ARCHITECT API ENDPOINTS
# ============================================================

@app.route('/api/architect/stats', methods=['GET'])
@login_required
@auth.require_role('architect', 'admin')
def get_architect_stats():
    stats = architect_db.get_dashboard_stats()
    return jsonify({'success': True, 'stats': stats})


@app.route('/api/architect/projects', methods=['GET'])
@login_required
@auth.require_role('architect', 'admin')
def get_architect_projects():
    status_filter = request.args.get('status', 'all')
    search = request.args.get('search', '')
    projects = architect_db.get_project_list(status_filter=status_filter, search=search)
    return jsonify({'success': True, 'projects': projects})


@app.route('/api/architect/project/<int:project_id>', methods=['GET'])
@login_required
@auth.require_role('architect', 'admin')
def get_architect_project_detail(project_id):
    project = architect_db.get_full_project_detail(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404
    return jsonify({'success': True, 'project': project})


@app.route('/api/architect/project/<int:project_id>/status', methods=['POST'])
@login_required
@auth.require_role('architect', 'admin')
def update_project_status(project_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get('status')
    note = data.get('note', '')
    if not new_status:
        return jsonify({'success': False, 'error': 'Status is required'}), 400

    success = architect_db.change_project_status(project_id, current_user.id, new_status, note)
    if not success:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    return jsonify({'success': True, 'status': new_status})


@app.route('/api/architect/project/<int:project_id>/note', methods=['POST'])
@login_required
@auth.require_role('architect', 'admin')
def add_architect_note(project_id):
    data = request.get_json(silent=True) or {}
    content = data.get('content', '').strip()
    note_type = data.get('note_type', 'general')

    if not content:
        return jsonify({'success': False, 'error': 'Note content cannot be empty'}), 400

    note_id = architect_db.add_note(project_id, current_user.id, content, note_type)
    return jsonify({'success': True, 'note_id': note_id})


@app.route('/api/architect/project/<int:project_id>/note/<int:note_id>', methods=['PUT', 'DELETE'])
@login_required
@auth.require_role('architect', 'admin')
def manage_architect_note(project_id, note_id):
    if request.method == 'DELETE':
        architect_db.delete_note(note_id, current_user.id)
        return jsonify({'success': True})

    data = request.get_json(silent=True) or {}
    content = data.get('content', '').strip()
    note_type = data.get('note_type')
    if not content:
        return jsonify({'success': False, 'error': 'Note content cannot be empty'}), 400

    architect_db.edit_note(note_id, current_user.id, content, note_type)
    return jsonify({'success': True})


@app.route('/api/architect/project/<int:project_id>/edit_answer', methods=['POST'])
@login_required
@auth.require_role('architect', 'admin')
def edit_project_answer(project_id):
    data = request.get_json(silent=True) or {}
    question_id = data.get('question_id')
    new_value = data.get('new_value')
    reason = data.get('reason', '')

    if not question_id:
        return jsonify({'success': False, 'error': 'question_id is required'}), 400

    project = architect_db.get_project_by_id(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    architect_db.edit_answer(project_id, project['session_token'], current_user.id, question_id, new_value, reason)
    architect_db.sync_project_metadata(project['session_token'])
    return jsonify({'success': True})


@app.route('/api/architect/notifications', methods=['GET'])
@login_required
@auth.require_role('architect', 'admin')
def get_architect_notifications():
    notifs = architect_db.get_notifications(current_user.id, unread_only=False)
    return jsonify({'success': True, 'notifications': notifs})


@app.route('/api/architect/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
@auth.require_role('architect', 'admin')
def read_notification(notification_id):
    architect_db.mark_notification_read(notification_id)
    return jsonify({'success': True})


@app.route('/api/architect/project/<int:project_id>/pdf', methods=['GET'])
@login_required
@auth.require_role('architect', 'admin')
def download_architect_pdf(project_id):
    project = architect_db.get_full_project_detail(project_id)
    if not project:
        return "Project not found", 404

    pdf_bytes = generate_architect_pdf_bytes(project, QUESTIONNAIRE_SCHEMA)
    version_id, v_num = architect_db.store_pdf_version(project_id, pdf_bytes, 'architect_export', current_user.id)

    client_name = project.get('client_name', 'Client')
    safe_name = "".join(c for c in client_name if c.isalnum() or c in (' ', '_', '-')).strip() or 'Client'
    filename = f"Shameer_Associates_Project_Brief_{project.get('project_uid', 'SA')}_{safe_name.replace(' ', '_')}_v{v_num}.pdf"

    is_download = request.args.get('download', '1') == '1'
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=is_download,
        download_name=filename
    )


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'Shameer Associates Design Questionnaire & Architect API'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
