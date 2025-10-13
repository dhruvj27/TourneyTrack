from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, time, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import pytz
import re

db = SQLAlchemy()

IST = pytz.timezone('Asia/Kolkata')

class User(db.Model):
    """Users who can log in - SMCs and Team Managers"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'smc' or 'team_manager'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))

    # Relationships
    tournaments_created = db.relationship('Tournament', backref='creator', lazy=True, foreign_keys='Tournament.created_by')
    teams_created = db.relationship('Team', backref='creator', lazy=True, foreign_keys='Team.created_by')

    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def validate_format(username, email, password, role):
        """
        Validate registration data format (NO database queries).
        Returns list of errors.
        Use this for tests that don't have app context.
        """
        errors = []
        
        # Username validation
        if not username or len(username.strip()) < 3:
            errors.append("Username must be at least 3 characters")
        
        if username and not username.replace('_', '').replace('-', '').isalnum():
            errors.append("Username can only contain letters, numbers, hyphens and underscores")
        
        # Email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not email or not re.match(email_pattern, email):
            errors.append("Valid email required")
        
        # Password validation
        if not password or len(password) < 8:
            errors.append("Password must be at least 8 characters")
        
        password_regex = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$"
        if password and not re.fullmatch(password_regex, password):
            errors.append("Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character")
        
        # Role validation
        if role not in ['smc', 'team_manager']:
            errors.append("Invalid role selected")
        
        return errors

    
class Tournament(db.Model):
    __tablename__ = 'tournament'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='upcoming')  # upcoming, active, completed
    rules = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    
    # Relationships 
    matches = db.relationship('Match', backref='tournament', lazy=True, foreign_keys='Match.tournament_id')
    tournament_teams = db.relationship('TournamentTeam', backref='tournament', lazy=True, cascade='all, delete-orphan')

    #def get_teams(self):
    """Get all teams in this tournament"""
        #return [tt.team for tt in self.tournament_teams]
    def get_teams(self):
        """Get all teams in this tournament (session-safe)"""
        return db.session.query(Team).join(
            TournamentTeam
        ).filter(
            TournamentTeam.tournament_id == self.id
        ).all()
    
    def get_active_teams(self):
        """Get active teams in this tournament"""
        return [tt.team for tt in self.tournament_teams if tt.status == 'active']


class TournamentTeam(db.Model):
    """Association table for many-to-many Tournament-Team relationship"""
    __tablename__ = 'tournament_team'
    
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    team_id = db.Column(db.String(20), db.ForeignKey('team.team_id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    status = db.Column(db.String(20), default='active')  # active, eliminated, champion
    points = db.Column(db.Integer, default=0)  # For league format
    
    # Ensure team can't join same tournament twice
    __table_args__ = (db.UniqueConstraint('tournament_id', 'team_id', name='unique_tournament_team'),)


class Team(db.Model):
    __tablename__ = 'team'
    
    id = db.Column(db.Integer, primary_key=True)  # Auto-increment PK
    team_id = db.Column(db.String(20), unique=True, nullable=False)  # Login ID
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50), nullable=False)
    manager_name = db.Column(db.String(100), nullable=False)
    manager_contact = db.Column(db.String(20))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_self_managed = db.Column(db.Boolean, default=False)  # True if created by team manager
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    
    # Relationships
    players = db.relationship('Player', backref='team', lazy=True, foreign_keys='Player.team_id')
    tournament_teams = db.relationship('TournamentTeam', backref='team', lazy=True)
    
    # Match relationships
    matches_as_team1 = db.relationship('Match', foreign_keys='Match.team1_id',
                                      primaryjoin='Team.team_id == Match.team1_id',
                                      backref='team1', lazy=True)
    matches_as_team2 = db.relationship('Match', foreign_keys='Match.team2_id',
                                      primaryjoin='Team.team_id == Match.team2_id', 
                                      backref='team2', lazy=True)
    matches_won = db.relationship('Match', foreign_keys='Match.winner_id',
                                 primaryjoin='Team.team_id == Match.winner_id',
                                 backref='winner', lazy=True)

    # def get_tournaments(self):
    """Get all tournaments this team is part of"""
        # return [tt.tournament for tt in self.tournament_teams]
    
    def get_tournaments(self):
        """Get all tournaments this team is in (session-safe)"""
        return db.session.query(Tournament).join(
            TournamentTeam
        ).filter(
            TournamentTeam.team_id == self.team_id
        ).all()
    
    def get_upcoming_matches(self, tournament_id=None):
        """Get upcoming matches for this team, optionally filtered by tournament"""
        query = Match.query.filter(
            db.or_(Match.team1_id == self.team_id, Match.team2_id == self.team_id),
            Match.status == 'scheduled',
            Match.date >= date.today()
        )
        if tournament_id:
            query = query.filter(Match.tournament_id == tournament_id)
        return query.order_by(Match.date, Match.time).all()
    
    def get_completed_matches(self, tournament_id=None):
        """Get completed matches for this team, optionally filtered by tournament"""
        query = Match.query.filter(
            db.or_(Match.team1_id == self.team_id, Match.team2_id == self.team_id),
            Match.status == 'completed'
        )
        if tournament_id:
            query = query.filter(Match.tournament_id == tournament_id)
        return query.order_by(Match.date.desc(), Match.time.desc()).all()
    
    def get_match_record(self, tournament_id=None):
        """Get win/loss/draw record, optionally filtered by tournament"""
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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    is_active = db.Column(db.Boolean, default=True)
    
    def update_player(self, **kwargs):
        """Update player profile with provided fields"""
        for field, value in kwargs.items():
            if hasattr(self, field) and value:
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
    winner_id = db.Column(db.String(20), db.ForeignKey('team.team_id'), nullable=True)
    status = db.Column(db.String(20), default='scheduled')  # scheduled, completed
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))

    @property
    def is_upcoming(self):
        """Check if match is upcoming"""
        return self.status == 'scheduled' and self.date >= date.today()
    
    @property
    def versus_display(self):
        """Display match as Team A vs Team B"""
        return f"{self.team1.name} vs {self.team2.name}"
    
    @property
    def score_display(self):
        """Display score in readable format"""
        if self.status != 'completed':
            return "Match not completed"
        return f"{self.team1.name}: {self.team1_score} | {self.team2.name}: {self.team2_score}"
    
    @property
    def result_display(self):
        """Display result summary"""
        if self.status != 'completed':
            return "Match not completed"
        
        if self.winner_id:
            return f"Winner: {self.winner.name}"
        else:
            return "Match drawn"
        
    def opponent_of(self, team_id):
        """Get opponent team for given team_id"""
        if self.team1_id == team_id:
            return self.team2
        elif self.team2_id == team_id:
            return self.team1
        return None


def init_default_data():
    """Initialize default data for the application"""
    
    # Create default SMC admin user
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', email='admin@tourneytrack.local', role='smc')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.flush()
    else:
        # Update existing admin with new fields
        if not admin.email:
            admin.email = 'admin@tourneytrack.local'
        if not admin.role:
            admin.role = 'smc'
    
    # Create default tournament
    tournament = Tournament.query.filter_by(name='Inter-Department Sports Tournament 2025').first()
    if not tournament:
        tournament = Tournament(
            name='Inter-Department Sports Tournament 2025',
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() + timedelta(days=30),
            status='active',
            rules='Standard inter-department tournament rules apply.',
            created_by=admin.id
        )
        db.session.add(tournament)
    
    db.session.commit()


def get_default_tournament():
    """Get the default tournament"""
    return Tournament.query.filter_by(name='Inter-Department Sports Tournament 2025').first()