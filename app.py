from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, User, Tournament, Team, Player, Match, init_default_data, get_default_tournament
from datetime import datetime, timedelta, date
from functools import wraps
import os

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'tourneytrack')

# Database configuration - supports both local SQLite and remote PostgreSQL
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    # Heroku PostgreSQL URL fix (Heroku uses postgres://, SQLAlchemy needs postgresql://)
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    # Fallback to SQLite for local development
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tournament.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Verify connections before using them
    'pool_recycle': 300,    # Recycle connections after 5 minutes
}

db.init_app(app)

with app.app_context():
    db.create_all()
    init_default_data()
    print("Database initialized successfully!")

# Decorators for authentication
def require_smc_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session.get('user_type') != 'smc':
            flash('Please log in as SMC to access this page.', 'error')
            return redirect(url_for('smc_login'))
        return f(*args, **kwargs)
    return decorated_function

def require_team_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'team_id' not in session or session.get('user_type') != 'team':
            flash('Please log in as Team to access this page.', 'error')
            return redirect(url_for('team_login'))
        return f(*args, **kwargs)
    return decorated_function


# Routes

@app.route('/')
def index():
    """Home page with login options"""
    # Get some basic stats for display
    tournament = get_default_tournament()
    total_teams = Team.query.filter_by(is_active=True).count()
    upcoming_matches = Match.query.filter(
        Match.status == 'scheduled',
        Match.date >= datetime.now().date()
    ).count()
    
    return render_template('index.html', 
                         tournament=tournament,
                         total_teams=total_teams,
                         upcoming_matches=upcoming_matches)

@app.route('/login-smc', methods=['GET', 'POST'])
def smc_login():
    """SMC login"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_type'] = 'smc'
            session['username'] = user.username
            flash('Login successful!', 'success')
            return redirect(url_for('smc_dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('login-smc.html')

@app.route('/login-team', methods=['GET', 'POST'])
def team_login():
    """Team login"""
    if request.method == 'POST':
        team_id = request.form['team_id']
        password = request.form['password']
        
        team = Team.query.filter_by(team_id=team_id).first()
        if team and team.check_password(password):
            session['team_id'] = team.team_id
            session['user_type'] = 'team'
            session['team_name'] = team.name
            flash('Login successful!', 'success')
            return redirect(url_for('team_dashboard'))
        else:
            flash('Invalid team credentials!', 'error')
    
    return render_template('login-team.html')

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# SMC Routes

@app.route('/smc-dashboard')
@require_smc_login
def smc_dashboard():
    """SMC dashboard"""
    tournament = get_default_tournament()
    
    # Get statistics
    stats = {
        'total_teams': Team.query.filter_by(is_active=True).count(),
        'total_players': Player.query.filter_by(is_active=True).count(),
        'upcoming_matches': Match.query.filter(
            Match.status == 'scheduled',
            Match.date >= date.today()
        ).count(),
        'completed_matches': Match.query.filter_by(status='completed').count()
    }
    
    # Get recent teams
    tournament_teams = Team.query.filter_by(is_active=True).order_by(Team.created_at.desc()).all()
    
    # Get upcoming matches
    upcoming_matches = Match.query.filter(
        Match.status == 'scheduled',
        Match.date >= date.today()
    ).order_by(Match.date, Match.time).limit(5).all()
    
    return render_template('smc-dashboard.html',
                         tournament=tournament,
                         stats=stats,
                         tournament_teams=tournament_teams,
                         upcoming_matches=upcoming_matches)

@app.route('/register-team', methods=['GET', 'POST'])
@require_smc_login
def register_team():
    """UC_01: Register Player/Team"""
    if request.method == 'POST':
        try:        
            tournament = get_default_tournament()

            # Store form data in variables first
            team_name = request.form.get('team_name', '').strip()
            team_id = request.form.get('team_id', '').strip()
            department = request.form.get('department', '').strip()
            manager_name = request.form.get('manager_name', '').strip()
            password = request.form.get('password', '').strip()
            manager_contact = request.form.get('manager_contact', '').strip()

            # Validate required fields using the stored variables
            
            if not team_id:
                flash('Team ID is required!', 'error')
                return redirect(url_for('register_team'))
            
            # Check for duplicates using the stored variables
            existing_team_id = Team.query.filter_by(team_id=team_id).first()
            if existing_team_id:
                flash('A team with this Team ID already exists!', 'error')
                return redirect(url_for('register_team'))
            
            if not team_name:
                flash('Team name is required!', 'error')
                return redirect(url_for('register_team'))

            existing_team_name = Team.query.filter_by(
                name=team_name, 
                tournament_id=tournament.id
            ).first()
            if existing_team_name:
                flash('A team with this name already exists in the tournament!', 'error')
                return redirect(url_for('register_team'))
            

            if not department:
                flash('Department is required!', 'error')
                return redirect(url_for('register_team'))

            if not manager_name:
                flash('Manager name is required!', 'error')
                return redirect(url_for('register_team'))

            if not password:
                flash('Password is required!', 'error')
                return redirect(url_for('register_team'))

            



            # Create team using the validated variables
            team = Team(
                name=team_name,
                department=department,
                manager_name=manager_name,
                manager_contact=manager_contact,
                team_id=team_id,
                tournament_id=tournament.id
            )
            team.set_password(password)

            db.session.add(team)
            db.session.flush()  # Get team.id
            
            
            # Add players if provided
            players_added = 0
            while True:    # Unbound number of players can be added
                i = players_added + 1
                name = request.form.get(f'player_{i}_name', '').strip()
                if name:
                    player = Player(
                        name=name,
                        roll_number=int(request.form.get(f'player_{i}_roll', '')),
                        department=request.form.get(f'player_{i}_dept', team.department),
                        year=request.form.get(f'player_{i}_year', ''),
                        contact=request.form.get(f'player_{i}_contact', ''),
                        team_id=team.team_id
                    )
                    
                    db.session.add(player)
                    players_added += 1
                else:
                    break
            
            db.session.commit()
            flash(f'Team "{team.name}" registered successfully with {players_added} players! Team ID: {team.team_id}', 'success')
            return redirect(url_for('smc_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error registering team: {str(e)}', 'error')
    
    return render_template('register-team.html')


@app.route('/schedule-matches', methods=['GET', 'POST'])
@require_smc_login
def schedule_matches():
    """UC_03: Schedule Adding"""

    tournament = get_default_tournament()

    if request.method == 'POST':
        try:
            # Get team names before creating the match for better error handling
            team1 = Team.query.get(request.form['team1_id'])
            team2 = Team.query.get(request.form['team2_id'])
            
            if not team1 or not team2:
                flash('Invalid team selection!', 'error')
                return redirect(url_for('schedule_matches'))
            
            match = Match(
                tournament_id=tournament.id,
                team1_id=team1.team_id,  # Use team_id (string) instead of id (integer)
                team2_id=team2.team_id,  # Use team_id (string) instead of id (integer)
                date=datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
                time=datetime.strptime(request.form['time'], '%H:%M').time(),
                venue=request.form['venue']
            )
            
            # Basic validation
            if team1.team_id == team2.team_id:
                flash('A team cannot play against itself!', 'error')
                return redirect(url_for('schedule_matches'))
            
            # Match date must be within tournament period
            if match.date < tournament.start_date or match.date > tournament.end_date:
                flash(f'Match date must be between {tournament.start_date} and {tournament.end_date}', 'error')
                return redirect(url_for('schedule_matches'))
            
            # if match.date < date.today():
            #     flash('Cannot schedule matches in the past!', 'error')
            #     return redirect(url_for('schedule_matches'))
            
            # Check for venue conflicts (same venue, date, time)
            existing_match = Match.query.filter_by(
                venue=match.venue,
                date=match.date,
                time=match.time
            ).first()
            
            if existing_match:
                flash(f'Venue "{match.venue}" is already booked at {match.time} on {match.date}', 'error')
                return redirect(url_for('schedule_matches'))
            
            # Team Conflict Check - Check if either team already has a match at the same time
            existing_team_match = Match.query.filter(
                db.or_(
                    db.and_(Match.team1_id == match.team1_id, Match.date == match.date, Match.time == match.time),
                    db.and_(Match.team2_id == match.team1_id, Match.date == match.date, Match.time == match.time),
                    db.and_(Match.team1_id == match.team2_id, Match.date == match.date, Match.time == match.time),
                    db.and_(Match.team2_id == match.team2_id, Match.date == match.date, Match.time == match.time)
                )
            ).first()

            if existing_team_match:
                flash('One of the teams already has a match scheduled at this time', 'error')
                return redirect(url_for('schedule_matches'))
            
            db.session.add(match)
            db.session.commit()
            
            flash(f'Match scheduled: {match.versus_display} on {match.date} at {match.time}', 'success')
            return redirect(url_for('schedule_matches'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error scheduling match: {str(e)}', 'error')
    
    
    # Get active teams for dropdown
    active_teams = Team.query.filter_by(is_active=True).order_by(Team.name).all()
    all_teams = Team.query.all()

    # Get all matches
    all_matches = Match.query.order_by(Match.date, Match.time).all()
    
    # Separate upcoming and completed
    today = date.today()
    now = datetime.now()
    today = date.today()
    upcoming_matches = [m for m in all_matches if m.is_upcoming]
    completed_matches = [m for m in all_matches if datetime.combine(m.date, m.time) < datetime.now()]


    return render_template('schedule-matches.html',
                           teams=active_teams,
                           tournament=tournament,
                           all_teams=all_teams,
                           upcoming_matches=upcoming_matches,
                           completed_matches=completed_matches)

@app.route('/add-results', methods=['GET', 'POST'])
@require_smc_login
def add_results():
    """UC_05: Result Announcements"""
    if request.method == 'POST':
        try:
            match_id = int(request.form['match_id'])
            match = Match.query.get_or_404(match_id)
            
            if match.status == 'completed':
                flash('Results have already been entered for this match!', 'error')
                return redirect(url_for('add_results'))

            if match.date > date.today():
                flash('Cannot enter results for future matches!', 'error')
                return redirect(url_for('add_results'))
            
            # Update match with results
            match.team1_score = request.form['team1_score'].strip()
            match.team2_score = request.form['team2_score'].strip()
            match.status = 'completed'
            
            # Set winner if provided
            winner_id = request.form.get('winner_id')
            if winner_id and winner_id != '':
                if winner_id not in [match.team1_id, match.team2_id]:
                    flash('Winner must be one of the participating teams!', 'error')
                    return redirect(url_for('add_results'))
                match.winner_id = winner_id
            else:
                match.winner_id = None  # For draws or no winner scenarios
            
            db.session.commit()
            
            flash(f'Results updated for match: {match.team1.name} vs {match.team2.name}', 'success')
            return redirect(url_for('add_results'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating results: {str(e)}', 'error')
    
    # Get matches that can have results added (scheduled matches in the past or today)
    today = date.today()
    pending_matches = Match.query.filter(
        Match.status == 'scheduled',
        Match.date <= today
    ).order_by(Match.date, Match.time).all()
    
    # Get completed matches for display
    completed_matches = Match.query.filter_by(status='completed').order_by(
        Match.date.desc(), Match.time.desc()
    ).limit(10).all()

    # Get all active teams for winner dropdown
    active_teams = Team.query.filter_by(is_active=True).all()

    return render_template('add-results.html',
                     pending_matches=pending_matches,
                     completed_matches=completed_matches,
                     teams=active_teams)
    
    
# Team Routes

@app.route('/team-dashboard')
@require_team_login
def team_dashboard():
    """Team dashboard with team info, stats, fixtures and results"""
    team_id = session['team_id']
    team = Team.query.filter_by(team_id=team_id).first()
    
    if not team:
        flash('Team not found!', 'error')
        return redirect(url_for('team_login'))
    
    # Get team statistics using existing methods
    upcoming_matches = team.get_upcoming_matches()
    completed_matches = team.get_completed_matches()
    record = team.get_match_record()
    
    # Get active players using the relationship
    active_players = [p for p in team.players if p.is_active]
    
    return render_template('team-dashboard.html',
                         team=team,
                         players=active_players,
                         upcoming_matches=upcoming_matches,
                         completed_matches=completed_matches,
                         record=record)

@app.route('/update-profile', methods=['GET', 'POST'])
@require_team_login
def update_profile():
    """UC_02: Team/Player's Profile Updation - handles team details AND player management"""
    team_id = session['team_id']
    team = Team.query.filter_by(team_id=team_id).first()
    
    if not team:
        flash('Team not found!', 'error')
        return redirect(url_for('team_login'))
    
    if request.method == 'POST':
        try:
            action = request.form.get('action', 'update_team')
            
            if action == 'update_team':
                # Update team information
                if request.form.get('manager_name'):
                    team.manager_name = request.form['manager_name'].strip()
                if request.form.get('manager_contact'):
                    team.manager_contact = request.form['manager_contact'].strip()
                
                db.session.commit()
                flash('Team details updated successfully!', 'success')
                
            elif action == 'update_players':
                # Update existing players
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
                # Add new player
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
                # Remove player (set inactive)
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
    
    # GET request - display form with current data
    active_players = [p for p in team.players if p.is_active]
    
    return render_template('update-profile.html', team=team, players=active_players)

# Public Routes (for viewers)

@app.route('/public-view')
def public_view():
    """Combined public view of fixtures and results"""
    tournament = get_default_tournament()
    
    # Get upcoming matches
    upcoming_matches = Match.query.filter(
        Match.status == 'scheduled',
        Match.date >= date.today()
    ).order_by(Match.date, Match.time).all()
    
    # Get completed matches
    completed_matches = Match.query.filter_by(status='completed').order_by(
        Match.date.desc(), Match.time.desc()
    ).limit(10).all()  # Show last 10 results
    
    return render_template('public-view.html',
                         tournament=tournament,
                         upcoming_matches=upcoming_matches,
                         completed_matches=completed_matches)

if __name__=="__main__":
    app.run(debug=True, port=5000)