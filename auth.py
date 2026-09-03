"""
auth.py
Flask-Login user model and authentication helpers for Phase 2.
"""
from flask_login import LoginManager, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask import redirect, url_for, abort
from flask_login import current_user

import architect_db

login_manager = LoginManager()
login_manager.login_view = 'architect_login'
login_manager.login_message = 'Please sign in to access the Architect Workspace.'
login_manager.login_message_category = 'info'


class User(UserMixin):
    """Flask-Login user class backed by the users DB table."""

    def __init__(self, user_dict):
        self.id = user_dict['id']
        self.email = user_dict['email']
        self.full_name = user_dict['full_name']
        self.role = user_dict['role']
        self.is_active_flag = bool(user_dict.get('is_active', 1))

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self.is_active_flag

    def is_admin(self):
        return self.role == 'admin'

    def is_architect(self):
        return self.role in ('architect', 'admin')


@login_manager.user_loader
def load_user(user_id):
    user_dict = architect_db.get_user_by_id(int(user_id))
    if not user_dict:
        return None
    return User(user_dict)


def require_role(*roles):
    """Decorator: require one of the given roles. Must be used after @login_required."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('architect_login'))
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def hash_password(plaintext):
    return generate_password_hash(plaintext)


def verify_password(plaintext, hashed):
    return check_password_hash(hashed, plaintext)
