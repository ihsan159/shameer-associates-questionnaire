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
import storage
from pdf_generator import generate_pdf_bytes, generate_architect_pdf_bytes

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, 'static'),
    template_folder=os.path.join(BASE_DIR, 'templates')
)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB max upload

# Production environment detection
is_vercel = bool(os.environ.get('VERCEL'))
is_production = bool(
    os.environ.get('VERCEL')
    or os.environ.get('FLASK_ENV') == 'production'
    or os.environ.get('PRODUCTION')
    or os.environ.get('ENVIRONMENT') == 'production'
)

# Production security: require SECRET_KEY in production, fail safely at startup if missing
secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    if is_production:
        raise RuntimeError("CRITICAL: SECRET_KEY environment variable is required in production environment.")
    secret_key = 'shameer_associates_dev_secret_key_2026'

app.secret_key = secret_key

# Allowed upload extensions and MIME types whitelist
ALLOWED_EXTENSIONS = {'pdf', 'dwg', 'dxf', 'png', 'jpg', 'jpeg', 'webp', 'doc', 'docx', 'zip'}
MAX_UPLOAD_SIZE = 32 * 1024 * 1024  # 32 MB
ALLOWED_MIME_TYPES = {
    'application/pdf',
    'image/png',
    'image/jpeg',
    'image/pjpeg',
    'image/webp',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/zip',
    'application/x-zip-compressed',
    'multipart/x-zip',
    'image/vnd.dwg',
    'image/x-dwg',
    'application/acad',
    'application/x-acad',
    'application/autocad_dwg',
    'application/dwg',
    'application/x-dwg',
    'application/dxf',
    'application/x-dxf',
    'application/octet-stream'
}

def allowed_file(filename):
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS

# Serverless-friendly upload directory (fallback to /tmp on Vercel/read-only systems)
default_upload = '/tmp/uploads' if is_vercel else os.path.join(BASE_DIR, 'uploads')
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', default_upload)
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except Exception:
    UPLOAD_FOLDER = '/tmp/uploads'
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Production security session cookie settings
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=bool(os.environ.get('VERCEL') or os.environ.get('SESSION_COOKIE_SECURE', '').lower() == 'true')
)

# Initialize DBs on start
database.init_db()
architect_db.init_phase2_db()

# Initialize Flask-Login
auth.login_manager.init_app(app)


def seed_default_architect():
    try:
        default_email = os.environ.get("INITIAL_ARCHITECT_EMAIL", "architect@shameerassociates.com").strip().lower()
        user = architect_db.get_user_by_email(default_email)
        if not user:
            initial_pass = os.environ.get("INITIAL_ARCHITECT_PASSWORD")
            if not initial_pass:
                if is_production:
                    print(f"[SEED] Notice: Production mode active without INITIAL_ARCHITECT_PASSWORD. Skipping automatic architect creation.")
                    return
                # Development/testing fallback only
                initial_pass = "Architect123!"
                print(f"[SEED] Notice: INITIAL_ARCHITECT_PASSWORD not set. Using dev fallback password in local/test environment.")

            p_hash = auth.hash_password(initial_pass)
            architect_db.create_user(default_email, p_hash, "Lead Architect", "admin")
            print(f"[SEED] Created initial architect user: {default_email}")
    except Exception as e:
        print(f"[SEED] Error seeding architect user: {e}")


seed_default_architect()

# Load static schema & visuals into memory cache
SCHEMA_PATH = os.path.join(BASE_DIR, 'static', 'questionnaire_schema.json')
VISUALS_PATH = os.path.join(BASE_DIR, 'static', 'visual_references.json')

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


@app.route('/questionnaire/<token>')
def client_questionnaire(token):
    """Canonical client questionnaire entry point.
    The client clicks this link and their session is loaded automatically.
    No login required — the token IS the authentication.
    """
    # Ensure the session exists (create if new token from architect)
    existing = database.get_session_data(token)
    if not existing:
        database.create_session(token)
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


@app.route('/api/session/<token>/upload/prepare', methods=['POST'])
def prepare_upload(token):
    """Generate a signed upload URL to upload directly to Supabase Storage, bypassing Vercel payload limits."""
    session_data = database.get_session_data(token)
    if not session_data:
        return jsonify({'success': False, 'error': 'Invalid session token'}), 404

    data = request.get_json(silent=True) or {}
    filename = (data.get('filename') or '').strip()
    if not filename or not allowed_file(filename):
        return jsonify({
            'success': False,
            'error': f"File type not allowed. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        }), 400

    try:
        size = int(data.get('size', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid file size format'}), 400

    if size <= 0:
        return jsonify({'success': False, 'error': 'File cannot be empty'}), 400

    if size > MAX_UPLOAD_SIZE:
        return jsonify({
            'success': False,
            'error': f"File size exceeds 32 MB limit ({size} bytes)"
        }), 400

    category = data.get('category', 'site_document')
    file_id = str(uuid.uuid4())
    storage_path = storage.build_storage_path(token, file_id, filename)
    signed_upload_url = storage.create_signed_upload_url(storage_path)

    if signed_upload_url:
        return jsonify({
            'success': True,
            'direct_upload': True,
            'upload_url': signed_upload_url,
            'file_id': file_id,
            'stored_name': storage_path,
            'filename': filename,
            'category': category
        })
    else:
        # Fallback to standard server upload endpoint
        return jsonify({
            'success': True,
            'direct_upload': False,
            'upload_endpoint': f"/api/session/{token}/upload",
            'file_id': file_id,
            'stored_name': f"{token}_{file_id}_{secure_filename(filename)}",
            'filename': filename,
            'category': category
        })


@app.route('/api/session/<token>/upload/confirm', methods=['POST'])
def confirm_upload(token):
    """Record file metadata after a direct client upload to Supabase Storage succeeds."""
    session_data = database.get_session_data(token)
    if not session_data:
        return jsonify({'success': False, 'error': 'Invalid session token'}), 404

    data = request.get_json(silent=True) or {}
    file_id = data.get('file_id') or str(uuid.uuid4())
    orig_name = (data.get('filename') or '').strip()
    if not orig_name or not allowed_file(orig_name):
        return jsonify({'success': False, 'error': 'Invalid or disallowed file type'}), 400

    stored_name = (data.get('stored_name') or '').strip()
    if not stored_name:
        return jsonify({'success': False, 'error': 'stored_name is required'}), 400

    # Ensure stored_name conforms to session namespace
    if not (stored_name.startswith(f"sessions/{token}/") or stored_name.startswith(f"{token}_")):
        return jsonify({'success': False, 'error': 'Invalid stored_name format or unauthorized path'}), 400

    try:
        file_size = int(data.get('size', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid size format'}), 400

    if file_size <= 0 or file_size > MAX_UPLOAD_SIZE:
        return jsonify({'success': False, 'error': 'File size must be between 1 byte and 32 MB'}), 400

    category = data.get('category', 'site_document')
    database.record_upload(token, file_id, orig_name, stored_name, file_size, category)

    return jsonify({
        'success': True,
        'file_id': file_id,
        'filename': orig_name,
        'size': file_size
    })


@app.route('/api/session/<token>/upload', methods=['POST'])
def upload_file(token):
    """Fallback standard multipart upload handler."""
    session_data = database.get_session_data(token)
    if not session_data:
        return jsonify({'success': False, 'error': 'Invalid session token'}), 404

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if not file.filename or file.filename == '':
        return jsonify({'success': False, 'error': 'Empty filename'}), 400

    if not allowed_file(file.filename):
        return jsonify({
            'success': False,
            'error': f"File type not allowed. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        }), 400

    # Validate MIME type if present
    content_type = (file.content_type or '').lower().split(';')[0].strip()
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        return jsonify({'success': False, 'error': f"Disallowed MIME type: {content_type}"}), 400

    orig_name = secure_filename(file.filename) or f"upload_{uuid.uuid4().hex[:8]}"
    file_id = str(uuid.uuid4())
    category = request.form.get('category', 'site_document')

    # Read bytes to check actual size
    file_bytes = file.read()
    file_size = len(file_bytes)
    if file_size <= 0:
        return jsonify({'success': False, 'error': 'File cannot be empty'}), 400
    if file_size > MAX_UPLOAD_SIZE:
        return jsonify({'success': False, 'error': f"File size exceeds 32 MB limit ({file_size} bytes)"}), 400

    # If Supabase Storage is configured, stream directly to bucket
    if storage.is_storage_configured():
        storage_path = storage.build_storage_path(token, file_id, orig_name)
        storage_ct = content_type or 'application/octet-stream'
        ok = storage.upload_file_bytes(storage_path, file_bytes, storage_ct)
        if ok:
            database.record_upload(token, file_id, orig_name, storage_path, file_size, category)
            return jsonify({
                'success': True,
                'file_id': file_id,
                'filename': orig_name,
                'size': file_size,
                'storage': 'supabase'
            })

    # Local disk fallback
    ext = os.path.splitext(orig_name)[1]
    stored_name = f"{token}_{file_id}{ext}"
    stored_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
    with open(stored_path, 'wb') as f:
        f.write(file_bytes)

    database.record_upload(token, file_id, orig_name, stored_name, file_size, category)

    return jsonify({
        'success': True,
        'file_id': file_id,
        'filename': orig_name,
        'size': file_size,
        'storage': 'local'
    })


@app.route('/api/architect/uploads/<path:stored_name>', methods=['GET'])
@login_required
@auth.require_role('architect', 'admin')
def download_uploaded_file(stored_name):
    """Securely download or view uploaded documents."""
    # Check if stored in Supabase Storage
    if storage.is_storage_configured() and stored_name.startswith('sessions/'):
        signed_url = storage.create_signed_download_url(stored_name)
        if signed_url:
            return redirect(signed_url)

    # Check local disk
    safe_name = os.path.basename(stored_name)
    local_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
    if os.path.exists(local_path):
        return send_from_directory(app.config['UPLOAD_FOLDER'], safe_name)

    return "File not found", 404


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


# NOTE: /api/session/<token>/pdf has been removed for security.
# PDF generation is strictly architect-only via /api/architect/project/<id>/pdf.
# Clients must NOT be able to access or download design PDFs.


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


@app.route('/api/architect/project/<int:project_id>', methods=['DELETE'])
@login_required
@auth.require_role('architect', 'admin')
def delete_architect_project(project_id):
    project = architect_db.get_project_by_id(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    user_id = getattr(current_user, 'id', None)
    permanent = request.args.get('permanent', '0') == '1'
    if permanent:
        architect_db.delete_project_permanent(project_id, user_id)
    else:
        architect_db.archive_project(project_id, user_id)

    return jsonify({'success': True, 'message': 'Project deleted successfully'})


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


@app.route('/api/architect/new-questionnaire', methods=['POST'])
@login_required
@auth.require_role('architect', 'admin')
def architect_new_questionnaire():
    """Architect creates a new client questionnaire session.
    Pre-populates client info so it is visible in the dashboard immediately.
    Returns a unique client link the architect can copy or send.
    """
    data = request.get_json(silent=True) or {}
    client_name = (data.get('client_name') or '').strip()
    phone = (data.get('phone') or '').strip()
    email = (data.get('email') or '').strip()
    project_name = (data.get('project_name') or '').strip()
    location = (data.get('location') or '').strip()

    if not client_name:
        return jsonify({'success': False, 'error': 'Client name is required'}), 400

    # 1. Create a new session token
    token = str(uuid.uuid4())
    database.create_session(token)

    # 2. Pre-populate answers with client info so dashboard shows it right away
    pre_answers = {}
    if client_name:
        pre_answers['client_name'] = client_name
    if email:
        pre_answers['email_address'] = email
    if phone:
        pre_answers['contact_number'] = phone
    if project_name:
        pre_answers['project_name'] = project_name
    if location:
        pre_answers['project_location'] = location

    if pre_answers:
        database.save_answers(token, pre_answers, current_chapter=0, progress_percent=0)

    # 3. Create or retrieve the architect project record
    project = architect_db.get_or_create_project(
        token,
        client_name=client_name,
        location=location,
        project_type='Residential Project'
    )
    # Sync metadata so client_name/location are visible in project list
    architect_db.sync_project_metadata(token)

    # 4. Build the questionnaire URL dynamically
    base_url = request.host_url.rstrip('/')
    questionnaire_url = f"{base_url}/questionnaire/{token}"

    return jsonify({
        'success': True,
        'token': token,
        'project_id': project['id'],
        'url': questionnaire_url
    })


def format_whatsapp_number(phone):
    """Format phone number for WhatsApp deep-links.
    Automatically handles 10-digit Indian mobile numbers (e.g. starting with 6,7,8,9)
    by prepending country code '91'.
    Strips non-digits, leading zeros, hyphens, and spaces.
    """
    if not phone:
        return ""
    digits = "".join(c for c in str(phone) if c.isdigit())
    if not digits:
        return ""
    
    # Strip leading zero if present (e.g. 09567843662 -> 9567843662)
    digits = digits.lstrip('0')
    
    # If standard 10-digit Indian mobile number (e.g. 9567843662), prepend '91'
    if len(digits) == 10:
        return "91" + digits
    
    return digits


@app.route('/api/architect/send-questionnaire', methods=['POST'])
@login_required
@auth.require_role('architect', 'admin')
def architect_send_questionnaire():
    """Send the questionnaire link to a client phone/WhatsApp.
    Currently returns the WhatsApp deep-link for the frontend to open.
    Wire in a real SMS/WhatsApp provider via notify.py when ready.
    """
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    phone = (data.get('phone') or '').strip()
    client_name = (data.get('client_name') or 'Client').strip()

    if not token or not phone:
        return jsonify({'success': False, 'error': 'token and phone are required'}), 400

    base_url = request.host_url.rstrip('/')
    questionnaire_url = f"{base_url}/questionnaire/{token}"

    # Attempt notify via configured provider (email/WhatsApp placeholder)
    try:
        notify.notify_questionnaire_link(client_name, phone, questionnaire_url)
    except Exception as e:
        app.logger.warning(f"[SEND] Notification provider error: {e}")

    # Return WhatsApp deep-link so the frontend can open it
    message = f"Hello {client_name},\n\nPlease complete your Shameer Associates Residential Design Questionnaire using the link below:\n\n{questionnaire_url}\n\nThank you,\nShameer Associates"
    import urllib.parse
    wa_number = format_whatsapp_number(phone)
    wa_url = f"https://wa.me/{wa_number}?text={urllib.parse.quote(message)}"

    return jsonify({
        'success': True,
        'wa_url': wa_url,
        'questionnaire_url': questionnaire_url
    })


@app.route('/api/architect/project/<int:project_id>/pdf', methods=['GET'])
@login_required
@auth.require_role('architect', 'admin')
def download_architect_pdf(project_id):
    try:
        project = architect_db.get_full_project_detail(project_id)
        if not project:
            return jsonify({'success': False, 'error': 'Project not found'}), 404

        pdf_bytes = generate_architect_pdf_bytes(project, QUESTIONNAIRE_SCHEMA)
        v_num = 1
        try:
            version_id, v_num = architect_db.store_pdf_version(project_id, pdf_bytes, 'architect_export', getattr(current_user, 'id', None))
        except Exception as store_err:
            app.logger.warning(f"Could not store pdf version history: {store_err}")

        client_name = project.get('client_name', 'Client')
        safe_name = "".join(c for c in client_name if c.isalnum() or c in (' ', '_', '-')).strip() or 'Client'
        filename = f"Shameer_Associates_Project_Brief_{project.get('project_uid', 'SA')}_{safe_name.replace(' ', '_')}_v{v_num}.pdf"

        is_download = request.args.get('download', '1') == '1'
        resp = send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=is_download,
            download_name=filename
        )
        resp.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return resp
    except Exception as e:
        app.logger.error(f"Error generating PDF for project {project_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f"Failed to generate PDF: {str(e)}"}), 500


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'Shameer Associates Design Questionnaire & Architect API'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
