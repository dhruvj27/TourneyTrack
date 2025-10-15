from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from datetime import datetime, date
from functools import wraps
import pytz

from models import (
    db,
    User,
    Tournament,
    Team,
    Player,
    Match,
    TournamentTeam,
    Notification,
    get_default_tournament,
)
from blueprints.auth import require_smc

smc_bp = Blueprint('smc', __name__, url_prefix='/smc')
IST = pytz.timezone('Asia/Kolkata')


def _generate_team_id() -> str:
    """Generate next available team identifier in TM0001 format."""
    last_team = Team.query.order_by(Team.id.desc()).first()
    if last_team and last_team.team_id and last_team.team_id.startswith('TM'):
        try:
            next_num = int(last_team.team_id[2:]) + 1
        except ValueError:
            next_num = Team.query.count() + 1
    else:
        next_num = 1
    return f"TM{next_num:04d}"


def _smc_can_access_team(team: Team) -> bool:
    if team.created_by == g.current_user.id:
        return True
    return any(
        assoc.tournament and assoc.tournament.created_by == g.current_user.id
        for assoc in team.tournament_teams
    )

def require_tournament_access(f):
    """Require SMC owns the tournament"""
    @wraps(f)
    def decorated_function(tournament_id, *args, **kwargs):
        tournament = Tournament.query.get_or_404(tournament_id)
        default_tournament = get_default_tournament()
        allowed_default = default_tournament and default_tournament.id == tournament.id

        if tournament.created_by != g.current_user.id and not allowed_default:
            flash('You do not have access to this tournament.', 'error')
            return redirect(url_for('smc.dashboard'))
        g.tournament_context = tournament
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
    
    pending_summary = []
    total_pending_requests = 0
    total_pending_invites = 0

    for tournament in my_tournaments:
        requests = [
            assoc
            for assoc in tournament.tournament_teams
            if assoc.status == 'pending' and assoc.registration_method != 'smc_invited'
        ]
        invites = [
            assoc
            for assoc in tournament.tournament_teams
            if assoc.status == 'pending' and assoc.registration_method == 'smc_invited'
        ]

        if requests or invites:
            pending_summary.append(
                {
                    'tournament': tournament,
                    'requests': requests,
                    'invites': invites,
                }
            )

        total_pending_requests += len(requests)
        total_pending_invites += len(invites)

    stats = {
        'total_tournaments': total_tournaments,
        'total_teams': total_teams,
        'total_matches': total_matches,
        'pending_requests': total_pending_requests,
        'pending_invites': total_pending_invites,
    }
    
    tournament_ids = [t.id for t in my_tournaments]
    live_matches = []
    upcoming_matches = []
    recent_results = []

    if tournament_ids:
        live_matches = (
            Match.query.options(joinedload(Match.team1), joinedload(Match.team2))
            .filter(Match.tournament_id.in_(tournament_ids), Match.status == 'active')
            .order_by(Match.date.desc(), Match.time.desc())
            .limit(3)
            .all()
        )

        today = date.today()
        upcoming_matches = (
            Match.query.options(joinedload(Match.team1), joinedload(Match.team2))
            .filter(
                Match.tournament_id.in_(tournament_ids),
                Match.status == 'scheduled',
                Match.date >= today,
            )
            .order_by(Match.date.asc(), Match.time.asc())
            .limit(5)
            .all()
        )

        recent_results = (
            Match.query.options(joinedload(Match.team1), joinedload(Match.team2))
            .filter(Match.tournament_id.in_(tournament_ids), Match.status == 'completed')
            .order_by(Match.date.desc(), Match.time.desc())
            .limit(5)
            .all()
        )

    notifications_preview = Notification.active_for_user(g.current_user.id).limit(6).all()
    unread_count = Notification.query.filter_by(user_id=g.current_user.id, is_read=False).count()

    return render_template(
        'smc/dashboard.html',
        tournaments=my_tournaments,
        stats=stats,
        notifications_preview=notifications_preview,
        unread_notification_count=unread_count,
        live_matches=live_matches,
        upcoming_matches=upcoming_matches,
        recent_results=recent_results,
        pending_summary=pending_summary,
    )


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


@smc_bp.route('/notifications')
@require_smc
def notifications():
    """Dedicated notification center for SMC users."""
    status_filter = request.args.get('status', 'active')
    query = Notification.query.filter_by(user_id=g.current_user.id)

    if status_filter == 'archived':
        query = query.filter(Notification.status == 'archived')
    elif status_filter == 'resolved':
        query = query.filter(Notification.status == 'resolved')
    elif status_filter == 'all':
        pass
    else:
        query = query.filter(Notification.status.in_(['pending', 'active']))

    notifications_list = query.order_by(Notification.created_at.desc()).all()
    return render_template(
        'smc/notifications.html',
        notifications=notifications_list,
        status_filter=status_filter,
    )


@smc_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@require_smc
def mark_notification_read(notification_id):
    """Mark an SMC notification as read or resolved."""
    note = Notification.query.filter_by(id=notification_id, user_id=g.current_user.id).first_or_404()
    note.is_read = True
    if request.form.get('resolve') == '1':
        note.resolve()
    db.session.commit()
    flash('Notification updated.', 'success')
    return redirect(url_for('smc.notifications', status=request.args.get('status', 'active')))


@smc_bp.route('/tournament/<int:tournament_id>')
@require_smc
@require_tournament_access
def tournament_detail(tournament_id):
    """View tournament details and stats"""
    tournament = Tournament.query.get_or_404(tournament_id)
    
    unread_count = Notification.query.filter_by(user_id=g.current_user.id, is_read=False).count()

    stats = {
        'total_teams': len(tournament.tournament_teams),
        'active_teams': len([tt for tt in tournament.tournament_teams if tt.status == 'active']),
        'total_matches': len(tournament.matches),
        'upcoming_matches': len([m for m in tournament.matches if m.is_upcoming]),
        'completed_matches': len([m for m in tournament.matches if m.status == 'completed'])
    }
    
    # Get teams in this tournament
    confirmed_associations = [
        assoc
        for assoc in tournament.tournament_teams
        if assoc.status in {'active', 'champion', 'eliminated'}
    ]
    smc_managed_teams = [
        assoc
        for assoc in confirmed_associations
        if assoc.team and not assoc.team.is_self_managed
    ]
    self_managed_teams = [
        assoc
        for assoc in confirmed_associations
        if assoc.team and assoc.team.is_self_managed
    ]
    invited_teams = [
        assoc
        for assoc in tournament.tournament_teams
        if assoc.status == 'pending' and assoc.registration_method == 'smc_invited'
    ]
    pending_requests = [
        assoc
        for assoc in tournament.tournament_teams
        if assoc.status == 'pending' and assoc.registration_method != 'smc_invited'
    ]
    
    # Get upcoming matches
    upcoming_matches = [m for m in tournament.matches if m.is_upcoming]
    upcoming_matches.sort(key=lambda x: (x.date, x.time))

    completed_matches = [m for m in tournament.matches if m.status == 'completed']
    completed_matches.sort(key=lambda x: (x.date, x.time), reverse=True)
    
    return render_template(
        'smc/tournament-detail.html',
        tournament=tournament,
        stats=stats,
        tournament_teams=confirmed_associations,
        smc_managed_teams=smc_managed_teams,
        self_managed_teams=self_managed_teams,
        upcoming_matches=upcoming_matches[:5],
        completed_matches=completed_matches[:10],
        invited_teams=invited_teams,
        pending_requests=pending_requests,
        unread_notification_count=unread_count,
    )


@smc_bp.route('/tournament/<int:tournament_id>/pending-teams')
@require_smc
@require_tournament_access
def pending_teams(tournament_id):
    """List pending team join requests for a tournament."""
    tournament = g.get('tournament_context') or Tournament.query.get_or_404(tournament_id)
    unread_count = Notification.query.filter_by(user_id=g.current_user.id, is_read=False).count()
    pending = (
        TournamentTeam.query.options(joinedload(TournamentTeam.team))
        .filter_by(tournament_id=tournament_id, status='pending')
        .filter(TournamentTeam.registration_method != 'smc_invited')
        .order_by(TournamentTeam.requested_at.asc())
        .all()
    )
    return render_template(
        'smc/pending-teams.html',
        tournament=tournament,
        pending_teams=pending,
        unread_notification_count=unread_count,
    )


@smc_bp.route('/tournament/<int:tournament_id>/register-team', methods=['GET', 'POST'])
@require_smc
@require_tournament_access
def register_team(tournament_id):
    """Register a new team for this tournament"""
    tournament = Tournament.query.get_or_404(tournament_id)
    unread_count = Notification.query.filter_by(user_id=g.current_user.id, is_read=False).count()
    
    if request.method == 'POST':
        try:
            mode = request.form.get('action', 'create')

            if mode == 'invite_existing':
                existing_team_id = request.form.get('existing_team_id', '').strip()
                team = Team.query.filter_by(team_id=existing_team_id).first()
                if not team:
                    flash('Selected team was not found.', 'error')
                    return redirect(url_for('smc.register_team', tournament_id=tournament_id))

                if TournamentTeam.query.filter_by(tournament_id=tournament_id, team_id=team.team_id).first():
                    flash('Team is already linked to this tournament.', 'error')
                    return redirect(url_for('smc.register_team', tournament_id=tournament_id))

                if (
                    tournament.institution is not None
                    and team.institution is not None
                    and team.institution != tournament.institution
                ):
                    flash('Team belongs to a different institution.', 'error')
                    return redirect(url_for('smc.register_team', tournament_id=tournament_id))

                assoc = tournament.add_team(team, added_by=g.current_user, method='smc_invited', auto_commit=True)

                if team.manager:
                    context_ref = f"{tournament.id}:{team.team_id}"
                    team.manager.notify(
                        f'Your team "{team.name}" was invited to join {tournament.name}.',
                        category='info',
                        kind='tournament_invite',
                        status='pending',
                        link_target=url_for('team.browse_tournaments'),
                        context_type='tournament',
                        context_ref=context_ref,
                        actor_id=getattr(g.current_user, 'id', None),
                        commit=True,
                    )
                flash('Invitation sent to team manager.', 'success')
                return redirect(url_for('smc.pending_teams', tournament_id=tournament_id))

            # Create or update team directly under SMC
            team_name = request.form.get('team_name', '').strip()
            department = request.form.get('department', '').strip()
            team_institution = request.form.get('team_institution', '').strip()

            if not team_name or not department:
                flash('Team name and department are required.', 'error')
                return redirect(url_for('smc.register_team', tournament_id=tournament_id))

            generated_team_id = _generate_team_id()
            while Team.query.filter_by(team_id=generated_team_id).first():
                generated_team_id = _generate_team_id()

            if not team_institution:
                team_institution = tournament.institution or g.current_user.institution

            team = Team(
                name=team_name,
                department=department,
                team_id=generated_team_id,
                created_by=g.current_user.id,
                managed_by=g.current_user.id,
                manager_name='Unassigned',
                institution=team_institution,
            )

            db.session.add(team)
            db.session.flush()

            assoc = tournament.add_team(team, added_by=g.current_user, method='smc_added')

            db.session.commit()

            flash(f'Team "{team.name}" registered successfully. Team ID: {team.team_id}', 'success')
            return redirect(url_for('smc.tournament_detail', tournament_id=tournament_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error registering team: {str(e)}', 'error')
    
    candidate_query = Team.query.filter_by(is_active=True)
    if tournament.institution:
        candidate_query = candidate_query.filter(or_(Team.institution == tournament.institution, Team.institution.is_(None)))
    existing_team_ids = [tt.team_id for tt in tournament.tournament_teams]
    if existing_team_ids:
        candidate_query = candidate_query.filter(Team.team_id.notin_(existing_team_ids))
    candidate_teams = candidate_query.order_by(Team.name).all()

    return render_template(
        'smc/register-team.html',
        tournament=tournament,
        candidate_teams=candidate_teams,
        unread_notification_count=unread_count,
    )

@smc_bp.route('/tournament/<int:tournament_id>/approve-team/<team_id>', methods=['POST'])
@require_smc
def approve_team(tournament_id, team_id):
    """Approve team join request"""
    tournament = Tournament.query.get_or_404(tournament_id)
    
    # Authorization check
    if tournament.created_by != g.current_user.id:
        flash('You do not have permission to manage this tournament.', 'error')
        return redirect(url_for('smc.dashboard'))
    
    try:
        tt = TournamentTeam.query.options(joinedload(TournamentTeam.team)).filter_by(
            tournament_id=tournament_id,
            team_id=team_id
        ).first_or_404()
        
        action = request.form.get('action')
        team = tt.team
        manager_user = getattr(team, 'manager', None)
        context_ref = f"{tournament.id}:{team.team_id}"
        smc_notes = Notification.query.filter(
            Notification.user_id == g.current_user.id,
            Notification.context_type == 'tournament',
            Notification.kind == 'tournament_request',
            Notification.status == 'pending',
            Notification.context_ref.in_([context_ref, str(tournament.id)]),
        ).all()

        if action == 'approve':
            tt.set_status('active', actor=g.current_user)
            for note in smc_notes:
                note.message = f'Approved: {team.name} will compete in {tournament.name}.'
                note.resolve()
            db.session.commit()
            if manager_user:
                manager_user.notify(
                    f'Your team "{team.name}" was approved for {tournament.name}.',
                    category='success',
                    kind='tournament_request',
                    status='active',
                    link_target=url_for('team.team_detail', team_id=team.team_id),
                    context_type='tournament',
                    context_ref=context_ref,
                    actor_id=getattr(g.current_user, 'id', None),
                    commit=True,
                )
            flash('Team approved successfully.', 'success')
        elif action == 'reject':
            for note in smc_notes:
                note.message = f'Rejected: {team.name} will not participate in {tournament.name}.'
                note.resolve()
            db.session.delete(tt)
            db.session.commit()
            if manager_user:
                manager_user.notify(
                    f'Your team "{team.name}" invitation to {tournament.name} was declined.',
                    category='warning',
                    kind='tournament_request',
                    status='active',
                    context_type='tournament',
                    context_ref=context_ref,
                    actor_id=getattr(g.current_user, 'id', None),
                    commit=True,
                )
            flash('Team request rejected.', 'info')

        return redirect(url_for('smc.pending_teams', tournament_id=tournament_id))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing request: {str(e)}', 'error')
        return redirect(url_for('smc.pending_teams', tournament_id=tournament_id))

@smc_bp.route('/tournament/<int:tournament_id>/schedule-matches', methods=['GET', 'POST'])
@require_smc
@require_tournament_access
def schedule_matches(tournament_id):
    """Schedule matches for this tournament"""
    tournament = Tournament.query.get_or_404(tournament_id)
    unread_count = Notification.query.filter_by(user_id=g.current_user.id, is_read=False).count()

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
                or_(
                    Match.team1_id == team1_id,
                    Match.team2_id == team1_id,
                    Match.team1_id == team2_id,
                    Match.team2_id == team2_id,
                ),
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

    return render_template('smc/schedule-matches.html',
                           tournament=tournament,
                           teams=tournament_teams,
                           upcoming_matches=upcoming_matches,
                           completed_matches=completed_matches,
                           unread_notification_count=unread_count)


@smc_bp.route('/tournament/<int:tournament_id>/add-results', methods=['GET', 'POST'])
@require_smc
@require_tournament_access
def add_results(tournament_id):
    """Add results for matches in this tournament"""
    tournament = Tournament.query.get_or_404(tournament_id)
    unread_count = Notification.query.filter_by(user_id=g.current_user.id, is_read=False).count()
    
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

    return render_template('smc/add-results.html',
                         tournament=tournament,
                         pending_matches=pending_matches,
                         completed_matches=completed_matches,
                         teams=teams,
                         unread_notification_count=unread_count)


@smc_bp.route('/team/<team_id>/view')
@require_smc
def view_team(team_id):
    """Read-only view for teams managed within SMC tournaments."""
    team = Team.query.options(
        joinedload(Team.players),
        joinedload(Team.tournament_teams).joinedload(TournamentTeam.tournament),
    ).filter_by(team_id=team_id).first_or_404()

    if not _smc_can_access_team(team):
        abort(403)

    active_players = [player for player in team.players if player.is_active]
    tournaments = team.get_tournaments()
    upcoming_matches = team.get_upcoming_matches()
    completed_matches = team.get_completed_matches()

    return render_template(
        'smc/team-view.html',
        team=team,
        active_players=active_players,
        tournaments=tournaments,
        upcoming_matches=upcoming_matches,
        completed_matches=completed_matches,
    )


@smc_bp.route('/team/<team_id>/edit', methods=['GET', 'POST'])
@require_smc
def edit_team_as_smc(team_id):
    """Allow SMCs to edit teams they are responsible for."""
    team = Team.query.options(joinedload(Team.players)).filter_by(team_id=team_id).first_or_404()

    if team.managed_by != g.current_user.id:
        flash('You do not manage this team.', 'error')
        return redirect(url_for('smc.view_team', team_id=team_id))

    if request.method == 'POST':
        try:
            team.manager_name = request.form.get('manager_name', team.manager_name).strip()
            team.manager_contact = request.form.get('manager_contact', team.manager_contact).strip()
            team.department = request.form.get('department', team.department).strip()
            db.session.commit()
            flash('Team details updated.', 'success')
        except Exception as exc:
            db.session.rollback()
            flash(f'Error updating team: {exc}', 'error')
        return redirect(url_for('smc.view_team', team_id=team_id))

    active_players = [player for player in team.players if player.is_active]
    return render_template('smc/team-edit.html', team=team, players=active_players)


@smc_bp.route('/team/<team_id>/assign-manager', methods=['POST'])
@require_smc
def assign_manager(team_id):
    """Assign a team manager to a team created by the SMC."""
    team = Team.query.filter_by(team_id=team_id).first_or_404()

    if not _smc_can_access_team(team):
        abort(403)

    username = request.form.get('manager_username', '').strip()
    manager = User.query.filter_by(username=username, role='team_manager').first()
    if not manager:
        flash('Team manager account not found.', 'error')
        return redirect(url_for('smc.view_team', team_id=team_id))

    team.assign_manager(manager, actor_id=getattr(g.current_user, 'id', None))
    db.session.commit()

    flash('Team manager assigned.', 'success')
    return redirect(url_for('smc.view_team', team_id=team_id))