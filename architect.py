import os
import json
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify, send_file
import io
from flask_login import login_user, logout_user, login_required, current_user

import architect_db
from auth import require_role, User, verify_password
import pdf_generator

architect_bp = Blueprint('architect_bp', __name__)

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'questionnaire_schema.json')
with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
    QUESTIONNAIRE_SCHEMA = json.load(f)


@architect_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('architect_bp.dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        user_dict = architect_db.get_user_by_email(email)
        if user_dict and verify_password(password, user_dict['password_hash']):
            user = User(user_dict)
            login_user(user)
            architect_db.update_last_login(user.id)
            return redirect(url_for('architect_bp.dashboard'))
            
        flash('Invalid email or password.', 'error')
        
    return render_template('architect_login.html')


@architect_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('architect_bp.login'))


@architect_bp.route('/')
@architect_bp.route('/dashboard')
@require_role('architect', 'admin')
def dashboard():
    status_filter = request.args.get('status', 'all')
    search_query = request.args.get('q', '').strip()
    
    projects = architect_db.get_project_list(status_filter=status_filter, search=search_query)
    stats = architect_db.get_dashboard_stats()
    notifications = architect_db.get_notifications(user_id=current_user.id)
    
    return render_template(
        'architect_dashboard.html',
        projects=projects,
        stats=stats,
        notifications=notifications,
        status_filter=status_filter,
        search_query=search_query
    )


@architect_bp.route('/project/<int:project_id>')
@require_role('architect', 'admin')
def project_detail(project_id):
    project = architect_db.get_full_project_detail(project_id)
    if not project:
        abort(404)
        
    # Get all users (architects/admins) to support assignment
    architects = [u for u in architect_db.get_all_users() if u['role'] in ('architect', 'admin')]
    
    # Render detail template with schema and visual references lookup support
    return render_template(
        'architect_project.html',
        project=project,
        schema=QUESTIONNAIRE_SCHEMA,
        architects=architects
    )


@architect_bp.route('/project/<int:project_id>/status', methods=['POST'])
@require_role('architect', 'admin')
def update_status(project_id):
    new_status = request.form.get('status')
    note = request.form.get('note', '')
    if not new_status:
        flash('Missing status field.', 'error')
        return redirect(url_for('architect_bp.project_detail', project_id=project_id))
        
    success = architect_db.change_project_status(project_id, current_user.id, new_status, note)
    if success:
        flash('Project status updated successfully.', 'success')
    else:
        flash('Failed to update project status.', 'error')
        
    return redirect(url_for('architect_bp.project_detail', project_id=project_id))


@architect_bp.route('/project/<int:project_id>/assign', methods=['POST'])
@require_role('architect', 'admin')
def assign(project_id):
    architect_id = request.form.get('assigned_architect_id')
    if not architect_id:
        flash('Missing architect ID.', 'error')
        return redirect(url_for('architect_bp.project_detail', project_id=project_id))
        
    architect_db.assign_architect(project_id, int(architect_id), current_user.id)
    flash('Architect assigned successfully.', 'success')
    return redirect(url_for('architect_bp.project_detail', project_id=project_id))


@architect_bp.route('/project/<int:project_id>/note', methods=['POST'])
@require_role('architect', 'admin')
def add_project_note(project_id):
    content = request.form.get('content', '').strip()
    note_type = request.form.get('note_type', 'general')
    
    if not content:
        flash('Note content cannot be empty.', 'error')
        return redirect(url_for('architect_bp.project_detail', project_id=project_id))
        
    architect_db.add_note(project_id, current_user.id, content, note_type)
    flash('Note added successfully.', 'success')
    return redirect(url_for('architect_bp.project_detail', project_id=project_id))


@architect_bp.route('/project/<int:project_id>/note/<int:note_id>/edit', methods=['POST'])
@require_role('architect', 'admin')
def edit_project_note(project_id, note_id):
    content = request.form.get('content', '').strip()
    note_type = request.form.get('note_type')
    
    if not content:
        flash('Note content cannot be empty.', 'error')
        return redirect(url_for('architect_bp.project_detail', project_id=project_id))
        
    architect_db.edit_note(note_id, current_user.id, content, note_type)
    flash('Note updated successfully.', 'success')
    return redirect(url_for('architect_bp.project_detail', project_id=project_id))


@architect_bp.route('/project/<int:project_id>/note/<int:note_id>/delete', methods=['POST'])
@require_role('architect', 'admin')
def delete_project_note(project_id, note_id):
    architect_db.delete_note(note_id, current_user.id)
    flash('Note deleted successfully.', 'success')
    return redirect(url_for('architect_bp.project_detail', project_id=project_id))


@architect_bp.route('/project/<int:project_id>/edit_answer', methods=['POST'])
@require_role('architect', 'admin')
def edit_project_answer(project_id):
    project = architect_db.get_project_by_id(project_id)
    if not project:
        abort(404)
        
    if request.is_json:
        data = request.get_json()
        question_id = data.get('question_id')
        new_value = data.get('new_value')
        reason = data.get('reason', '')
    else:
        question_id = request.form.get('question_id')
        new_value_raw = request.form.get('new_value')
        reason = request.form.get('reason', '')
        try:
            new_value = json.loads(new_value_raw)
        except Exception:
            new_value = new_value_raw
            
    if not question_id:
        if request.is_json:
            return jsonify({'success': False, 'error': 'Missing question_id'}), 400
        flash('Missing question ID.', 'error')
        return redirect(url_for('architect_bp.project_detail', project_id=project_id))
        
    architect_db.edit_answer(project_id, project['session_token'], current_user.id, question_id, new_value, reason)
    
    # Sync overview fields (client name, location, project type) if changed
    architect_db.sync_project_metadata(project['session_token'])
    
    if request.is_json:
        return jsonify({'success': True})
        
    flash('Client response updated successfully.', 'success')
    return redirect(url_for('architect_bp.project_detail', project_id=project_id))


@architect_bp.route('/project/<int:project_id>/pdf', methods=['GET'])
@require_role('architect', 'admin')
def download_project_pdf(project_id):
    project = architect_db.get_full_project_detail(project_id)
    if not project:
        abort(404)
        
    # Generate bytes with custom architect review sections appended
    pdf_bytes = pdf_generator.generate_pdf_bytes(
        project['session'],
        QUESTIONNAIRE_SCHEMA,
        project_data=project
    )
    
    client_name = project['client_name'] or 'Client'
    safe_name = "".join(c for c in client_name if c.isalnum() or c in (' ', '_', '-')).strip() or 'Client'
    filename = f"Shameer_Associates_Project_Brief_{safe_name.replace(' ', '_')}_{project['project_uid']}.pdf"
    
    # Record generated version to database
    architect_db.store_pdf_version(project_id, pdf_bytes, label='architect_review', generated_by_id=current_user.id)
    
    is_download = request.args.get('download', '0') == '1'
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=is_download,
        download_name=filename
    )


@architect_bp.route('/notification/<int:notification_id>/read', methods=['POST'])
@require_role('architect', 'admin')
def mark_read(notification_id):
    architect_db.mark_notification_read(notification_id)
    if request.is_json:
        return jsonify({'success': True})
    return redirect(request.referrer or url_for('architect_bp.dashboard'))
