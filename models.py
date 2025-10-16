from datetime import datetime, date, time, timedelta
import re
import pytz

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, inspect, text, func
from sqlalchemy.orm import validates
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

IST = pytz.timezone('Asia/Kolkata')
AVAILABLE_INSTITUTIONS = (
    'General Institution',
    'Tech University',
    'Commerce College',
)

AVAILABLE_INSTITUTIONS = (
    'Heritage Institute of Technology, Kolkata',
    'General Institution',
    'Tech University',
    'Commerce College',
)

DEFAULT_MATCH_DURATION_MINUTES = 90


def current_time():
    return datetime.now(IST)


class User(db.Model):
    """Users who can log in - SMCs and Team Managers."""

    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'smc' or 'team_manager'
    institution = db.Column(db.String(100))
    phone_number = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=current_time)

    tournaments_created = db.relationship(
        'Tournament', backref='creator', lazy=True, foreign_keys='Tournament.created_by'
    )
    teams_created = db.relationship(
        'Team', backref='creator', lazy=True, foreign_keys='Team.created_by'
    )
    teams_managed = db.relationship(
        'Team', backref='manager', lazy=True, foreign_keys='Team.managed_by'
    )
    notifications = db.relationship(
        'Notification',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan',
        foreign_keys='Notification.user_id',
    )

    def __repr__(self):  # pragma: no cover - debug helper
        return f"<User {self.id} {self.username} role={self.role}>"

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def notify(
        self,
        message: str,
        category: str = 'info',
        kind: str = 'general',
        status: str = 'active',
        link_target: str = None,
        context_type: str = None,
        context_ref: str = None,
        actor_id: int | None = None,
        commit: bool = False,
    ):
        """Create an in-app notification entry for a user."""
        if actor_id is not None and actor_id == self.id:
            return None
        note = Notification(
            user_id=self.id,
            message=message,
            category=category,
            kind=kind,
            status=status,
            context_type=context_type,
            context_ref=context_ref,
            link_target=link_target,
            actor_id=actor_id,
        )
        db.session.add(note)
        if commit:
            db.session.commit()
        return note

    @staticmethod
    def validate_format(
        username: str,
        email: str,
        password: str,
        role: str,
        phone_number: str | None = None,
    ) -> list[str]:
        """Validate registration data format without using the database."""
        errors: list[str] = []

        if not username or len(username.strip()) < 3:
            errors.append("Username must be at least 3 characters")

        if username and not username.replace('_', '').replace('-', '').isalnum():
            errors.append("Username can only contain letters, numbers, hyphens and underscores")

        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not email or not re.match(email_pattern, email):
            errors.append("Valid email required")

        if not password or len(password) < 8:
            errors.append("Password must be at least 8 characters")

        password_regex = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$"
        if password and not re.fullmatch(password_regex, password):
            errors.append(
                "Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character"
            )

        if role not in ['smc', 'team_manager']:
            errors.append("Invalid role selected")

        if phone_number:
            phone_pattern = r'^\+?[0-9\s-]{7,15}$'
            if not re.fullmatch(phone_pattern, phone_number):
                errors.append("Phone number must contain 7-15 digits and may include + or -")

        return errors

class Notification(db.Model):
    """Persistent notifications surfaced via dashboards and dedicated feeds."""

    __tablename__ = 'notification'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(40), default='info')
    kind = db.Column(db.String(40), default='general')
    status = db.Column(db.String(20), default='active')  # pending, active, resolved, archived
    context_type = db.Column(db.String(40))  # e.g. tournament, team, match
    context_ref = db.Column(db.String(40))
    link_target = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=current_time)
    expires_at = db.Column(db.DateTime)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self):  # pragma: no cover - debug helper
        return f"<Notification {self.id} user={self.user_id} status={self.status}>"

    actor = db.relationship('User', foreign_keys=[actor_id], backref='notifications_triggered')

    def activate(self):
        self.status = 'active'
        self.is_read = False

    def resolve(self):
        self.status = 'resolved'
        self.is_read = True

    @classmethod
    def active_for_user(cls, user_id: int):
        query = cls.query.filter_by(user_id=user_id).filter(cls.status.in_(['pending', 'active']))
        query = query.filter(
            or_(cls.expires_at.is_(None), cls.expires_at > current_time())
        )
        return query.order_by(cls.created_at.desc())

    @classmethod
    def cleanup_expired(cls):
        expired = cls.query.filter(
            cls.expires_at.isnot(None),
            cls.expires_at <= current_time(),
        ).all()
        removed = len(expired)
        for note in expired:
            db.session.delete(note)
        if removed:
            db.session.commit()
        return removed


class Bracket(db.Model):
    """Tournament format configuration and progression rules."""

    __tablename__ = 'bracket'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False, unique=True)
    format = db.Column(db.String(20), default='league')  # league or knockout
    points_win = db.Column(db.Integer, default=3)
    points_draw = db.Column(db.Integer, default=1)
    points_loss = db.Column(db.Integer, default=0)
    config_payload = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=current_time)
    updated_at = db.Column(db.DateTime, default=current_time, onupdate=current_time)

    tournament = db.relationship('Tournament', back_populates='bracket', uselist=False)

    def update_after_result(self, match: 'Match') -> None:
        """Update standings or knockout progression after a result is posted."""
        if not match or match.tournament_id != self.tournament_id:
            return

        if match.status != 'completed':
            return

        if self.format == 'knockout':
            self._apply_knockout_progression(match)
        else:
            self._apply_league_points(match)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _apply_knockout_progression(self, match: 'Match') -> None:
        if not match.winner_id:
            return

        winner_assoc = TournamentTeam.query.filter_by(
            tournament_id=self.tournament_id,
            team_id=match.winner_id,
        ).first()
        if winner_assoc:
            winner_assoc.set_status('active')

        loser_id = match.team1_id if match.team1_id != match.winner_id else match.team2_id
        loser_assoc = TournamentTeam.query.filter_by(
            tournament_id=self.tournament_id,
            team_id=loser_id,
        ).first()
        if loser_assoc:
            loser_assoc.set_status('eliminated')

        if self._is_final_match(match) and winner_assoc:
            winner_assoc.set_status('champion')
            tournament = winner_assoc.tournament
            if tournament and tournament.status != 'completed':
                tournament.status = 'completed'

        self._advance_knockout_bracket(match)

    def _apply_league_points(self, match: 'Match') -> None:
        team1_assoc = TournamentTeam.query.filter_by(
            tournament_id=self.tournament_id,
            team_id=match.team1_id,
        ).first()
        team2_assoc = TournamentTeam.query.filter_by(
            tournament_id=self.tournament_id,
            team_id=match.team2_id,
        ).first()

        if not team1_assoc or not team2_assoc:
            return

        team1_score = self._score_as_int(match.team1_score)
        team2_score = self._score_as_int(match.team2_score)

        if match.winner_id == match.team1_id:
            team1_assoc.points += self.points_win
            team2_assoc.points += self.points_loss
            team1_assoc.set_status('active')
            if team2_assoc.status == 'pending':
                team2_assoc.set_status('active')
        elif match.winner_id == match.team2_id:
            team2_assoc.points += self.points_win
            team1_assoc.points += self.points_loss
            team2_assoc.set_status('active')
            if team1_assoc.status == 'pending':
                team1_assoc.set_status('active')
        else:
            team1_assoc.points += self.points_draw
            team2_assoc.points += self.points_draw
            team1_assoc.set_status('active')
            team2_assoc.set_status('active')

        team1_assoc.stats_payload = team1_assoc.stats_payload or {}
        team2_assoc.stats_payload = team2_assoc.stats_payload or {}

        team1_assoc.stats_payload['goals_for'] = team1_assoc.stats_payload.get('goals_for', 0) + team1_score
        team1_assoc.stats_payload['goals_against'] = team1_assoc.stats_payload.get('goals_against', 0) + team2_score
        team2_assoc.stats_payload['goals_for'] = team2_assoc.stats_payload.get('goals_for', 0) + team2_score
        team2_assoc.stats_payload['goals_against'] = team2_assoc.stats_payload.get('goals_against', 0) + team1_score

    def _score_as_int(self, score_value: str | None) -> int:
        try:
            return int(score_value)
        except (TypeError, ValueError):
            return 0

    def _is_final_match(self, match: 'Match') -> bool:
        if match.stage and match.stage.lower() == 'final':
            return True

        if match.round_number is None:
            return False

        max_round = db.session.query(func.max(Match.round_number)).filter(
            Match.tournament_id == self.tournament_id,
            Match.round_number.isnot(None),
        ).scalar()

        return bool(max_round and match.round_number == max_round)

    def _advance_knockout_bracket(self, match: 'Match') -> None:
        payload = self.config_payload or {}
        match_map = payload.get('match_map') or {}
        if not match.bracket_slot or match.bracket_slot not in match_map:
            return

        advance = match_map[match.bracket_slot].get('advance')
        if not advance:
            return

        target_slot = advance.get('slot')
        target_position = advance.get('position')
        if not target_slot or target_position not in (1, 2):
            return

        target_config = match_map.get(target_slot, {})
        schedule = target_config.get('schedule', {})
        placeholders = target_config.get('placeholders', {})

        next_match = Match.query.filter_by(tournament_id=self.tournament_id, bracket_slot=target_slot).first()

        if not next_match:
            next_match = Match(
                tournament_id=self.tournament_id,
                bracket_slot=target_slot,
                round_number=target_config.get('round'),
                stage=target_config.get('stage'),
                date=self._resolve_schedule_date(schedule, match.date),
                time=self._resolve_schedule_time(schedule, match.time),
                venue=schedule.get('venue') or match.venue,
                duration_minutes=schedule.get('duration') or match.duration_minutes or DEFAULT_MATCH_DURATION_MINUTES,
                status='scheduled',
            )
            next_match.team1_placeholder = placeholders.get('team1')
            next_match.team2_placeholder = placeholders.get('team2')
            db.session.add(next_match)
        else:
            if not next_match.date:
                next_match.date = self._resolve_schedule_date(schedule, match.date)
            if not next_match.time:
                next_match.time = self._resolve_schedule_time(schedule, match.time)
            if not next_match.venue:
                next_match.venue = schedule.get('venue') or match.venue
            if not next_match.duration_minutes:
                next_match.duration_minutes = schedule.get('duration') or match.duration_minutes or DEFAULT_MATCH_DURATION_MINUTES

        if target_position == 1:
            next_match.team1_id = match.winner_id
            next_match.team1_placeholder = None
        else:
            next_match.team2_id = match.winner_id
            next_match.team2_placeholder = None

        if next_match.team1_id is None:
            next_match.team1_placeholder = placeholders.get('team1')
        if next_match.team2_id is None:
            next_match.team2_placeholder = placeholders.get('team2')

    def _resolve_schedule_date(self, schedule: dict, fallback_date: date | None) -> date:
        date_str = schedule.get('date') if schedule else None
        if date_str:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if fallback_date:
            return fallback_date
        tournament = getattr(self, 'tournament', None)
        return tournament.start_date if tournament else date.today()

    def _resolve_schedule_time(self, schedule: dict, fallback_time: time | None) -> time:
        time_str = schedule.get('time') if schedule else None
        if time_str:
            try:
                return datetime.strptime(time_str, '%H:%M').time()
            except ValueError:
                pass
        if fallback_time:
            return fallback_time
        return time(10, 0)

    def league_table(self) -> list[dict]:
        if self.format != 'league' or not self.tournament:
            return []

        standings = []
        for assoc in self.tournament.tournament_teams:
            if not assoc.team:
                continue
            record = assoc.team.get_match_record(self.tournament_id)
            meta = assoc.stats_payload or {}
            goals_for = meta.get('goals_for', 0)
            goals_against = meta.get('goals_against', 0)
            goal_diff = goals_for - goals_against
            standings.append(
                {
                    'association': assoc,
                    'team': assoc.team,
                    'points': assoc.points,
                    'record': record,
                    'goals_for': goals_for,
                    'goals_against': goals_against,
                    'goal_diff': goal_diff,
                }
            )

        standings.sort(
            key=lambda entry: (
                entry['points'],
                entry['record']['wins'],
                entry['goal_diff'],
                entry['goals_for'],
            ),
            reverse=True,
        )
        return standings


class Tournament(db.Model):
    __tablename__ = 'tournament'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='upcoming')  # upcoming, active, completed
    rules = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    institution = db.Column(db.String(100))
    location = db.Column(db.String(100))
    tournament_type = db.Column(db.String(20), default='league')
    created_at = db.Column(db.DateTime, default=current_time)

    matches = db.relationship('Match', backref='tournament', lazy=True, foreign_keys='Match.tournament_id')
    tournament_teams = db.relationship(
        'TournamentTeam', backref='tournament', lazy=True, cascade='all, delete-orphan'
    )
    bracket = db.relationship(
        'Bracket', back_populates='tournament', uselist=False, cascade='all, delete-orphan'
    )

    def __repr__(self):  # pragma: no cover - debug helper
        return f"<Tournament {self.id} {self.name}>"

    @validates('end_date')
    def validate_end_date(self, key, value):
        if self.start_date and value < self.start_date:
            raise ValueError('End date must be on or after the start date')
        return value

    def get_teams(self):
        return [tt.team for tt in self.tournament_teams]

    def get_active_teams(self):
        return [tt.team for tt in self.tournament_teams if tt.status == 'active']

    def ensure_bracket(self) -> 'Bracket':
        if self.bracket:
            return self.bracket
        bracket = Bracket(
            tournament_id=self.id,
            format=self.tournament_type or 'league',
        )
        db.session.add(bracket)
        self.bracket = bracket
        return bracket

    def active_standings(self):
        bracket = self.bracket
        if bracket and bracket.format == 'league':
            return bracket.league_table()
        return []

    def add_team(self, team, added_by, method='smc_added', auto_commit=False):
        """Attach team to tournament while respecting institution policy."""
        if (
            self.institution is not None
            and team.institution is not None
            and team.institution != self.institution
        ):
            raise ValueError('Team and tournament must belong to the same institution')

        existing = TournamentTeam.query.filter_by(tournament_id=self.id, team_id=team.team_id).first()
        if existing:
            raise ValueError('Team already associated with tournament')

        if method not in {'smc_added', 'smc_invited', 'team_joined'}:
            raise ValueError('Unsupported registration method')

        status = 'active' if method == 'smc_added' else 'pending'
        approval_time = current_time() if status == 'active' else None

        assoc = TournamentTeam(
            tournament_id=self.id,
            team_id=team.team_id,
            registration_method=method,
            status=status,
            requested_at=current_time(),
            approved_by=added_by.id if status == 'active' else None,
            approved_at=approval_time,
            status_updated_at=approval_time or current_time(),
        )
        db.session.add(assoc)

        if status == 'active' and team.manager:
            actor_id = getattr(added_by, 'id', None)
            if actor_id is None or team.manager.id != actor_id:
                team.manager.notify(
                    f'{team.name} was added to tournament {self.name}.',
                    category='success',
                    link_target=f'/team/team/{team.team_id}',
                    context_type='tournament',
                    context_ref=str(self.id),
                    actor_id=actor_id,
                )

        if auto_commit:
            db.session.commit()
        return assoc


class TournamentTeam(db.Model):
    """Associates teams with tournaments, tracking approvals and standings."""

    __tablename__ = 'tournament_team'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    team_id = db.Column(db.String(20), db.ForeignKey('team.team_id'), nullable=False)
    registration_method = db.Column(db.String(20), default='team_joined')  # team_joined, smc_added, smc_invited
    status = db.Column(db.String(20), default='pending')  # pending, active, eliminated, champion
    points = db.Column(db.Integer, default=0)
    requested_at = db.Column(db.DateTime, default=current_time)
    approved_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    status_updated_at = db.Column(db.DateTime, default=current_time)
    stats_payload = db.Column(db.JSON, default=dict)

    __table_args__ = (db.UniqueConstraint('tournament_id', 'team_id', name='unique_tournament_team'),)

    team = db.relationship('Team', back_populates='tournament_teams')
    approver = db.relationship('User', foreign_keys=[approved_by])

    def set_status(self, new_status: str, actor=None):
        self.status = new_status
        self.status_updated_at = current_time()
        if new_status == 'active':
            self.approved_at = current_time()
            self.approved_by = actor.id if actor else None


class Team(db.Model):
    __tablename__ = 'team'

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50), nullable=False)
    manager_name = db.Column(db.String(100), nullable=False)
    manager_contact = db.Column(db.String(20))
    institution = db.Column(db.String(100))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    managed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=current_time)

    players = db.relationship('Player', backref='team', lazy=True, cascade='all, delete-orphan')
    tournament_teams = db.relationship('TournamentTeam', back_populates='team', lazy=True)

    matches_as_team1 = db.relationship(
        'Match',
        foreign_keys='Match.team1_id',
        primaryjoin='Team.team_id == Match.team1_id',
        backref='team1',
        lazy=True,
    )
    matches_as_team2 = db.relationship(
        'Match',
        foreign_keys='Match.team2_id',
        primaryjoin='Team.team_id == Match.team2_id',
        backref='team2',
        lazy=True,
    )
    matches_won = db.relationship(
        'Match',
        foreign_keys='Match.winner_id',
        primaryjoin='Team.team_id == Match.winner_id',
        backref='winner',
        lazy=True,
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.managed_by is None and self.created_by is not None:
            self.managed_by = self.created_by
        if not self.manager_name:
            self.manager_name = 'Unassigned'

    def __repr__(self):  # pragma: no cover - debug helper
        return f"<Team {self.team_id} {self.name}>"

    @property
    def is_self_managed(self) -> bool:
        manager_user = getattr(self, 'manager', None)
        return bool(manager_user and manager_user.role == 'team_manager')

    def assign_manager(self, user, actor_id: int | None = None):
        self.managed_by = user.id
        self.manager_name = getattr(user, 'username', self.manager_name)
        if getattr(user, 'phone_number', None):
            self.manager_contact = user.phone_number
        if getattr(user, 'role', None) == 'team_manager':
            user.notify(
                f'You are now managing team {self.name}.',
                category='info',
                kind='team_assignment',
                status='active',
                link_target=f'/team/team/{self.team_id}',
                actor_id=actor_id,
                commit=False,
            )

    def get_tournaments(self):
        return [tt.tournament for tt in self.tournament_teams]

    def get_upcoming_matches(self, tournament_id=None):
        query = Match.query.filter(
            or_(Match.team1_id == self.team_id, Match.team2_id == self.team_id),
            Match.status == 'scheduled',
            Match.date >= date.today(),
        )
        if tournament_id:
            query = query.filter(Match.tournament_id == tournament_id)
        return query.order_by(Match.date, Match.time).all()

    def get_completed_matches(self, tournament_id=None):
        query = Match.query.filter(
            or_(Match.team1_id == self.team_id, Match.team2_id == self.team_id),
            Match.status == 'completed',
        )
        if tournament_id:
            query = query.filter(Match.tournament_id == tournament_id)
        return query.order_by(Match.date.desc(), Match.time.desc()).all()

    def get_match_record(self, tournament_id=None):
        completed = self.get_completed_matches(tournament_id)
        wins = len([m for m in completed if m.winner_id == self.team_id])
        losses = len([m for m in completed if m.winner_id and m.winner_id != self.team_id])
        draws = len([m for m in completed if not m.winner_id])
        return {'wins': wins, 'losses': losses, 'draws': draws, 'total': len(completed)}


class Player(db.Model):
    __tablename__ = 'player'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.Integer, unique=True, nullable=False)
    contact = db.Column(db.String(15))
    department = db.Column(db.String(50))
    year = db.Column(db.String(10))
    team_id = db.Column(db.String(20), db.ForeignKey('team.team_id'), nullable=False)
    created_at = db.Column(db.DateTime, default=current_time)
    is_active = db.Column(db.Boolean, default=True)

    def update_player(self, **kwargs):
        for field, value in kwargs.items():
            if hasattr(self, field) and value is not None:
                if isinstance(value, str) and value.strip() == '':
                    continue
                setattr(self, field, value)


class Match(db.Model):
    __tablename__ = 'match'

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    team1_id = db.Column(db.String(20), db.ForeignKey('team.team_id'))
    team2_id = db.Column(db.String(20), db.ForeignKey('team.team_id'))
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    venue = db.Column(db.String(100), nullable=False)
    round_number = db.Column(db.Integer)
    stage = db.Column(db.String(50))
    duration_minutes = db.Column(db.Integer, default=DEFAULT_MATCH_DURATION_MINUTES)
    team1_score = db.Column(db.String(100))
    team2_score = db.Column(db.String(100))
    winner_id = db.Column(db.String(20), db.ForeignKey('team.team_id'))
    status = db.Column(db.String(20), default='scheduled')
    bracket_slot = db.Column(db.String(40))
    team1_placeholder = db.Column(db.String(100))
    team2_placeholder = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=current_time)

    @property
    def is_upcoming(self):
        """Check if match is upcoming"""
        return self.status == 'scheduled' and self.date >= date.today()

    @property
    def is_live(self):
        return self.status == 'active'
    
    @property
    def versus_display(self):
        """Display match as Team A vs Team B"""
        return f"{self._display_name(1)} vs {self._display_name(2)}"
    
    @property
    def score_display(self) -> str:
        if self.status != 'completed':
            return "Match not completed"
        return f"{self._display_name(1)}: {self.team1_score} | {self._display_name(2)}: {self.team2_score}"

    @property
    def result_display(self) -> str:
        if self.status != 'completed':
            return "Match not completed"
        if self.winner_id:
            return f"Winner: {self.winner.name}"
        return "Match drawn"

    def opponent_of(self, team_id):
        if not team_id:
            return None
        if self.team1_id == team_id:
            return self.team2
        if self.team2_id == team_id:
            return self.team1
        return None

    @property
    def duration_label(self) -> str:
        minutes = self.duration_minutes or DEFAULT_MATCH_DURATION_MINUTES
        return f"{minutes} min"

    @property
    def start_datetime(self) -> datetime:
        return datetime.combine(self.date, self.time)

    @property
    def end_datetime(self) -> datetime:
        minutes = self.duration_minutes or DEFAULT_MATCH_DURATION_MINUTES
        return self.start_datetime + timedelta(minutes=minutes)

    def overlaps_range(self, start_dt: datetime, end_dt: datetime) -> bool:
        return self.start_datetime < end_dt and start_dt < self.end_datetime

    def _display_name(self, slot: int) -> str:
        team = self.team1 if slot == 1 else self.team2
        placeholder = self.team1_placeholder if slot == 1 else self.team2_placeholder
        if team:
            return team.name
        if placeholder:
            return placeholder
        return 'TBD'


def init_default_data():
    """Initialize default data for the application."""

    ensure_schema_integrity()

    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@tourneytrack.local',
            role='smc',
            institution=AVAILABLE_INSTITUTIONS[0],
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.flush()
    else:
        if not admin.email:
            admin.email = 'admin@tourneytrack.local'
        if not admin.role:
            admin.role = 'smc'
        if not admin.institution:
            admin.institution = AVAILABLE_INSTITUTIONS[0]

    tournament = Tournament.query.filter_by(name='Inter-Department Sports Tournament 2025').first()
    if not tournament:
        tournament = Tournament(
            name='Inter-Department Sports Tournament 2025',
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() + timedelta(days=30),
            status='active',
            rules='Standard inter-department tournament rules apply.',
            created_by=admin.id,
            institution=admin.institution,
        )
        db.session.add(tournament)

    db.session.commit()


def get_default_tournament():
    """Get the default tournament."""
    return Tournament.query.filter_by(name='Inter-Department Sports Tournament 2025').first()


def ensure_schema_integrity():
    """Apply lightweight schema updates required for new fields."""

    inspector = inspect(db.engine)

    try:
        user_columns = {col['name'] for col in inspector.get_columns('users')}
    except Exception:
        return

    if 'phone_number' not in user_columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE users ADD COLUMN phone_number VARCHAR(20)'))

    try:
        notification_columns = {col['name'] for col in inspector.get_columns('notification')}
    except Exception:
        return

    if 'actor_id' not in notification_columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE notification ADD COLUMN actor_id INTEGER'))

    try:
        tournament_columns = {col['name'] for col in inspector.get_columns('tournament')}
    except Exception:
        return

    migrations: list[tuple[str, str]] = []

    if 'tournament_type' not in tournament_columns:
        migrations.append(('tournament', 'ALTER TABLE tournament ADD COLUMN tournament_type VARCHAR(20) DEFAULT "league"'))
    if 'location' not in tournament_columns:
        migrations.append(('tournament', 'ALTER TABLE tournament ADD COLUMN location VARCHAR(100)'))

    for table_name, ddl in migrations:
        with db.engine.begin() as connection:
            connection.execute(text(ddl))

    try:
        bracket_columns = inspector.get_columns('bracket')
    except Exception:
        bracket_columns = None

    if bracket_columns is None:
        with db.engine.begin() as connection:
            connection.execute(
                text(
                    '''CREATE TABLE IF NOT EXISTS bracket (
                        id INTEGER PRIMARY KEY,
                        tournament_id INTEGER UNIQUE NOT NULL,
                        format VARCHAR(20) DEFAULT 'league',
                        points_win INTEGER DEFAULT 3,
                        points_draw INTEGER DEFAULT 1,
                        points_loss INTEGER DEFAULT 0,
                        config_payload JSON,
                        created_at DATETIME,
                        updated_at DATETIME,
                        FOREIGN KEY(tournament_id) REFERENCES tournament(id)
                    )'''
                )
            )

    try:
        tournament_team_columns = {col['name'] for col in inspector.get_columns('tournament_team')}
    except Exception:
        return

    if 'stats_payload' not in tournament_team_columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE tournament_team ADD COLUMN stats_payload JSON'))

    try:
        match_columns = {col['name'] for col in inspector.get_columns('match')}
    except Exception:
        return

    if 'round_number' not in match_columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE match ADD COLUMN round_number INTEGER'))
    if 'stage' not in match_columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE match ADD COLUMN stage VARCHAR(50)'))
    if 'duration_minutes' not in match_columns:
        with db.engine.begin() as connection:
            connection.execute(text(f'ALTER TABLE match ADD COLUMN duration_minutes INTEGER DEFAULT {DEFAULT_MATCH_DURATION_MINUTES}'))
    if 'bracket_slot' not in match_columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE match ADD COLUMN bracket_slot VARCHAR(40)'))
    if 'team1_placeholder' not in match_columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE match ADD COLUMN team1_placeholder VARCHAR(100)'))
    if 'team2_placeholder' not in match_columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE match ADD COLUMN team2_placeholder VARCHAR(100)'))