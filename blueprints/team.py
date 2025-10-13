from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from models import db, User, Tournament, Team, Player, Match, TournamentTeam
from blueprints.auth import login_required
from functools import wraps
from datetime import datetime, date
import pytz

team_bp = Blueprint('team', __name__, url_prefix='/team')
IST = pytz.timezone('Asia/Kolkata')

def require_team_manager(f):
    """Require team manager role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.current_user:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        
        if g.current_user.role != 'team_manager':
            flash('Please use a Team Manager account to access this page.', 'error')
            return redirect(url_for('auth.login'))
        
        return f(*args, **kwargs)
    return decorated_function


def generate_team_id():
    """Generate next available team ID in format TM0001, TM0002, etc."""
    last_team = Team.query.order_by(Team.id.desc()).first()
    if last_team and last_team.team_id.startswith('TM'):
        try:
            last_num = int(last_team.team_id[2:])
            next_num = last_num + 1
        except ValueError:
            next_num = 1
    else:
        next_num = 1
    
    return f"TM{next_num:04d}"


@team_bp.route('/create-team', methods=['GET', 'POST'])
@require_team_manager
def create_team():
    """Team manager creates a new team"""
    if request.method == 'POST':
        try:
            team_name = request.form.get('team_name', '').strip()
            department = request.form.get('department', '').strip()
            manager_name = request.form.get('manager_name', '').strip()
            manager_contact = request.form.get('manager_contact', '').strip()

            # Validation
            if not team_name:
                flash('Team name is required!', 'error')
                return redirect(url_for('team.create_team'))

            if not department:
                flash('Department is required!', 'error')
                return redirect(url_for('team.create_team'))

            if not manager_name:
                flash('Manager name is required!', 'error')
                return redirect(url_for('team.create_team'))

            # Generate team ID
            team_id = generate_team_id()

            # Create team
            team = Team(
                name=team_name,
                department=department,
                manager_name=manager_name,
                manager_contact=manager_contact,
                team_id=team_id,
                created_by=g.current_user.id,
                is_self_managed=True
            )

            db.session.add(team)
            db.session.flush()

            # Add players if provided
            players_added = 0
            i = 1
            while True:
                name = request.form.get(f'player_{i}_name', '').strip()
                if name:
                    roll_number = request.form.get(f'player_{i}_roll', '').strip()
                    if not roll_number:
                        flash(f'Roll number required for player {i}', 'error')
                        db.session.rollback()
                        return redirect(url_for('team.create_team'))
                    
                    player = Player(
                        name=name,
                        roll_number=int(roll_number),
                        department=request.form.get(f'player_{i}_dept', department),
                        year=request.form.get(f'player_{i}_year', ''),
                        contact=request.form.get(f'player_{i}_contact', ''),
                        team_id=team.team_id
                    )
                    db.session.add(player)
                    players_added += 1
                    i += 1
                else:
                    break

            db.session.commit()
            flash(f'Team "{team.name}" created successfully! Team ID: {team.team_id}', 'success')
            return redirect(url_for('team.my_teams'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating team: {str(e)}', 'error')

    return render_template('team/create-team.html')


@team_bp.route('/my-teams')
@require_team_manager
def my_teams():
    """Display all teams created by this manager"""
    teams = Team.query.filter_by(
        created_by=g.current_user.id,
        is_active=True
    ).all()
    
    # Get tournament count for each team
    team_data = []
    for team in teams:
        tournament_count = TournamentTeam.query.filter_by(team_id=team.team_id).count()
        player_count = Player.query.filter_by(team_id=team.team_id, is_active=True).count()
        team_data.append({
            'team': team,
            'tournament_count': tournament_count,
            'player_count': player_count
        })
    
    return render_template('team/my-teams.html', team_data=team_data)


@team_bp.route('/dashboard/<team_id>')
@require_team_manager
def dashboard(team_id):
    """Team dashboard for specific team"""
    team = Team.query.filter_by(team_id=team_id).first_or_404()
    
    # Authorization: Only creator can access
    if team.created_by != g.current_user.id:
        flash('You do not have permission to access this team.', 'error')
        return redirect(url_for('team.my_teams'))
    
    # Get tournaments this team is part of
    tournament_teams = TournamentTeam.query.filter_by(team_id=team.team_id).all()
    tournaments = [tt.tournament for tt in tournament_teams]
    
    # Get upcoming and completed matches across all tournaments
    upcoming_matches = team.get_upcoming_matches()
    completed_matches = team.get_completed_matches()
    record = team.get_match_record()
    
    # Get active players
    active_players = [p for p in team.players if p.is_active]
    
    return render_template('team/team-dashboard.html',
                         team=team,
                         tournaments=tournaments,
                         players=active_players,
                         upcoming_matches=upcoming_matches,
                         completed_matches=completed_matches,
                         record=record)


@team_bp.route('/browse-tournaments')
@require_team_manager
def browse_tournaments():
    """Browse all available tournaments"""
    tournaments = Tournament.query.order_by(Tournament.start_date.desc()).all()
    
    # Get user's teams
    user_teams = Team.query.filter_by(
        created_by=g.current_user.id,
        is_active=True
    ).all()
    
    # Create mapping of which teams are in which tournaments
    tournament_data = []
    for tournament in tournaments:
        joined_teams = []
        pending_teams = []
        
        for team in user_teams:
            tt = TournamentTeam.query.filter_by(
                tournament_id=tournament.id,
                team_id=team.team_id
            ).first()
            
            if tt:
                if tt.status == 'pending':
                    pending_teams.append(team)
                else:
                    joined_teams.append(team)
        
        tournament_data.append({
            'tournament': tournament,
            'joined_teams': joined_teams,
            'pending_teams': pending_teams
        })
    
    return render_template('team/browse-tournaments.html',
                         tournament_data=tournament_data,
                         user_teams=user_teams)


@team_bp.route('/join-tournament', methods=['POST'])
@require_team_manager
def join_tournament():
    """Request to join a tournament"""
    try:
        tournament_id = int(request.form['tournament_id'])
        team_id = request.form['team_id']
        
        tournament = Tournament.query.get_or_404(tournament_id)
        team = Team.query.filter_by(team_id=team_id).first_or_404()
        
        # Authorization: Only creator can join
        if team.created_by != g.current_user.id:
            flash('You do not have permission to join tournaments with this team.', 'error')
            return redirect(url_for('team.browse_tournaments'))
        
        # Check if already joined or pending
        existing = TournamentTeam.query.filter_by(
            tournament_id=tournament_id,
            team_id=team_id
        ).first()
        
        if existing:
            flash(f'Team "{team.name}" has already requested to join this tournament.', 'info')
            return redirect(url_for('team.browse_tournaments'))
        
        # Create join request with pending status
        tt = TournamentTeam(
            tournament_id=tournament_id,
            team_id=team_id,
            status='pending'
        )
        db.session.add(tt)
        db.session.commit()
        
        flash(f'Join request sent for team "{team.name}" to tournament "{tournament.name}". Waiting for SMC approval.', 'success')
        return redirect(url_for('team.browse_tournaments'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error joining tournament: {str(e)}', 'error')
        return redirect(url_for('team.browse_tournaments'))


@team_bp.route('/update-profile/<team_id>', methods=['GET', 'POST'])
@require_team_manager
def update_profile(team_id):
    """Update team and player profiles"""
    team = Team.query.filter_by(team_id=team_id).first_or_404()
    
    # Authorization: Only creator can edit
    if team.created_by != g.current_user.id:
        flash('You do not have permission to edit this team.', 'error')
        return redirect(url_for('team.my_teams'))
    
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
                    roll_number=int(request.form['new_player_roll']),
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
            
            return redirect(url_for('team.update_profile', team_id=team_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')
    
    active_players = [p for p in team.players if p.is_active]
    
    return render_template('team/update-profile.html', team=team, players=active_players)