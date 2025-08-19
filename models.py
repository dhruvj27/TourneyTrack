from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, time, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import pytz

db = SQLAlchemy()

IST = pytz.timezone('Asia/Kolkata')

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # Auto-increment PK
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # SMC or TEAM_MANAGER
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='upcoming')  # upcoming, active, completed
    rules = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    
    # Relationships 
    teams = db.relationship('Team', backref='tournament', lazy=True,
                          foreign_keys='Team.tournament_id')
    matches = db.relationship('Match', backref='tournament', lazy=True,
                            foreign_keys='Match.tournament_id')

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # Auto-increment PK
    team_id = db.Column(db.String(20), unique=True, nullable=False)  # Login ID
    password_hash = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50), nullable=False)
#    manager_id = db.Column(db.Integer, db.ForeignKey('user.username'), nullable=False)
    manager_name =  db.Column(db.String(100), nullable=False)
    manager_contact = db.Column(db.String(20))
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    
    # Relationships
    players = db.relationship('Player', backref='team', lazy=True,
                            foreign_keys='Player.team_id')
    
    # Match relationships with backrefs (creates team1, team2, winner in Match)
    matches_as_team1 = db.relationship('Match', foreign_keys='Match.team1_id',
                                      primaryjoin='Team.team_id == Match.team1_id',
                                      backref='team1', lazy=True)
    matches_as_team2 = db.relationship('Match', foreign_keys='Match.team2_id',
                                      primaryjoin='Team.team_id == Match.team2_id', 
                                      backref='team2', lazy=True)
    matches_won = db.relationship('Match', foreign_keys='Match.winner_id',
                                 primaryjoin='Team.team_id == Match.winner_id',
                                 backref='winner', lazy=True)


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(20), unique = True, nullable = False)
    contact = db.Column(db.String(15))
    department = db.Column(db.String(50))
    year = db.Column(db.String(10))
    team_id = db.Column(db.Integer, db.ForeignKey('team.team_id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    is_active = db.Column(db.Boolean, default=True)

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    team1_id = db.Column(db.Integer, db.ForeignKey('team.team_id'), nullable=False)
    team2_id = db.Column(db.Integer, db.ForeignKey('team.team_id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    venue = db.Column(db.String(100), nullable=False)

    team1_score = db.Column(db.String(100))
    team2_score = db.Column(db.String(100))

    winner_id = db.Column(db.Integer, db.ForeignKey('team.team_id'), nullable=True)
    
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
    
# Utility functions for database operations
def init_default_data():
    """Initialize default data for the application"""
    
    # Create default SMC admin user
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', role='smc')
        admin.set_password('admin123')
        db.session.add(admin)
    
    # Create default tournament
    tournament = Tournament.query.filter_by(name='Inter-Department Sports Tournament 2025').first()
    if not tournament:
        tournament = Tournament(
            name='Inter-Department Sports Tournament 2025',
            start_date=datetime(2025, 9, 1).date(),
            end_date=datetime(2025, 9, 30).date(),
            status='active',
            rules='Standard inter-department tournament rules apply.'
        )
        db.session.add(tournament)
    
    db.session.commit()
    return tournament.id  # Return default tournament ID

def get_default_tournament():
    """Get the default tournament"""
    return Tournament.query.filter_by(name='Inter-Department Sports Tournament 2025').first()