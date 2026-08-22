import os
import io
import json
import uuid
from flask import Flask, request, jsonify, send_file, render_template, send_from_directory
from werkzeug.utils import secure_filename

import database
from pdf_generator import generate_pdf_bytes

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB max upload
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize DB on start
database.init_db()

# Load static schema & visuals into memory cache
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'questionnaire_schema.json')
VISUALS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'visual_references.json')

with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
    QUESTIONNAIRE_SCHEMA = json.load(f)

with open(VISUALS_PATH, 'r', encoding='utf-8') as f:
    VISUAL_REFERENCES = json.load(f)


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
        # Create session on the fly if valid token format
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
    return jsonify({'success': True, 'saved_at': database.datetime.now().isoformat()})


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
    disposition = 'attachment' if is_download else 'inline'

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


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'Shameer Associates Design Questionnaire API'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
