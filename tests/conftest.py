import pytest
from app import app
from models import db, User, Tournament, Team, Player, Match
from datetime import date, time, timedelta


@pytest.fixture
def flask_app():
    """Create test application with in-memory SQLite database"""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.app_context():
        db.create_all()
        # Initialize default data
        from models import init_default_data
        init_default_data()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(flask_app):
    """Test client"""
    return flask_app.test_client()


@pytest.fixture
def db_session(flask_app):
    """Database session for test fixtures"""
    return db.session


@pytest.fixture
def tournament(db_session):
    """Create a test tournament"""
    tournament = Tournament(
        name='Test Tournament 2025',
        start_date=date.today() - timedelta(days=5),
        end_date=date.today() + timedelta(days=30),
        status='active',
        rules='Test tournament rules'
    )
    db_session.add(tournament)
    db_session.commit()
    return tournament


@pytest.fixture
def team(db_session, tournament):
    """Create a test team"""
    team = Team(
        team_id='TEST001',
        name='Test Team',
        department='CSE',
        manager_name='John Doe',
        manager_contact='9876543210',
        tournament_id=tournament.id
    )
    team.set_password('team_password')
    db_session.add(team)
    db_session.commit()
    return team


@pytest.fixture
def team2(db_session, tournament):
    """Create a second test team"""
    team = Team(
        team_id='TEST002',
        name='Second Team',
        department='ECE',
        manager_name='Jane Doe',
        manager_contact='1234567890',
        tournament_id=tournament.id
    )
    team.set_password('team2_password')
    db_session.add(team)
    db_session.commit()
    return team


@pytest.fixture
def player(db_session, team):
    """Create a test player"""
    player = Player(
        name='Test Player',
        roll_number=12345,
        contact='9876543210',
        department='CSE',
        year='3',
        team_id=team.team_id
    )
    db_session.add(player)
    db_session.commit()
    return player


@pytest.fixture
def match(db_session, tournament, team, team2):
    """Create a test match"""
    match = Match(
        tournament_id=tournament.id,
        team1_id=team.team_id,
        team2_id=team2.team_id,
        date=date.today() + timedelta(days=5),
        time=time(14, 0),
        venue='Main Field',
        status='scheduled'
    )
    db_session.add(match)
    db_session.commit()
    return match


@pytest.fixture
def past_match(db_session, tournament, team, team2):
    """Create a past match for testing result entry"""
    match = Match(
        tournament_id=tournament.id,
        team1_id=team.team_id,
        team2_id=team2.team_id,
        date=date.today() - timedelta(days=1),
        time=time(14, 0),
        venue='Past Field',
        status='scheduled'
    )
    db_session.add(match)
    db_session.commit()
    return match