from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from datetime import datetime, date, time, timedelta
import math
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
    DEFAULT_MATCH_DURATION_MINUTES,
)
from blueprints.auth import require_smc

smc_bp = Blueprint('smc', __name__, url_prefix='/smc')
IST = pytz.timezone('Asia/Kolkata')
MIN_KNOCKOUT_SIZE = 2
MAX_KNOCKOUT_SIZE = 32


def _stage_name_for_round(total_rounds: int, round_index: int) -> str:
    mapping = {
        6: ['Round of 64', 'Round of 32', 'Round of 16', 'Quarterfinal', 'Semifinal', 'Final'],
        5: ['Round of 32', 'Round of 16', 'Quarterfinal', 'Semifinal', 'Final'],
        4: ['Round of 16', 'Quarterfinal', 'Semifinal', 'Final'],
        3: ['Quarterfinal', 'Semifinal', 'Final'],
        2: ['Semifinal', 'Final'],
        1: ['Final'],
    }
    names = mapping.get(total_rounds)
    if not names:
        names = [f'Round {i + 1}' for i in range(total_rounds)]
    try:
        return names[round_index - 1]
    except IndexError:
        return f'Round {round_index}'


def _build_knockout_template(bracket_size: int) -> dict:
    """Produce deterministic knockout bracket structure supporting BYEs."""
    if bracket_size < MIN_KNOCKOUT_SIZE or bracket_size > MAX_KNOCKOUT_SIZE:
        raise ValueError('Unsupported bracket size')

    effective_size = 1 << (bracket_size - 1).bit_length()
    total_rounds = int(math.log2(effective_size))

    rounds: list[dict] = []
    current_matches = effective_size // 2
    round_index = 1

    seeds_with_byes: list[int | None] = list(range(1, bracket_size + 1))
    seeds_with_byes.extend([None] * (effective_size - bracket_size))

    first_round_pairs: list[tuple[int | None, int | None]] = []
    for idx in range(current_matches):
        seed_a = seeds_with_byes[idx]
        seed_b = seeds_with_byes[-(idx + 1)]
        first_round_pairs.append((seed_a, seed_b))

    while current_matches >= 1:
        stage_name = _stage_name_for_round(total_rounds, round_index)
        round_entry = {
            'round_number': round_index,
            'stage_name': stage_name,
            'matches': [],
        }

        for match_idx in range(current_matches):
            slot_code = f"R{round_index}M{match_idx + 1}"
            label = f"{stage_name} {match_idx + 1}" if current_matches > 1 else stage_name
            match_info = {
                'slot': slot_code,
                'label': label,
                'advance_to': None,
                'placeholders': {},
            }

            if round_index == 1:
                seed_pair = first_round_pairs[match_idx]
                seed_a, seed_b = seed_pair
                if seed_a is not None:
                    match_info['seed1'] = seed_a
                else:
                    match_info.setdefault('placeholders', {})['team1'] = 'BYE'
                if seed_b is not None:
                    match_info['seed2'] = seed_b
                else:
                    match_info.setdefault('placeholders', {})['team2'] = 'BYE'

            round_entry['matches'].append(match_info)

        rounds.append(round_entry)
        current_matches //= 2
        round_index += 1

    # wire winners to next round slots
    for idx in range(len(rounds) - 1):
        current_round = rounds[idx]['matches']
        next_round = rounds[idx + 1]['matches']
        for match_idx, match_info in enumerate(current_round):
            target_match = next_round[match_idx // 2]
            position = 1 if match_idx % 2 == 0 else 2
            match_info['advance_to'] = {
                'slot': target_match['slot'],
                'position': position,
            }
            placeholders = target_match.setdefault('placeholders', {})
            placeholder_text = f"Winner of {match_info['label']}"
            if position == 1:
                placeholders.setdefault('team1', placeholder_text)
            else:
                placeholders.setdefault('team2', placeholder_text)

    return {
        'size': bracket_size,
        'effective_size': effective_size,
        'rounds': rounds,
    }


def _is_bye_placeholder(value: str | None) -> bool:
    return bool(value and value.strip().lower().startswith('bye'))


def _upsert_bracket_match(tournament: Tournament, slot: str, defaults: dict) -> Match:
    match = Match.query.filter_by(tournament_id=tournament.id, bracket_slot=slot).first()
    if not match:
        match = Match(tournament_id=tournament.id, bracket_slot=slot)
        db.session.add(match)

    match.round_number = defaults.get('round_number')
    match.stage = defaults.get('stage')
    match.date = defaults.get('date')
    match.time = defaults.get('time')
    match.venue = defaults.get('venue') or match.stage or 'TBD'
    match.duration_minutes = defaults.get('duration_minutes', DEFAULT_MATCH_DURATION_MINUTES)
    match.status = defaults.get('status', 'scheduled')

    match.team1_id = defaults.get('team1_id')
    match.team2_id = defaults.get('team2_id')

    placeholders = defaults.get('placeholders') or {}
    match.team1_placeholder = None if match.team1_id else placeholders.get('team1')
    match.team2_placeholder = None if match.team2_id else placeholders.get('team2')

    return match


def _auto_advance_byes(bracket, match_payload: dict[str, dict], match_objects: dict[str, Match]) -> None:
    for slot_code, match in match_objects.items():
        config = match_payload.get(slot_code, {})
        advance = config.get('advance') or {}
        if not advance:
            continue

        team1_placeholder = match.team1_placeholder or (config.get('placeholders') or {}).get('team1')
        team2_placeholder = match.team2_placeholder or (config.get('placeholders') or {}).get('team2')

        winner_id = None
        if match.team1_id and not match.team2_id and _is_bye_placeholder(team2_placeholder):
            winner_id = match.team1_id
        elif match.team2_id and not match.team1_id and _is_bye_placeholder(team1_placeholder):
            winner_id = match.team2_id

        if not winner_id:
            continue

        match.status = 'completed'
        match.winner_id = winner_id
        if match.team1_id == winner_id:
            match.team1_placeholder = None
            match.team1_score = match.team1_score or 'Advance'
            if not match.team2_id:
                match.team2_score = match.team2_score or 'BYE'
        else:
            match.team2_placeholder = None
            match.team2_score = match.team2_score or 'Advance'
            if not match.team1_id:
                match.team1_score = match.team1_score or 'BYE'

        target_slot = advance.get('slot')
        target_position = advance.get('position')
        if target_slot and target_slot in match_objects:
            next_match = match_objects[target_slot]
            if target_position == 1 and not next_match.team1_id:
                next_match.team1_id = winner_id
                next_match.team1_placeholder = None
            elif target_position == 2 and not next_match.team2_id:
                next_match.team2_id = winner_id
                next_match.team2_placeholder = None

        if hasattr(bracket, '_advance_knockout_bracket'):
            bracket._advance_knockout_bracket(match)


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
            institution = request.form.get('institution', '').strip() or g.current_user.institution
            location = request.form.get('location', '').strip()
            tournament_type = request.form.get('tournament_type', 'league')

            if tournament_type not in {'league', 'knockout'}:
                flash('Please choose a valid tournament format.', 'error')
                return redirect(url_for('smc.create_tournament'))
            
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
                created_by=g.current_user.id,
                institution=institution,
                location=location,
                tournament_type=tournament_type,
            )

            db.session.add(tournament)
            db.session.flush()
            tournament.ensure_bracket()
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
    bracket = tournament.ensure_bracket()
    standings = bracket.league_table() if bracket and bracket.format == 'league' else []
    
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
        bracket=bracket,
        standings=standings,
    )


@smc_bp.route('/tournament/<int:tournament_id>/configure-bracket', methods=['GET', 'POST'])
@require_smc
@require_tournament_access
def configure_bracket(tournament_id):
    """Configure bracket rules, points, and knockout seeding."""
    tournament = Tournament.query.get_or_404(tournament_id)
    bracket = tournament.ensure_bracket()
    unread_count = Notification.query.filter_by(user_id=g.current_user.id, is_read=False).count()

    league_defaults = {
        'points_win': bracket.points_win,
        'points_draw': bracket.points_draw,
        'points_loss': bracket.points_loss,
    }

    active_associations = [
        assoc
        for assoc in tournament.tournament_teams
        if assoc.team and assoc.status in {'active', 'pending', 'champion'}
    ]
    available_teams = sorted(
        (assoc.team for assoc in active_associations if assoc.team),
        key=lambda team: team.name.lower(),
    )

    config_payload = bracket.config_payload or {}
    stored_size = config_payload.get('size')
    default_size = max(MIN_KNOCKOUT_SIZE, min(MAX_KNOCKOUT_SIZE, len(available_teams) or 4))
    selected_size = default_size
    if isinstance(stored_size, int) and MIN_KNOCKOUT_SIZE <= stored_size <= MAX_KNOCKOUT_SIZE:
        selected_size = stored_size

    requested_size = request.args.get('size', type=int)
    if requested_size and MIN_KNOCKOUT_SIZE <= requested_size <= MAX_KNOCKOUT_SIZE:
        selected_size = requested_size

    knockout_template = _build_knockout_template(selected_size)
    existing_seed_map = {int(k): v for k, v in (config_payload.get('seed_map') or {}).items()}
    match_map = config_payload.get('match_map') or {}

    # Prefill schedule from saved payload or persisted matches
    prefill_schedule: dict[str, dict] = {}
    for slot, meta in match_map.items():
        schedule = meta.get('schedule', {})
        prefill_schedule[slot] = {
            'date': schedule.get('date'),
            'time': schedule.get('time'),
            'venue': schedule.get('venue'),
            'duration': schedule.get('duration', DEFAULT_MATCH_DURATION_MINUTES),
        }

    slot_matches = {
        m.bracket_slot: m
        for m in Match.query.filter_by(tournament_id=tournament.id).filter(Match.bracket_slot.isnot(None)).all()
    }

    for slot_code, match in slot_matches.items():
        if slot_code not in prefill_schedule:
            prefill_schedule[slot_code] = {
                'date': match.date.strftime('%Y-%m-%d') if match.date else None,
                'time': match.time.strftime('%H:%M') if match.time else None,
                'venue': match.venue,
                'duration': match.duration_minutes or DEFAULT_MATCH_DURATION_MINUTES,
            }

    if request.method == 'POST':
        format_choice = request.form.get('format', bracket.format or 'league')

        if format_choice == 'league':
            try:
                bracket.points_win = int(request.form.get('points_win', bracket.points_win))
                bracket.points_draw = int(request.form.get('points_draw', bracket.points_draw))
                bracket.points_loss = int(request.form.get('points_loss', bracket.points_loss))
            except ValueError:
                flash('Points must be numeric values.', 'error')
                return redirect(url_for('smc.configure_bracket', tournament_id=tournament_id))

            bracket.format = 'league'
            bracket.config_payload = {}
            db.session.commit()
            flash('League scoring updated for this tournament.', 'success')
            return redirect(url_for('smc.tournament_detail', tournament_id=tournament_id))

        # Knockout configuration
        try:
            bracket_size = int(request.form.get('knockout_size', selected_size))
        except (TypeError, ValueError):
            flash('Choose a valid bracket size.', 'error')
            return redirect(url_for('smc.configure_bracket', tournament_id=tournament_id))

        if bracket_size < MIN_KNOCKOUT_SIZE or bracket_size > MAX_KNOCKOUT_SIZE:
            flash(f'Bracket size must be between {MIN_KNOCKOUT_SIZE} and {MAX_KNOCKOUT_SIZE} teams.', 'error')
            return redirect(url_for('smc.configure_bracket', tournament_id=tournament_id))

        knockout_template = _build_knockout_template(bracket_size)
        valid_team_ids = {team.team_id for team in available_teams}
        seeds: dict[int, str | None] = {}
        seen_assigned: set[str] = set()
        for seed_idx in range(1, bracket_size + 1):
            field_name = f'seed_{seed_idx}'
            team_id = (request.form.get(field_name) or '').strip() or None
            if team_id:
                if team_id not in valid_team_ids:
                    flash('Selected seeds include teams that are not part of this tournament.', 'error')
                    return redirect(url_for('smc.configure_bracket', tournament_id=tournament_id, size=bracket_size))
                if team_id in seen_assigned:
                    flash('Each team can only occupy one seed slot.', 'error')
                    return redirect(url_for('smc.configure_bracket', tournament_id=tournament_id, size=bracket_size))
                seen_assigned.add(team_id)
            seeds[seed_idx] = team_id

        match_payload: dict[str, dict] = {}
        match_objects: dict[str, Match] = {}

        # Remove obsolete bracket-linked matches if reconfiguring
        existing_bracket_matches = Match.query.filter_by(tournament_id=tournament.id).filter(Match.bracket_slot.isnot(None)).all()
        for existing_match in existing_bracket_matches:
            # If match already completed, prevent destructive reconfiguration
            if existing_match.status == 'completed':
                flash('Cannot reconfigure bracket after results have been recorded.', 'error')
                return redirect(url_for('smc.configure_bracket', tournament_id=tournament_id, size=bracket_size))

        # Fresh rebuild: delete existing bracket matches to avoid duplicates
        for existing_match in existing_bracket_matches:
            db.session.delete(existing_match)

        for round_entry in knockout_template['rounds']:
            for match_entry in round_entry['matches']:
                slot_code = match_entry['slot']
                schedule_prefix = f'{slot_code}'
                date_raw = (request.form.get(f'date_{schedule_prefix}') or '').strip()
                time_raw = (request.form.get(f'time_{schedule_prefix}') or '').strip()
                venue_value = (request.form.get(f'venue_{schedule_prefix}') or '').strip()
                duration_raw = (request.form.get(f'duration_{schedule_prefix}') or '').strip()

                match_date = None
                match_time = None

                if date_raw and time_raw:
                    try:
                        match_date = datetime.strptime(date_raw, '%Y-%m-%d').date()
                        match_time = datetime.strptime(time_raw, '%H:%M').time()
                    except ValueError:
                        flash('Provide valid dates and times in the format YYYY-MM-DD and HH:MM.', 'error')
                        db.session.rollback()
                        return redirect(url_for('smc.configure_bracket', tournament_id=tournament_id, size=bracket_size))

                    if match_date < tournament.start_date or match_date > tournament.end_date:
                        flash('Match dates must fall within the tournament window.', 'error')
                        db.session.rollback()
                        return redirect(url_for('smc.configure_bracket', tournament_id=tournament_id, size=bracket_size))
                elif date_raw or time_raw:
                    flash('Please provide both a date and time when scheduling a knockout match.', 'error')
                    db.session.rollback()
                    return redirect(url_for('smc.configure_bracket', tournament_id=tournament_id, size=bracket_size))

                try:
                    duration_minutes = int(duration_raw) if duration_raw else DEFAULT_MATCH_DURATION_MINUTES
                except ValueError:
                    flash('Duration must be numeric minutes.', 'error')
                    db.session.rollback()
                    return redirect(url_for('smc.configure_bracket', tournament_id=tournament_id, size=bracket_size))

                if duration_minutes <= 0:
                    flash('Duration must be positive.', 'error')
                    db.session.rollback()
                    return redirect(url_for('smc.configure_bracket', tournament_id=tournament_id, size=bracket_size))

                placeholders = match_entry.get('placeholders', {})
                fallback_date = match_date or tournament.start_date or date.today()
                fallback_time = match_time or time(10, 0)
                match_defaults = {
                    'round_number': round_entry['round_number'],
                    'stage': match_entry['label'],
                    'date': fallback_date,
                    'time': fallback_time,
                    'venue': venue_value or match_entry['label'],
                    'duration_minutes': duration_minutes,
                    'placeholders': placeholders,
                }

                seed_one = match_entry.get('seed1')
                seed_two = match_entry.get('seed2')

                if seed_one:
                    match_defaults['team1_id'] = seeds.get(seed_one)
                if seed_two:
                    match_defaults['team2_id'] = seeds.get(seed_two)

                new_match = _upsert_bracket_match(tournament, slot_code, match_defaults)
                match_objects[slot_code] = new_match

                match_payload[slot_code] = {
                    'round': round_entry['round_number'],
                    'round_title': round_entry['stage_name'],
                    'stage': match_entry['label'],
                    'advance': match_entry.get('advance_to'),
                    'seed1': seed_one,
                    'seed2': seed_two,
                    'placeholders': placeholders,
                    'schedule': {
                        'date': match_date.strftime('%Y-%m-%d') if match_date else None,
                        'time': match_time.strftime('%H:%M') if match_time else None,
                        'venue': new_match.venue if venue_value or match_date or match_time else None,
                        'duration': duration_minutes,
                    },
                }

        bracket.format = 'knockout'
        bracket.config_payload = {
            'type': 'knockout',
            'size': bracket_size,
            'seed_map': {k: v for k, v in seeds.items()},
            'match_map': match_payload,
        }

        db.session.flush()
        _auto_advance_byes(bracket, match_payload, match_objects)

        db.session.commit()
        flash('Knockout bracket configured successfully.', 'success')
        return redirect(url_for('smc.tournament_detail', tournament_id=tournament_id))

    context = {
        'tournament': tournament,
        'bracket': bracket,
        'league_defaults': league_defaults,
        'available_teams': available_teams,
        'knockout_template': knockout_template,
        'seed_map': existing_seed_map,
        'schedule_prefill': prefill_schedule,
        'selected_size': selected_size,
        'match_map': match_map,
        'MIN_KNOCKOUT_SIZE': MIN_KNOCKOUT_SIZE,
        'MAX_KNOCKOUT_SIZE': MAX_KNOCKOUT_SIZE,
        'unread_notification_count': unread_count,
    }
    return render_template('smc/configure-bracket.html', **context)


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
            venue = request.form['venue'].strip()
            stage = request.form.get('stage', '').strip() or None
            round_number_raw = request.form.get('round_number', '').strip()
            round_number = int(round_number_raw) if round_number_raw.isdigit() else None
            duration_input = request.form.get('duration_minutes', '').strip()
            duration = int(duration_input) if duration_input.isdigit() else DEFAULT_MATCH_DURATION_MINUTES

            if duration <= 0:
                flash('Duration must be a positive number of minutes.', 'error')
                return redirect(url_for('smc.schedule_matches', tournament_id=tournament_id))
            
            if match_date < tournament.start_date or match_date > tournament.end_date:
                flash(f'Match date must be between {tournament.start_date} and {tournament.end_date}', 'error')
                return redirect(url_for('smc.schedule_matches', tournament_id=tournament_id))
            
            start_dt = datetime.combine(match_date, match_time)
            end_dt = start_dt + timedelta(minutes=duration)

            conflicts = Match.query.filter(
                Match.tournament_id == tournament_id,
                Match.date == match_date,
                Match.status.in_(['scheduled', 'active']),
                or_(
                    Match.venue == venue,
                    Match.team1_id.in_([team1_id, team2_id]),
                    Match.team2_id.in_([team1_id, team2_id]),
                ),
            ).all()

            for existing in conflicts:
                if existing.overlaps_range(start_dt, end_dt):
                    if existing.venue == venue:
                        flash(
                            f'Venue "{venue}" is unavailable between {existing.time.strftime("%H:%M")} and {existing.end_datetime.strftime("%H:%M")}.',
                            'error',
                        )
                        return redirect(url_for('smc.schedule_matches', tournament_id=tournament_id))
                    if team1_id in [existing.team1_id, existing.team2_id] or team2_id in [existing.team1_id, existing.team2_id]:
                        opponent = existing.opponent_of(team1_id) or existing.opponent_of(team2_id)
                        opponent_name = opponent.name if opponent else 'another opponent'
                        flash(
                            f'One of the teams already plays {opponent_name} around this time. Adjust the slot.',
                            'error',
                        )
                        return redirect(url_for('smc.schedule_matches', tournament_id=tournament_id))
            
            match = Match(
                tournament_id=tournament_id,
                team1_id=team1_id,
                team2_id=team2_id,
                date=match_date,
                time=match_time,
                venue=venue,
                round_number=round_number,
                stage=stage,
                duration_minutes=duration,
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
    default_duration = DEFAULT_MATCH_DURATION_MINUTES
    
    # Get matches for this tournament
    all_matches = Match.query.filter_by(tournament_id=tournament_id).order_by(Match.date, Match.time).all()
    live_matches = [m for m in all_matches if m.status == 'active']
    upcoming_matches = [
        m for m in all_matches if m.status == 'scheduled' and m.date >= date.today()
    ]
    completed_matches = [m for m in all_matches if m.status == 'completed']

    return render_template('smc/schedule-matches.html',
                           tournament=tournament,
                           teams=tournament_teams,
                           live_matches=live_matches,
                           upcoming_matches=upcoming_matches,
                           completed_matches=completed_matches,
                           unread_notification_count=unread_count,
                           DEFAULT_MATCH_DURATION_MINUTES=default_duration)


@smc_bp.route('/tournament/<int:tournament_id>/matches/<int:match_id>/status', methods=['POST'])
@require_smc
@require_tournament_access
def update_match_status(tournament_id, match_id):
    """Mark a scheduled match as live or revert to scheduled."""
    match = Match.query.filter_by(id=match_id, tournament_id=tournament_id).first_or_404()
    new_status = request.form.get('status', 'scheduled')
    next_url = request.form.get('next') or url_for('smc.schedule_matches', tournament_id=tournament_id)

    if new_status not in {'scheduled', 'active'}:
        flash('Unsupported status update.', 'error')
        return redirect(next_url)

    if match.status == 'completed':
        flash('Completed matches cannot change status.', 'error')
        return redirect(next_url)

    match.status = new_status
    db.session.commit()

    label = 'live' if new_status == 'active' else 'scheduled'
    flash(f'Match {match.versus_display} is now marked as {label}.', 'success')
    return redirect(next_url)


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
            
            # Set winner if provided
            winner_id = request.form.get('winner_id')
            if winner_id and winner_id != '':
                if winner_id not in [match.team1_id, match.team2_id]:
                    flash('Winner must be one of the participating teams!', 'error')
                    return redirect(url_for('smc.add_results', tournament_id=tournament_id))
                match.winner_id = winner_id
            else:
                match.winner_id = None

            match.status = request.form.get('match_status', 'completed')
            db.session.flush()

            bracket = match.tournament.ensure_bracket()
            bracket.update_after_result(match)
            db.session.commit()

            flash(f'Results updated for match: {match.versus_display}', 'success')
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