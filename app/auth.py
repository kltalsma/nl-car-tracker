"""
Simple authentication for Flask app
Uses environment variables for credentials
"""
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask import redirect, url_for, request, render_template, flash
from werkzeug.security import check_password_hash, generate_password_hash
import os

class User(UserMixin):
    def __init__(self, id):
        self.id = id

def init_auth(app):
    """Initialize Flask-Login"""
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User(user_id)
    
    return login_manager

def check_credentials(username, password):
    """Check if credentials are valid using environment variables"""
    valid_username = os.environ.get('APP_USERNAME', 'admin')
    valid_password = os.environ.get('APP_PASSWORD', 'changeme')
    
    return username == valid_username and password == valid_password
