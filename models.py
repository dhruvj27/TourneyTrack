from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import pytz

db = SQLAlchemy()

IST = pytz.timezone('Asia/Kolkata')

class User(db.Model):
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # SMC or TEAM_MANAGER
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))

    # Relationships
    managed_teams = db.relationship('Team', backref='manager', lazy=True)
    created_tournaments = db.relationship('Tournament', backref='creator', lazy=True)

class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    sport = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='UPCOMING')  # UPCOMING, ACTIVE, COMPLETED
    rules = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    
    # Relationships
    teams = db.relationship('Team', backref='tournament', lazy=True)
    matches = db.relationship('Match', backref='tournament', lazy=True)

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50), nullable=False)
    manager_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=True)
    registration_status = db.Column(db.String(20), default='PENDING')  # PENDING, APPROVED, REJECTED
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    
    # Relationships
    players = db.relationship('Player', backref='team', lazy=True)

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    contact = db.Column(db.String(15))
    department = db.Column(db.String(50))
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    team1_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    team2_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    match_date = db.Column(db.DateTime, nullable=False)
    venue = db.Column(db.String(100), nullable=False)
    team1_score = db.Column(db.Integer, default=0)
    team2_score = db.Column(db.Integer, default=0)
    winner_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    status = db.Column(db.String(20), default='SCHEDULED')  # SCHEDULED, COMPLETED
    created_at = db.Column(db.DateTime, lambda: datetime.now(IST))
    
    # Relationships
    team1 = db.relationship('Team', foreign_keys=[team1_id], backref='home_matches')
    team2 = db.relationship('Team', foreign_keys=[team2_id], backref='away_matches')
    winner = db.relationship('Team', foreign_keys=[winner_id], backref='won_matches')
