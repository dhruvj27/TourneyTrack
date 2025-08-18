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
        if 'user_id' not in session or session.get('user_type') != 'smc':
            flash('Please log in as SMC to access this page.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def require_team_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'team_id' not in session or session.get('user_type') != 'team':
            flash('Please log in as Team to access this page.', 'error')
            return redirect(url_for('index'))
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

@app.route('/login/smc', methods=['GET', 'POST'])
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
    
    return render_template('smc/login.html')

@app.route('/login/team', methods=['GET', 'POST'])
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
    
    return render_template('team/login.html')

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# SMC Routes

@app.route('/smc/dashboard')
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
    
    return render_template('smc/dashboard.html',
                         tournament=tournament,
                         stats=stats,
                         recent_teams=tournament_teams,
                         upcoming_matches=upcoming_matches)

@app.route('/smc/register-team', methods=['GET', 'POST'])
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
                password=request.form['password'],
                tournament_id = tournament.id
            )
            
            db.session.add(team)
            db.session.flush()  # Get team.id
            
            # Register team for default tournament
            if tournament:
                tournament.teams.append(team)
            
            # Add players if provided
            players_data = []
            for i in range(1, 12):  # Support up to 11 players
                name = request.form.get(f'player_{i}_name', '').strip()
                if name:
                    players_data.append({
                        'name': name,
                        'roll_number': request.form.get(f'player_{i}_roll', ''),
                        'department': request.form.get(f'player_{i}_dept', team.department),
                        'year': request.form.get(f'player_{i}_year', ''),
                        'contact': request.form.get(f'player_{i}_contact', ''),
                    })
            
            # Create player records
            for player_data in players_data:
                player = Player(
                    team_id=team.id,
                    **player_data
                )
                db.session.add(player)
            
            db.session.commit()
            flash(f'Team "{team.name}" registered successfully! Team ID: {team.team_id}', 'success')
            return redirect(url_for('smc_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error registering team: {str(e)}', 'error')
    
    return render_template('smc/register_team.html')


if __name__=="__main__":
    app.run(debug=True,port=5000)