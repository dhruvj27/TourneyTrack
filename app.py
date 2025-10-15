from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from models import (
    db,
    User,
    Tournament,
    Team,
    Player,
    Match,
    TournamentTeam,
    Notification,
    init_default_data,
    get_default_tournament,
    ensure_schema_integrity,
)
from datetime import datetime, timedelta, date
from functools import wraps
import os
from blueprints.auth import auth_bp, load_current_user

from blueprints.smc import smc_bp
from blueprints.team import team_bp

app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'tourneytrack')

# Database configuration - supports both local SQLite and remote PostgreSQL
DATABASE_URL = os.environ.get('DATABASE_URL')

sqlite_path = None

if DATABASE_URL:
    # Heroku PostgreSQL URL fix (postgres:// → postgresql://)
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    # Fallback to SQLite for local development
    default_sqlite_dir = os.path.join(BASE_DIR, 'instance')
    os.makedirs(default_sqlite_dir, exist_ok=True)
    sqlite_path = os.environ.get('SQLITE_PATH', os.path.join(default_sqlite_dir, 'tournament.db'))
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{sqlite_path}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

db.init_app(app)

with app.app_context():
    is_new_db = False
    if sqlite_path:
        is_new_db = not os.path.exists(sqlite_path)

    db.create_all()
    ensure_schema_integrity()

    # Seed defaults only if database was freshly created or critical records missing
    if is_new_db or not User.query.filter_by(username='admin').first():
        init_default_data()

    print("Database initialized successfully!")

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(smc_bp)
app.register_blueprint(team_bp)

@app.before_request
def before_request():
    """Load current user before every request to ANY route"""
    load_current_user()

# Sprint 1 Decorators (DEPRECATED - kept for backward compatibility with old Sprint 1 routes)
def require_smc_login(f):
    """DEPRECATED: Use require_smc from blueprints.smc instead"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Support new auth blueprint session format (role='smc')
        if session.get('role') == 'smc':
            return f(*args, **kwargs)
        # Support old Sprint 1 session format (user_type='smc')
        if 'username' not in session or session.get('user_type') != 'smc':
            flash('Please log in as SMC to access this page.', 'error')
            return redirect(url_for('smc_login'))
        return f(*args, **kwargs)
    return decorated_function

def require_team_login(f):
    """DEPRECATED: Use require_team_manager from blueprints.auth instead"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Support new auth blueprint session format (role='team_manager')
        if session.get('role') == 'team_manager':
            # Map user_id to team_id for backward compatibility with old routes
            if 'user_id' in session and 'team_id' not in session:
                session['team_id'] = session['user_id']
            return f(*args, **kwargs)
        # Support old Sprint 1 session format (user_type='team')
        if 'team_id' not in session or session.get('user_type') != 'team':
            flash('Please log in as Team to access this page.', 'error')
            return redirect(url_for('team_login'))
        return f(*args, **kwargs)
    return decorated_function

# Sprint 1 Routes (Keep for backward compatibility)

@app.route('/')
def index():
    """Home page with login options"""
    tournaments = Tournament.query.order_by(Tournament.start_date.asc()).all()
    featured_tournament = tournaments[0] if tournaments else get_default_tournament()

    total_teams = Team.query.filter_by(is_active=True).count()
    total_tournaments = len(tournaments)

    today = date.today()
    upcoming_base = Match.query.filter(
        Match.status == 'scheduled',
        Match.date >= today,
    )
    upcoming_matches_count = upcoming_base.count()
    next_fixture = (
        upcoming_base.order_by(Match.date.asc(), Match.time.asc()).first()
    )

    current_match = (
        Match.query.filter(Match.status == 'active')
        .order_by(Match.date.desc(), Match.time.desc())
        .first()
    )

    latest_result = (
        Match.query.filter(Match.status == 'completed')
        .order_by(Match.date.desc(), Match.time.desc())
        .first()
    )

    unread_notification_count = 0
    if getattr(g, 'current_user', None):
        unread_notification_count = Notification.query.filter_by(
            user_id=g.current_user.id, is_read=False
        ).count()

    return render_template(
        'index.html',
        featured_tournament=featured_tournament,
        tournaments=tournaments,
        total_teams=total_teams,
        total_tournaments=total_tournaments,
        upcoming_matches_count=upcoming_matches_count,
        next_fixture=next_fixture,
        current_match=current_match,
        latest_result=latest_result,
        unread_notification_count=unread_notification_count,
    )

@app.route('/login-smc', methods=['GET', 'POST'])
def smc_login():
    """Sprint 1: SMC login (old route - will be replaced by /auth/login)"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password) and user.role == 'smc':
            session['user_type'] = 'smc'
            session['username'] = user.username
            flash('Login successful!', 'success')
            return redirect(url_for('smc_dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('login-smc.html')

@app.route('/login-team', methods=['GET', 'POST'])
def team_login():
    """Sprint 1: Team login (old route - deprecated, teams no longer have passwords)"""
    flash('Team login has been updated. Please use the new login system.', 'info')
    return redirect(url_for('auth.login'))

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# SMC Routes (Sprint 1 - kept for backward compatibility, use smc_bp routes instead)

@app.route('/smc-dashboard')
@require_smc_login
def smc_dashboard():
    """SMC dashboard - OLD ROUTE (use /smc/dashboard instead)"""
    return redirect(url_for('smc.dashboard'))

@app.route('/register-team', methods=['GET', 'POST'])
@require_smc_login
def register_team():
    """UC_01: Register Player/Team - OLD ROUTE (use /smc/tournament/<id>/register-team instead)"""
    tournament = get_default_tournament()
    return redirect(url_for('smc.register_team', tournament_id=tournament.id))

@app.route('/schedule-matches', methods=['GET', 'POST'])
@require_smc_login
def schedule_matches():
    """UC_03: Schedule Adding - OLD ROUTE (use /smc/tournament/<id>/schedule-matches instead)"""
    tournament = get_default_tournament()
    return redirect(url_for('smc.schedule_matches', tournament_id=tournament.id))

@app.route('/add-results', methods=['GET', 'POST'])
@require_smc_login
def add_results():
    """UC_05: Result Announcements - OLD ROUTE (use /smc/tournament/<id>/add-results instead)"""
    tournament = get_default_tournament()
    return redirect(url_for('smc.add_results', tournament_id=tournament.id))

@app.route('/update-profile', methods=['GET', 'POST'])
@require_team_login
def update_profile():
    """UC_02: Team/Player's Profile Updation"""
    team_id = session['team_id']
    team = Team.query.filter_by(team_id=team_id).first()
    
    if not team:
        flash('Team not found!', 'error')
        return redirect(url_for('team_login'))
    
    if request.method == 'POST':
        try:
            action = request.form.get('action', 'update_team')
            
            if action == 'update_team':
                if request.form.get('manager_name'):
                    team.manager_name = request.form['manager_name'].strip()
                if request.form.get('manager_contact'):
                    team.manager_contact = request.form['manager_contact'].strip()
                
                db.session.commit()
                flash('Team details updated successfully!', 'success')
                
            elif action == 'update_players':
                active_players = [p for p in team.players if p.is_active]
                for player in active_players:
                    player_prefix = f'player_{player.id}_'
                    update_data = {}
                    
                    for field in ['name', 'contact', 'department', 'year', 'roll_number']:
                        form_key = player_prefix + field
                        if form_key in request.form:
                            value = request.form[form_key].strip()
                            if value:
                                update_data[field] = value
                    
                    if update_data:
                        player.update_player(**update_data)
                
                db.session.commit()
                flash('Player details updated successfully!', 'success')
                
            elif action == 'add_player':
                player = Player(
                    name=request.form['new_player_name'].strip(),
                    roll_number=request.form.get('new_player_roll', ''),
                    contact=request.form.get('new_player_contact', ''),
                    department=request.form.get('new_player_department', team.department),
                    year=request.form.get('new_player_year', ''),
                    team_id=team_id
                )
                
                db.session.add(player)
                db.session.commit()
                flash('Player added successfully!', 'success')
                
            elif action == 'remove_player':
                player_id = int(request.form['player_id'])
                player = Player.query.filter_by(id=player_id, team_id=team_id).first()
                
                if player:
                    player.is_active = False
                    db.session.commit()
                    flash('Player removed successfully!', 'success')
                else:
                    flash('Player not found!', 'error')
            
            return redirect(url_for('update_profile'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')
    
    # GET request - display form
    active_players = [p for p in team.players if p.is_active]
    
    return render_template('update-profile.html', team=team, players=active_players)

# Public Routes

@app.route('/public-view')
def public_view():
    """Combined public view of fixtures and results"""
    tournament = get_default_tournament()
    
    # Get upcoming matches
    upcoming_matches = Match.query.filter(
        Match.tournament_id == tournament.id,
        Match.status == 'scheduled',
        Match.date >= date.today()
    ).order_by(Match.date, Match.time).all()
    
    # Get completed matches
    completed_matches = Match.query.filter(
        Match.tournament_id == tournament.id,
        Match.status == 'completed'
    ).order_by(Match.date.desc(), Match.time.desc()).limit(10).all()
    
    return render_template('public-view.html',
                         tournament=tournament,
                         upcoming_matches=upcoming_matches,
                         completed_matches=completed_matches)


if __name__ == "__main__":
    app.run(debug=True, port=5000)