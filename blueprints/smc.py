from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from models import db, User, Tournament, Team, Player, Match, TournamentTeam
from datetime import datetime, date
from functools import wraps
import pytz

smc_bp = Blueprint('smc', __name__, url_prefix='/smc')
IST = pytz.timezone('Asia/Kolkata')

# Decorator for SMC authorization
def require_smc(f):
    """Require SMC role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.get('current_user'):
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        
        if g.current_user.role != 'smc':
            flash('Please use an SMC account to access this page.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def require_tournament_access(f):
    """Require SMC owns the tournament"""
    @wraps(f)
    def decorated_function(tournament_id, *args, **kwargs):
        tournament = Tournament.query.get_or_404(tournament_id)
        
        if tournament.created_by != g.current_user.id:
            flash('You do not have access to this tournament.', 'error')
            return redirect(url_for('smc.dashboard'))
        
        return f(tournament_id, *args, **kwargs)
    return decorated_function


@smc_bp.route('/dashboard')
@require_smc
def dashboard():
    """SMC dashboard showing all tournaments created by this SMC"""
    my_tournaments = Tournament.query.filter_by(created_by=g.current_user.id).order_by(Tournament.created_at.desc()).all()
    
    # Calculate stats across all tournaments
    total_tournaments = len(my_tournaments)
    total_teams = sum(len(t.tournament_teams) for t in my_tournaments)
    total_matches = sum(len(t.matches) for t in my_tournaments)
    
    stats = {
        'total_tournaments': total_tournaments,
        'total_teams': total_teams,
        'total_matches': total_matches
    }
    
    return render_template('smc-dashboard.html',
                         tournaments=my_tournaments,
                         stats=stats)


@smc_bp.route('/create-tournament', methods=['GET', 'POST'])
@require_smc
def create_tournament():
    """Create a new tournament"""
    if request.method == 'POST':
        try:
            name = request.form['name'].strip()
            start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
            rules = request.form.get('rules', '').strip()
            
            # Validation
            if not name:
                flash('Tournament name is required!', 'error')
                return redirect(url_for('smc.create_tournament'))
            
            if start_date > end_date:
                flash('Start date must be before end date!', 'error')
                return redirect(url_for('smc.create_tournament'))
            
            # Determine status based on dates
            today = date.today()
            if start_date > today:
                status = 'upcoming'
            elif start_date <= today <= end_date:
                status = 'active'
            else:
                status = 'completed'
            
            tournament = Tournament(
                name=name,
                start_date=start_date,
                end_date=end_date,
                status=status,
                rules=rules,
                created_by=g.current_user.id
            )
            
            db.session.add(tournament)
            db.session.commit()
            
            flash(f'Tournament "{tournament.name}" created successfully!', 'success')
            return redirect(url_for('smc.tournament_detail', tournament_id=tournament.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating tournament: {str(e)}', 'error')
    
    return render_template('smc/create-tournament.html')


@smc_bp.route('/tournament/<int:tournament_id>')
@require_smc
@require_tournament_access
def tournament_detail(tournament_id):
    """View tournament details and stats"""
    tournament = Tournament.query.get_or_404(tournament_id)
    
    stats = {
        'total_teams': len(tournament.tournament_teams),
        'active_teams': len([tt for tt in tournament.tournament_teams if tt.status == 'active']),
        'total_matches': len(tournament.matches),
        'upcoming_matches': len([m for m in tournament.matches if m.is_upcoming]),
        'completed_matches': len([m for m in tournament.matches if m.status == 'completed'])
    }
    
    # Get teams in this tournament
    tournament_teams = tournament.tournament_teams
    
    # Get upcoming matches
    upcoming_matches = [m for m in tournament.matches if m.is_upcoming]
    upcoming_matches.sort(key=lambda x: (x.date, x.time))
    
    return render_template('smc/tournament-detail.html',
                         tournament=tournament,
                         stats=stats,
                         tournament_teams=tournament_teams,
                         upcoming_matches=upcoming_matches[:5])


@smc_bp.route('/tournament/<int:tournament_id>/register-team', methods=['GET', 'POST'])
@require_smc
@require_tournament_access
def register_team(tournament_id):
    """Register a new team for this tournament"""
    tournament = Tournament.query.get_or_404(tournament_id)
    
    if request.method == 'POST':
        try:
            # Get form data
            team_name = request.form.get('team_name', '').strip()
            team_id = request.form.get('team_id', '').strip()
            department = request.form.get('department', '').strip()
            manager_name = request.form.get('manager_name', '').strip()
            manager_contact = request.form.get('manager_contact', '').strip()

            # Validation
            if not team_id:
                flash('Team ID is required!', 'error')
                return redirect(url_for('smc.register_team', tournament_id=tournament_id))
            
            if not team_name:
                flash('Team name is required!', 'error')
                return redirect(url_for('smc.register_team', tournament_id=tournament_id))

            if not department:
                flash('Department is required!', 'error')
                return redirect(url_for('smc.register_team', tournament_id=tournament_id))

            if not manager_name:
                flash('Manager name is required!', 'error')
                return redirect(url_for('smc.register_team', tournament_id=tournament_id))

            # Check if team_id already exists globally
            existing_team = Team.query.filter_by(team_id=team_id).first()
            if existing_team:
                # Team exists, check if already in this tournament
                existing_tt = TournamentTeam.query.filter_by(
                    tournament_id=tournament_id,
                    team_id=team_id
                ).first()
                
                if existing_tt:
                    flash('This team is already registered in this tournament!', 'error')
                    return redirect(url_for('smc.register_team', tournament_id=tournament_id))
                
                # Add existing team to tournament
                tt = TournamentTeam(
                    tournament_id=tournament_id,
                    team_id=team_id
                )
                db.session.add(tt)
                db.session.commit()
                
                flash(f'Existing team "{existing_team.name}" added to tournament!', 'success')
                return redirect(url_for('smc.tournament_detail', tournament_id=tournament_id))

            # Create new team
            team = Team(
                name=team_name,
                department=department,
                manager_name=manager_name,
                manager_contact=manager_contact,
                team_id=team_id,
                created_by=g.current_user.id,
                is_self_managed=False
            )

            db.session.add(team)
            db.session.flush()
            
            # Add team to tournament
            tt = TournamentTeam(
                tournament_id=tournament_id,
                team_id=team.team_id
            )
            db.session.add(tt)
            
            # Add players
            players_added = 0
            i = 1
            while True:
                name = request.form.get(f'player_{i}_name', '').strip()
                if not name:
                    break
                
                roll_number = request.form.get(f'player_{i}_roll', '')
                if roll_number:
                    player = Player(
                        name=name,
                        roll_number=int(roll_number),
                        department=request.form.get(f'player_{i}_dept', team.department),
                        year=request.form.get(f'player_{i}_year', ''),
                        contact=request.form.get(f'player_{i}_contact', ''),
                        team_id=team.team_id
                    )
                    
                    db.session.add(player)
                    players_added += 1
                
                i += 1
            
            db.session.commit()
            flash(f'Team "{team.name}" registered successfully with {players_added} players!', 'success')
            return redirect(url_for('smc.tournament_detail', tournament_id=tournament_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error registering team: {str(e)}', 'error')
    
    return render_template('register-team.html', tournament=tournament)


@smc_bp.route('/tournament/<int:tournament_id>/schedule-matches', methods=['GET', 'POST'])
@require_smc
@require_tournament_access
def schedule_matches(tournament_id):
    """Schedule matches for this tournament"""
    tournament = Tournament.query.get_or_404(tournament_id)

    if request.method == 'POST':
        try:
            team1_id = request.form['team1_id']
            team2_id = request.form['team2_id']
            
            # Verify teams are in this tournament
            tt1 = TournamentTeam.query.filter_by(tournament_id=tournament_id, team_id=team1_id).first()
            tt2 = TournamentTeam.query.filter_by(tournament_id=tournament_id, team_id=team2_id).first()
            
            if not tt1 or not tt2:
                flash('Both teams must be registered in this tournament!', 'error')
                return redirect(url_for('smc.schedule_matches', tournament_id=tournament_id))
            
            if team1_id == team2_id:
                flash('A team cannot play against itself!', 'error')
                return redirect(url_for('smc.schedule_matches', tournament_id=tournament_id))
            
            match_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            match_time = datetime.strptime(request.form['time'], '%H:%M').time()
            venue = request.form['venue']
            
            if match_date < tournament.start_date or match_date > tournament.end_date:
                flash(f'Match date must be between {tournament.start_date} and {tournament.end_date}', 'error')
                return redirect(url_for('smc.schedule_matches', tournament_id=tournament_id))
            
            # Check venue conflicts
            existing_match = Match.query.filter_by(
                tournament_id=tournament_id,
                venue=venue,
                date=match_date,
                time=match_time
            ).first()
            
            if existing_match:
                flash(f'Venue "{venue}" is already booked at {match_time} on {match_date}', 'error')
                return redirect(url_for('smc.schedule_matches', tournament_id=tournament_id))
            
            # Check team availability
            existing_team_match = Match.query.filter(
                Match.tournament_id == tournament_id,
                Match.date == match_date,
                Match.time == match_time,
                db.or_(
                    Match.team1_id == team1_id,
                    Match.team2_id == team1_id,
                    Match.team1_id == team2_id,
                    Match.team2_id == team2_id
                )
            ).first()

            if existing_team_match:
                flash('One of the teams already has a match scheduled at this time', 'error')
                return redirect(url_for('smc.schedule_matches', tournament_id=tournament_id))
            
            match = Match(
                tournament_id=tournament_id,
                team1_id=team1_id,
                team2_id=team2_id,
                date=match_date,
                time=match_time,
                venue=venue
            )
            
            db.session.add(match)
            db.session.commit()
            
            flash(f'Match scheduled: {match.versus_display} on {match.date} at {match.time}', 'success')
            return redirect(url_for('smc.schedule_matches', tournament_id=tournament_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error scheduling match: {str(e)}', 'error')
    
    # Get teams in this tournament
    tournament_teams = tournament.get_teams()
    
    # Get matches for this tournament
    all_matches = Match.query.filter_by(tournament_id=tournament_id).order_by(Match.date, Match.time).all()
    upcoming_matches = [m for m in all_matches if m.is_upcoming]
    completed_matches = [m for m in all_matches if m.status == 'completed']

    return render_template('schedule-matches.html',
                           tournament=tournament,
                           teams=tournament_teams,
                           upcoming_matches=upcoming_matches,
                           completed_matches=completed_matches)


@smc_bp.route('/tournament/<int:tournament_id>/add-results', methods=['GET', 'POST'])
@require_smc
@require_tournament_access
def add_results(tournament_id):
    """Add results for matches in this tournament"""
    tournament = Tournament.query.get_or_404(tournament_id)
    
    if request.method == 'POST':
        try:
            match_id = int(request.form['match_id'])
            match = Match.query.get_or_404(match_id)
            
            # Verify match belongs to this tournament
            if match.tournament_id != tournament_id:
                flash('Match does not belong to this tournament!', 'error')
                return redirect(url_for('smc.add_results', tournament_id=tournament_id))
            
            if match.status == 'completed':
                flash('Results have already been entered for this match!', 'error')
                return redirect(url_for('smc.add_results', tournament_id=tournament_id))

            if match.date > date.today():
                flash('Cannot enter results for future matches!', 'error')
                return redirect(url_for('smc.add_results', tournament_id=tournament_id))
            
            # Update match with results
            match.team1_score = request.form['team1_score'].strip()
            match.team2_score = request.form['team2_score'].strip()
            match.status = 'completed'
            
            # Set winner if provided
            winner_id = request.form.get('winner_id')
            if winner_id and winner_id != '':
                if winner_id not in [match.team1_id, match.team2_id]:
                    flash('Winner must be one of the participating teams!', 'error')
                    return redirect(url_for('smc.add_results', tournament_id=tournament_id))
                match.winner_id = winner_id
            else:
                match.winner_id = None
            
            db.session.commit()
            
            flash(f'Results updated for match: {match.team1.name} vs {match.team2.name}', 'success')
            return redirect(url_for('smc.add_results', tournament_id=tournament_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating results: {str(e)}', 'error')
    
    # Get matches that can have results added
    today = date.today()
    pending_matches = Match.query.filter(
        Match.tournament_id == tournament_id,
        Match.status == 'scheduled',
        Match.date <= today
    ).order_by(Match.date, Match.time).all()
    
    # Get completed matches
    completed_matches = Match.query.filter(
        Match.tournament_id == tournament_id,
        Match.status == 'completed'
    ).order_by(Match.date.desc(), Match.time.desc()).limit(10).all()

    # Get teams for winner dropdown
    teams = tournament.get_teams()

    return render_template('add-results.html',
                         tournament=tournament,
                         pending_matches=pending_matches,
                         completed_matches=completed_matches,
                         teams=teams)