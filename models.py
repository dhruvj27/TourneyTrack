from datetime import datetime, date, time, timedelta
import re
import pytz

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from sqlalchemy.orm import validates
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

IST = pytz.timezone('Asia/Kolkata')
AVAILABLE_INSTITUTIONS = (
    'General Institution',
    'Tech University',
    'Commerce College',
)


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
        'Notification', backref='user', lazy=True, cascade='all, delete-orphan'
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
        commit: bool = False,
    ):
        """Create an in-app notification entry."""
        note = Notification(
            user_id=self.id,
            message=message,
            category=category,
            kind=kind,
            status=status,
            context_type=context_type,
            context_ref=context_ref,
            link_target=link_target,
        )
        db.session.add(note)
        if commit:
            db.session.commit()
        return note

    @staticmethod
    def validate_format(username: str, email: str, password: str, role: str) -> list[str]:
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

    def __repr__(self):  # pragma: no cover - debug helper
        return f"<Notification {self.id} user={self.user_id} status={self.status}>"

    def activate(self):
        self.status = 'active'
        self.is_read = False

    def resolve(self):
        self.status = 'resolved'
        self.is_read = True

    @classmethod
    def active_for_user(cls, user_id: int):
        query = cls.query.filter_by(user_id=user_id).filter(cls.status == 'active')
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
    created_at = db.Column(db.DateTime, default=current_time)

    matches = db.relationship('Match', backref='tournament', lazy=True, foreign_keys='Match.tournament_id')
    tournament_teams = db.relationship(
        'TournamentTeam', backref='tournament', lazy=True, cascade='all, delete-orphan'
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
            team.manager.notify(
                f'{team.name} was added to tournament {self.name}.',
                category='success',
                link_target=f'/team/team/{team.team_id}',
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

    def __repr__(self):  # pragma: no cover - debug helper
        return f"<Team {self.team_id} {self.name}>"

    @property
    def is_self_managed(self) -> bool:
        return self.created_by == self.managed_by

    def assign_manager(self, user):
        self.managed_by = user.id
        if getattr(user, 'role', None) == 'team_manager':
            user.notify(
                f'You are now managing team {self.name}.',
                category='info',
                kind='team_assignment',
                status='active',
                link_target=f'/team/team/{self.team_id}',
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
    team1_id = db.Column(db.String(20), db.ForeignKey('team.team_id'), nullable=False)
    team2_id = db.Column(db.String(20), db.ForeignKey('team.team_id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    venue = db.Column(db.String(100), nullable=False)
    team1_score = db.Column(db.String(100))
    team2_score = db.Column(db.String(100))
    winner_id = db.Column(db.String(20), db.ForeignKey('team.team_id'))
    status = db.Column(db.String(20), default='scheduled')
    created_at = db.Column(db.DateTime, default=current_time)

    @property
    def is_upcoming(self):
        """Check if match is upcoming"""
        return self.status == 'scheduled' and self.date >= date.today()
    
    @property
    def versus_display(self):
        """Display match as Team A vs Team B"""
        return f"{self.team1.name} vs {self.team2.name}"
    
    @property
    def score_display(self) -> str:
        if self.status != 'completed':
            return "Match not completed"
        return f"{self.team1.name}: {self.team1_score} | {self.team2.name}: {self.team2_score}"

    @property
    def result_display(self) -> str:
        if self.status != 'completed':
            return "Match not completed"
        if self.winner_id:
            return f"Winner: {self.winner.name}"
        return "Match drawn"

    def opponent_of(self, team_id):
        if self.team1_id == team_id:
            return self.team2
        if self.team2_id == team_id:
            return self.team1
        return None


def init_default_data():
    """Initialize default data for the application."""

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