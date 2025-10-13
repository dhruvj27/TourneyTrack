from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from models import Team, db, User
from functools import wraps
from datetime import datetime
import pytz

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
IST = pytz.timezone('Asia/Kolkata')

# Helper function - load current user
def load_current_user():
    """Load user into g.current_user for easy access"""
    if 'user_id' in session:
        g.current_user = User.query.get(session['user_id'])
    else:
        g.current_user = None

# Register before_request
@auth_bp.before_app_request
def before_request():
    """Load current user before each request"""
    load_current_user()

# Decorators for authentication
def require_smc(f):
    """Require SMC role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.current_user:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        
        if g.current_user.role != 'smc':
            flash('Please use an SMC account to access this page.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def require_team_manager(f):
    """Require team manager role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.current_user:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        
        if g.current_user.role != 'team_manager':
            flash('Please use a Team manager account to access this page.', 'error')
            return redirect(url_for('auth.login'))
        
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    """Require any logged-in user"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.current_user:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def check_user_uniqueness(username, email):
    """
    Check if username or email already exists in database.
    Returns list of errors. Requires Flask app context.
    """
    errors = []
    
    if User.query.filter_by(username=username).first():
        errors.append("Username already exists")
    
    if User.query.filter_by(email=email).first():
        errors.append("Email already registered")
    
    return errors


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration for both SMC and team manager"""
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password'].strip()
        role = request.form['role']  # 'smc' or 'team_manager'
        
        # Validate format (no DB queries)
        errors = User.validate_format(username, email, password, role)
        
        # Check uniqueness (requires DB queries)
        if not errors:
            uniqueness_errors = check_user_uniqueness(username, email)
            errors.extend(uniqueness_errors)
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('auth/register.html')
        
        # Create user
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        
        try:
            db.session.add(user)
            db.session.commit()
            
            flash(f'Registration successful! You can now log in.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error during registration: {str(e)}', 'error')
            return render_template('auth/register.html')
    
    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Unified login for SMC and team manager"""
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            # Set session data
            session.clear()
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['logged_in_at'] = datetime.now(IST).isoformat()

            # Regenerate session ID
            session.modified = True

            flash(f'Login successful! Welcome, {user.username}.', 'success')
            
            # Route based on role
            if user.role == 'smc':
                return redirect(url_for('smc.dashboard'))
            elif user.role == 'team_manager':
                team = Team.query.filter_by(created_by=user.id, is_active=True).first()
            if team:
                return redirect(url_for('team.dashboard', team_id=team.team_id))
            else:
                flash("No team found. Please create one to continue.", "info")
            return redirect(url_for('team.create_team'))

    
    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))