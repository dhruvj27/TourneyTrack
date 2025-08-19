from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, User, Tournament, Team, Player, Match, init_default_data, get_default_tournament
from datetime import datetime, timedelta, date
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tourneytrack'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tournament.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
            session['team_id'] = team.id
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

            # Create team
            team = Team(
                name=request.form['team_name'],
                department=request.form['department'],
                manager_name=request.form['manager_name'],
                manager_contact=request.form['manager_contact'],
                team_id=request.form['team_id'],
                tournament_id = tournament.id
            )
            team.set_password(request.form['password'])
            
            db.session.add(team)
            db.session.flush()  # Get team.id
            
            
            # Add players if provided
            players_added = 0
            while True:    # Unbound number of players can be added
                name = request.form.get(f'player_{i}_name', '').strip()
                if name:
                    player = Player(
                        name=name,
                        roll_number=request.form.get(f'player_{i}_roll', ''),
                        department=request.form.get(f'player_{i}_dept', team.department),
                        year=request.form.get(f'player_{i}_year', ''),
                        contact=request.form.get(f'player_{i}_contact', ''),
                        team_id=team.id,
                    )
                    db.session.add(player)
                    players_added +=1
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
    if request.method == 'POST':
        try:
            tournament = get_default_tournament()
            
            match = Match(
                tournament_id=tournament.id,
                team1_id=request.form['team1_id'],
                team2_id=request.form['team2_id'],
                date=datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
                time=datetime.strptime(request.form['time'], '%H:%M').time(),
                venue=request.form['venue']
            )
            
            # Basic validation
            if match.team1_id == match.team2_id:
                flash('A team cannot play against itself!', 'error')
                return redirect(url_for('schedule_matches'))
            
            # Check for venue conflicts (same venue, date, time)
            existing_match = Match.query.filter_by(
                venue=match.venue,
                date=match.date,
                time=match.time
            ).first()
            
            if existing_match:
                flash(f'Venue "{match.venue}" is already booked at {match.time} on {match.date}', 'error')
                return redirect(url_for('schedule_matches'))
            
            db.session.add(match)
            db.session.commit()
            
            flash(f'Match scheduled: {match.team1.name} vs {match.team2.name} on {match.date} at {match.time}', 'success')
            return redirect(url_for('smc_fixtures'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error scheduling match: {str(e)}', 'error')
    
    # Get active teams for dropdown
    active_teams = Team.query.filter_by(is_active=True).order_by(Team.name).all()
    
    return render_template('schedule-matches.html', teams=active_teams)


if __name__=="__main__":
    app.run(debug=True,port=5000)