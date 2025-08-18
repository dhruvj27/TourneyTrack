from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, time, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import pytz

db = SQLAlchemy()

IST = pytz.timezone('Asia/Kolkata')

class User(db.Model):
    username = db.Column(db.String(80), unique=True, nullable=False, primary_key=True)
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
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='UPCOMING')  # UPCOMING, ACTIVE, COMPLETED
    rules = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    
    # Relationships
    teams = db.relationship('Team', backref='tournament', lazy=True)
    matches = db.relationship('Match', backref='tournament', lazy=True)

class Team(db.Model):
    team_id = db.Column(db.Integer, primary_key=True)
    password_hash = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50), nullable=False)
#    manager_id = db.Column(db.Integer, db.ForeignKey('user.username'), nullable=False)
    manager_name =  db.Column(db.String(100), nullable=False)
    manager_contact = db.Column(db.String(20))
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    
    # Relationships
    players = db.relationship('Player', backref='team', lazy=True)

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
    team1_score = db.Column(db.Integer, default=0)
    team2_score = db.Column(db.Integer, default=0)
    winner_id = db.Column(db.Integer, db.ForeignKey('team.team_id'), nullable=True)
    status = db.Column(db.String(20), default='SCHEDULED')  # SCHEDULED, COMPLETED
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    
    # Relationships
    team1 = db.relationship('Team', foreign_keys=[team1_id], backref='home_matches')
    team2 = db.relationship('Team', foreign_keys=[team2_id], backref='away_matches')
    winner = db.relationship('Team', foreign_keys=[winner_id], backref='won_matches')

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