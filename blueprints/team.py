from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from models import (
    db,
    Tournament,
    Team,
    Player,
    TournamentTeam,
    Notification,
    current_time,
)
from blueprints.auth import require_team_manager
from functools import wraps
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

team_bp = Blueprint('team', __name__, url_prefix='/team')


def require_team_ownership(f):
    """Require the current user to manage the target team."""

    @wraps(f)
    def decorated_function(team_id, *args, **kwargs):
        if not getattr(g, 'current_user', None):
            flash('Please log in to continue.', 'error')
            return redirect(url_for('auth.login'))

        team = Team.query.filter_by(team_id=team_id, is_active=True).first_or_404()

        if g.current_user.id != team.managed_by:
            flash('You do not have permission to access this team.', 'error')
            return redirect(url_for('team.dashboard_overview'))

        g.team_context = team
        return f(team_id, *args, **kwargs)

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

@team_bp.route('/dashboard')
@require_team_manager
def dashboard_overview():
    """Overview dashboard showing all teams managed by the user."""
    managed_teams = (
        Team.query.options(joinedload(Team.players), joinedload(Team.tournament_teams))
        .filter_by(managed_by=g.current_user.id, is_active=True)
        .order_by(Team.created_at.desc())
        .all()
    )

    teams_view = []
    total_players = 0
    total_active_tournaments = 0

    for team in managed_teams:
        active_players = [player for player in team.players if player.is_active]
        total_players += len(active_players)
        total_active_tournaments += len([assoc for assoc in team.tournament_teams if assoc.status == 'active'])
        upcoming_matches = team.get_upcoming_matches()
        completed_matches = team.get_completed_matches()
        teams_view.append(
            {
                'team': team,
                'player_count': len(active_players),
                'tournament_count': len(team.tournament_teams),
                'upcoming_matches': upcoming_matches[:3],
                'recent_result': completed_matches[0] if completed_matches else None,
            }
        )

    pending_invites = (
        TournamentTeam.query.join(Team, TournamentTeam.team_id == Team.team_id)
        .filter(
            Team.managed_by == g.current_user.id,
            TournamentTeam.status == 'pending',
            TournamentTeam.registration_method == 'smc_invited',
        )
        .count()
    )

    stats = {
        'total_teams': len(managed_teams),
        'total_players': total_players,
        'active_tournaments': total_active_tournaments,
        'pending_invites': pending_invites,
    }

    notifications_preview = Notification.active_for_user(g.current_user.id).limit(6).all()
    unread_notification_count = Notification.query.filter_by(user_id=g.current_user.id, is_read=False).count()

    return render_template(
        'team/dashboard.html',
        teams=teams_view,
        stats=stats,
        notifications_preview=notifications_preview,
        unread_notification_count=unread_notification_count,
    )


@team_bp.route('/notifications')
@require_team_manager
def notifications():
    """Notification center for team managers."""
    status_filter = request.args.get('status', 'active')
    query = Notification.query.filter_by(user_id=g.current_user.id)

    if status_filter == 'archived':
        query = query.filter(Notification.status == 'archived')
    elif status_filter == 'all':
        pass
    else:
        query = query.filter(Notification.status.in_(['pending', 'active']))

    notifications_list = query.order_by(Notification.created_at.desc()).all()
    return render_template(
        'team/notifications.html',
        notifications=notifications_list,
        status_filter=status_filter,
    )


@team_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@require_team_manager
def mark_notification_read(notification_id):
    """Mark a team manager notification as read or resolved."""
    note = Notification.query.filter_by(id=notification_id, user_id=g.current_user.id).first_or_404()
    note.is_read = True
    if request.form.get('resolve') == '1':
        note.resolve()
    db.session.commit()
    flash('Notification updated.', 'success')
    return redirect(url_for('team.notifications', status=request.args.get('status', 'active')))


@team_bp.route('/create-team', methods=['GET', 'POST'])
@require_team_manager
def create_team():
    """Team manager creates a new team."""
    if request.method == 'POST':
        try:
            team_name = request.form.get('team_name', '').strip()
            department = request.form.get('department', '').strip()
            manager_name = request.form.get('manager_name', '').strip()
            manager_contact = request.form.get('manager_contact', '').strip()

            if not team_name:
                flash('Team name is required.', 'error')
                return redirect(url_for('team.create_team'))

            if not department:
                flash('Department is required.', 'error')
                return redirect(url_for('team.create_team'))

            if not manager_name:
                flash('Manager name is required.', 'error')
                return redirect(url_for('team.create_team'))

            team_id = generate_team_id()
            team = Team(
                name=team_name,
                department=department,
                manager_name=manager_name,
                manager_contact=manager_contact,
                team_id=team_id,
                created_by=g.current_user.id,
                managed_by=g.current_user.id,
                institution=g.current_user.institution,
            )

            db.session.add(team)
            db.session.flush()

            index = 1
            while True:
                name = request.form.get(f'player_{index}_name', '').strip()
                if not name:
                    break

                roll_number = request.form.get(f'player_{index}_roll', '').strip()
                if not roll_number:
                    flash(f'Roll number required for player {index}.', 'error')
                    db.session.rollback()
                    return redirect(url_for('team.create_team'))

                try:
                    roll_number_int = int(roll_number)
                except ValueError:
                    flash(f'Roll number must be numeric for player {index}.', 'error')
                    db.session.rollback()
                    return redirect(url_for('team.create_team'))

                player = Player(
                    name=name,
                    roll_number=roll_number_int,
                    department=request.form.get(f'player_{index}_dept', department),
                    year=request.form.get(f'player_{index}_year', ''),
                    contact=request.form.get(f'player_{index}_contact', ''),
                    team_id=team.team_id,
                )
                db.session.add(player)
                index += 1

            db.session.commit()
            flash(f'Team "{team.name}" created successfully! Team ID: {team.team_id}', 'success')
            return redirect(url_for('team.dashboard_overview'))
        except Exception as exc:
            db.session.rollback()
            flash(f'Error creating team: {exc}', 'error')

    return render_template('team/create-team.html')


@team_bp.route('/my-teams')
@require_team_manager
def my_teams():
    """Display all teams managed by this user."""
    teams = (
        Team.query.filter_by(managed_by=g.current_user.id, is_active=True)
        .order_by(Team.created_at.desc())
        .all()
    )

    team_data = []
    for team in teams:
        tournament_count = TournamentTeam.query.filter_by(team_id=team.team_id).count()
        player_count = Player.query.filter_by(team_id=team.team_id, is_active=True).count()
        team_data.append(
            {
                'team': team,
                'tournament_count': tournament_count,
                'player_count': player_count,
            }
        )

    return render_template('team/my-teams.html', team_data=team_data)


@team_bp.route('/team/<team_id>')
@require_team_manager
@require_team_ownership
def team_detail(team_id):
    """Detailed dashboard for a single team."""
    team = getattr(g, 'team_context', None)
    if not team:
        team = (
            Team.query.options(joinedload(Team.players), joinedload(Team.tournament_teams))
            .filter_by(team_id=team_id)
            .first_or_404()
        )

    active_players = [player for player in team.players if player.is_active]
    tournaments = [assoc.tournament for assoc in team.tournament_teams if assoc.tournament]
    upcoming_matches = team.get_upcoming_matches()
    completed_matches = team.get_completed_matches()
    record = team.get_match_record()

    pending_invites = [
        assoc
        for assoc in team.tournament_teams
        if assoc.status == 'pending' and assoc.registration_method == 'smc_invited'
    ]
    pending_requests = [
        assoc
        for assoc in team.tournament_teams
        if assoc.status == 'pending' and assoc.registration_method != 'smc_invited'
    ]

    return render_template(
        'team/team-dashboard.html',
        team=team,
        tournaments=tournaments,
        players=active_players,
        upcoming_matches=upcoming_matches,
        completed_matches=completed_matches,
        record=record,
        pending_invites=pending_invites,
        pending_requests=pending_requests,
    )


team_bp.add_url_rule('/dashboard/<team_id>', view_func=team_detail, endpoint='dashboard')


@team_bp.route('/browse-tournaments')
@require_team_manager
def browse_tournaments():
    """Browse tournaments a team manager can join."""
    tournament_query = Tournament.query.order_by(Tournament.start_date.desc())
    if g.current_user.institution is not None:
        tournament_query = tournament_query.filter(
            or_(
                Tournament.institution == g.current_user.institution,
                Tournament.institution.is_(None),
            )
        )
    tournaments = tournament_query.all()

    user_teams = (
        Team.query.filter_by(managed_by=g.current_user.id, is_active=True)
        .order_by(Team.name.asc())
        .all()
    )

    team_ids = [team.team_id for team in user_teams]
    tournament_ids = [tournament.id for tournament in tournaments]

    assoc_lookup = {}
    if team_ids and tournament_ids:
        associations = TournamentTeam.query.filter(
            TournamentTeam.team_id.in_(team_ids),
            TournamentTeam.tournament_id.in_(tournament_ids),
        ).all()
        assoc_lookup = {(assoc.tournament_id, assoc.team_id): assoc for assoc in associations}

    tournament_data = []
    for tournament in tournaments:
        joined_entries = []
        pending_entries = []
        invited_entries = []

        for team in user_teams:
            assoc = assoc_lookup.get((tournament.id, team.team_id))
            if not assoc:
                continue

            if assoc.status == 'active':
                joined_entries.append({'team': team, 'association': assoc})
            elif assoc.status == 'pending':
                if assoc.registration_method == 'smc_invited':
                    invited_entries.append({'team': team, 'association': assoc})
                else:
                    pending_entries.append({'team': team, 'association': assoc})

        associated_team_ids = {
            entry['team'].team_id for entry in joined_entries + pending_entries + invited_entries
        }

        tournament_data.append(
            {
                'tournament': tournament,
                'joined_teams': [entry['team'] for entry in joined_entries],
                'pending_teams': [entry['team'] for entry in pending_entries],
                'invited_entries': [
                    {'team': entry['team'], 'assoc_id': entry['association'].id}
                    for entry in invited_entries
                ],
                'associated_team_ids': associated_team_ids,
            }
        )

    return render_template(
        'team/browse-tournaments.html',
        tournament_data=tournament_data,
        user_teams=user_teams,
    )


@team_bp.route('/join-tournament', methods=['POST'])
@require_team_manager
def join_tournament():
    """Request to join a tournament."""
    try:
        tournament_id = int(request.form.get('tournament_id', 0))
    except (TypeError, ValueError):
        flash('Invalid tournament selection.', 'error')
        return redirect(url_for('team.browse_tournaments'))

    team_id = request.form.get('team_id', '').strip()
    if not team_id:
        flash('Please select a team to join this tournament.', 'error')
        return redirect(url_for('team.browse_tournaments'))

    tournament = Tournament.query.get_or_404(tournament_id)
    team = Team.query.filter_by(team_id=team_id, is_active=True).first_or_404()

    if team.managed_by != g.current_user.id:
        flash('You do not have permission to join tournaments with this team.', 'error')
        return redirect(url_for('team.browse_tournaments'))

    if (
        tournament.institution is not None
        and team.institution is not None
        and tournament.institution != team.institution
    ):
        flash('This tournament is limited to another institution.', 'error')
        return redirect(url_for('team.browse_tournaments'))

    existing = TournamentTeam.query.filter_by(tournament_id=tournament_id, team_id=team_id).first()
    if existing:
        if existing.status == 'pending':
            flash(f'Team "{team.name}" already has a pending request for "{tournament.name}".', 'info')
        else:
            flash(f'Team "{team.name}" is already participating in "{tournament.name}".', 'info')
        return redirect(url_for('team.browse_tournaments'))

    association = TournamentTeam(
        tournament_id=tournament_id,
        team_id=team_id,
        status='pending',
        registration_method='team_joined',
        requested_at=current_time(),
        status_updated_at=current_time(),
    )
    db.session.add(association)

    organizer = tournament.creator
    if organizer:
        organizer.notify(
            f'Team "{team.name}" requested to join {tournament.name}.',
            category='info',
            kind='tournament_request',
            status='pending',
            link_target=url_for('smc.pending_teams', tournament_id=tournament.id),
            context_type='tournament',
            context_ref=str(tournament.id),
        )

    db.session.commit()

    flash(
        f'Join request sent for team "{team.name}" to tournament "{tournament.name}". Waiting for SMC approval.',
        'success',
    )
    return redirect(url_for('team.browse_tournaments'))


@team_bp.route('/tournament-team/<int:assoc_id>/respond', methods=['POST'])
@require_team_manager
def respond_invitation(assoc_id):
    """Accept or decline a tournament invitation issued by an SMC."""
    association = (
        TournamentTeam.query.options(joinedload(TournamentTeam.team), joinedload(TournamentTeam.tournament))
        .filter_by(id=assoc_id)
        .first_or_404()
    )

    team = association.team
    tournament = association.tournament

    if not team or team.managed_by != g.current_user.id:
        flash('You do not have permission to manage this invitation.', 'error')
        return redirect(url_for('team.browse_tournaments'))

    if association.status != 'pending' or association.registration_method != 'smc_invited':
        flash('This invitation is no longer available.', 'error')
        return redirect(url_for('team.browse_tournaments'))

    decision = request.form.get('decision')
    organizer = tournament.creator if tournament else None

    manager_notes = Notification.query.filter_by(
        user_id=g.current_user.id,
        context_type='tournament',
        context_ref=str(association.tournament_id),
        kind='tournament_invite',
        status='pending',
    ).all()

    if decision == 'accept':
        association.status = 'active'
        association.status_updated_at = current_time()
        association.approved_at = current_time()
        association.approved_by = organizer.id if organizer else None

        for note in manager_notes:
            note.resolve()

        if organizer and tournament:
            organizer.notify(
                f'Team "{team.name}" accepted the invitation to {tournament.name}.',
                category='success',
                kind='tournament_invite',
                status='active',
                link_target=url_for('smc.tournament_detail', tournament_id=tournament.id),
            )

        db.session.commit()
        flash('Invitation accepted. Your team is now part of the tournament.', 'success')
    elif decision == 'decline':
        for note in manager_notes:
            note.resolve()

        db.session.delete(association)

        if organizer and tournament:
            organizer.notify(
                f'Team "{team.name}" declined the invitation to {tournament.name}.',
                category='warning',
                kind='tournament_invite',
                status='resolved',
                link_target=url_for('smc.tournament_detail', tournament_id=tournament.id),
            )

        db.session.commit()
        flash('Invitation declined.', 'info')
    else:
        flash('Invalid action.', 'error')

    return redirect(url_for('team.browse_tournaments'))


@team_bp.route('/update-profile/<team_id>', methods=['GET', 'POST'])
@require_team_manager
@require_team_ownership
def update_profile(team_id):
    """Update team and player profiles."""
    team = getattr(g, 'team_context', None)
    if not team:
        team = Team.query.options(joinedload(Team.players)).filter_by(team_id=team_id).first_or_404()

    if request.method == 'POST':
        action = request.form.get('action', 'update_team')

        try:
            if action == 'update_team':
                manager_name = request.form.get('manager_name', '').strip()
                manager_contact = request.form.get('manager_contact', '').strip()
                department = request.form.get('department', '').strip()

                if manager_name:
                    team.manager_name = manager_name
                if manager_contact:
                    team.manager_contact = manager_contact
                if department:
                    team.department = department

                db.session.commit()
                flash('Team details updated successfully!', 'success')

            elif action == 'update_players':
                active_players = [player for player in team.players if player.is_active]
                for player in active_players:
                    player_prefix = f'player_{player.id}_'
                    updates = {}
                    for field in ['name', 'contact', 'department', 'year', 'roll_number']:
                        form_key = player_prefix + field
                        if form_key in request.form:
                            value = request.form[form_key].strip()
                            if not value:
                                continue
                            if field == 'roll_number':
                                try:
                                    updates[field] = int(value)
                                except ValueError:
                                    flash(f'Invalid roll number for player {player.name}.', 'error')
                                    continue
                            else:
                                updates[field] = value
                    if updates:
                        player.update_player(**updates)

                db.session.commit()
                flash('Player details updated successfully!', 'success')

            elif action == 'add_player':
                name = request.form.get('new_player_name', '').strip()
                roll_number = request.form.get('new_player_roll', '').strip()

                if not name or not roll_number:
                    flash('Name and roll number are required for new players.', 'error')
                    return redirect(url_for('team.update_profile', team_id=team_id))

                try:
                    roll_number_int = int(roll_number)
                except ValueError:
                    flash('Roll number must be numeric.', 'error')
                    return redirect(url_for('team.update_profile', team_id=team_id))

                player = Player(
                    name=name,
                    roll_number=roll_number_int,
                    contact=request.form.get('new_player_contact', '').strip(),
                    department=request.form.get('new_player_department', team.department).strip() or team.department,
                    year=request.form.get('new_player_year', '').strip(),
                    team_id=team.team_id,
                )
                db.session.add(player)
                db.session.commit()
                flash('Player added successfully!', 'success')

            elif action == 'remove_player':
                try:
                    player_id = int(request.form.get('player_id', '0'))
                except ValueError:
                    flash('Invalid player selection.', 'error')
                    return redirect(url_for('team.update_profile', team_id=team_id))

                player = Player.query.filter_by(id=player_id, team_id=team.team_id).first()
                if player:
                    player.is_active = False
                    db.session.commit()
                    flash('Player removed successfully!', 'success')
                else:
                    flash('Player not found.', 'error')
            else:
                flash('Unsupported action.', 'error')

            return redirect(url_for('team.update_profile', team_id=team_id))

        except Exception as exc:
            db.session.rollback()
            flash(f'Error updating profile: {exc}', 'error')

    active_players = [player for player in team.players if player.is_active]
    return render_template('team/update-profile.html', team=team, players=active_players)