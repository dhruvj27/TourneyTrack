import pytest
from app import app
from models import db, User, Tournament, Team, Player, Match, TournamentTeam
from datetime import date, time, timedelta


@pytest.fixture
def flask_app():
    """Create test application with in-memory SQLite database"""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    with app.app_context():
        db.create_all()
        # Initialize default data (creates default admin user and tournament)
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
def smc_user(flask_app):
    """Create a test SMC user (Stage 1 - new auth)"""
    with flask_app.app_context():
        user = User(
            username='test_smc',
            email='smc@test.com',
            role='smc',
            institution='Test University',
        )
        user.set_password('Test@123')
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    
    # Return a function that fetches the user in the current context
    def get_user():
        return User.query.get(user_id)
    
    # But also return the user directly for immediate use
    with flask_app.app_context():
        return User.query.get(user_id)


@pytest.fixture
def team_manager_user(flask_app):
    """Create a test team manager user (Stage 1 - new auth)"""
    with flask_app.app_context():
        user = User(
            username='test_manager',
            email='manager@test.com',
            role='team_manager',
            institution='Test University',
        )
        user.set_password('Manager@123')
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    
    with flask_app.app_context():
        return User.query.get(user_id)


@pytest.fixture
def tournament(flask_app, smc_user):
    """Create a test tournament (Stage 2 - requires created_by)"""
    with flask_app.app_context():
        tournament = Tournament(
            name='Test Tournament',
            start_date=date.today() - timedelta(days=5),
            end_date=date.today() + timedelta(days=30),
            status='active',
            rules='Test tournament rules',
            created_by=smc_user.id,
            institution=smc_user.institution,
        )
        db.session.add(tournament)
        db.session.commit()
        tournament_id = tournament.id
    
    with flask_app.app_context():
        return Tournament.query.get(tournament_id)


@pytest.fixture
def tournament2(flask_app, smc_user):
    """Create a second test tournament (Stage 2)"""
    with flask_app.app_context():
        tournament = Tournament(
            name='Test Tournament 2',
            start_date=date.today() - timedelta(days=5),
            end_date=date.today() + timedelta(days=30),
            status='active',
            rules='Test tournament 2 rules',
            created_by=smc_user.id,
            institution=smc_user.institution,
        )
        db.session.add(tournament)
        db.session.commit()
        tournament_id = tournament.id
    
    with flask_app.app_context():
        return Tournament.query.get(tournament_id)


@pytest.fixture
def team(flask_app, smc_user):
    """Create a test team (Stage 2 - no password, no tournament_id, has created_by)"""
    with flask_app.app_context():
        team = Team(
            team_id='TEST001',
            name='Test Team',
            department='CSE',
            manager_name='John Doe',
            manager_contact='9876543210',
            created_by=smc_user.id,
            institution=smc_user.institution,
        )
        db.session.add(team)
        db.session.commit()
        team_id = team.team_id
    
    with flask_app.app_context():
        return Team.query.filter_by(team_id=team_id).first()


@pytest.fixture
def team2(flask_app, smc_user):
    """Create a second test team (Stage 2 - no password, no tournament_id)"""
    with flask_app.app_context():
        team = Team(
            team_id='TEST002',
            name='Second Team',
            department='ECE',
            manager_name='Jane Doe',
            manager_contact='1234567890',
            created_by=smc_user.id,
            institution=smc_user.institution,
        )
        db.session.add(team)
        db.session.commit()
        team_id = team.team_id
    
    with flask_app.app_context():
        return Team.query.filter_by(team_id=team_id).first()

@pytest.fixture
def self_managed_team(flask_app, team_manager_user):
    """Create a test team created by team manager (Stage 3)"""
    with flask_app.app_context():
        # Get fresh team_manager_user in this context
        manager = User.query.get(team_manager_user.id)
        
        team = Team(
            team_id='TM0001',
            name='Self Managed Team',
            department='IT',
            manager_name='Self Manager',
            manager_contact='5555555555',
            created_by=manager.id,
            institution=manager.institution,
        )
        db.session.add(team)
        db.session.commit()
        team_id = team.team_id
    
    # Return fresh instance in new context
    with flask_app.app_context():
        return Team.query.filter_by(team_id=team_id).first()


@pytest.fixture
def player(flask_app, team):
    """Create a test player"""
    with flask_app.app_context():
        player = Player(
            name='Test Player',
            roll_number=12345,
            contact='9876543210',
            department='CSE',
            year='3',
            team_id=team.team_id
        )
        db.session.add(player)
        db.session.commit()
        player_id = player.id
    
    with flask_app.app_context():
        return Player.query.get(player_id)


@pytest.fixture
def match(flask_app, tournament, team, team2):
    """Create a test match"""
    with flask_app.app_context():
        match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() + timedelta(days=5),
            time=time(14, 0),
            venue='Main Field',
            status='scheduled'
        )
        db.session.add(match)
        db.session.commit()
        match_id = match.id
    
    with flask_app.app_context():
        return Match.query.get(match_id)


@pytest.fixture
def past_match(flask_app, tournament, team, team2):
    """Create a past match for testing result entry"""
    with flask_app.app_context():
        match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() - timedelta(days=1),
            time=time(14, 0),
            venue='Past Field',
            status='scheduled'
        )
        db.session.add(match)
        db.session.commit()
        match_id = match.id
    
    with flask_app.app_context():
        return Match.query.get(match_id)

@pytest.fixture
def past_tournament(flask_app, smc_user):
    """Create a completed/past tournament (Stage 3)"""
    with flask_app.app_context():
        tournament = Tournament(
            name='PastTest',
            start_date=date.today() - timedelta(days=60),
            end_date=date.today() - timedelta(days=30),
            status='completed',
            rules='Past tournament for testing',
                created_by=smc_user.id,
                institution=smc_user.institution,
        )
        db.session.add(tournament)
        db.session.commit()
        tournament_id = tournament.id
    
    with flask_app.app_context():
        return Tournament.query.get(tournament_id)


@pytest.fixture
def future_tournament(flask_app, smc_user):
    """Create an upcoming/future tournament (Stage 3)"""
    with flask_app.app_context():
        tournament = Tournament(
            name='FutureTest',
            start_date=date.today() + timedelta(days=30),
            end_date=date.today() + timedelta(days=60),
            status='upcoming',
            rules='Future tournament for testing',
                created_by=smc_user.id,
                institution=smc_user.institution,
        )
        db.session.add(tournament)
        db.session.commit()
        tournament_id = tournament.id
    
    with flask_app.app_context():
        return Tournament.query.get(tournament_id)
        
@pytest.fixture
def authenticated_smc(client, smc_user):
    """Login as SMC via new auth blueprint and return authenticated client"""
    with client.session_transaction() as sess:
        sess['user_id'] = smc_user.id
        sess['username'] = smc_user.username
        sess['role'] = 'smc'
    return client


@pytest.fixture
def authenticated_team_manager(client, team_manager_user):
    """Login as team manager via new auth blueprint and return authenticated client"""
    with client.session_transaction() as sess:
        sess['user_id'] = team_manager_user.id
        sess['username'] = team_manager_user.username
        sess['role'] = 'team_manager'
    return client