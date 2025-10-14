'''Legacy Stage 1 tests retained as historical reference. They are now disabled.


    response = client.get('/register-team')
        assert response.status_code == 302

    def test_register_team_page_loads(self, client):
        """Test team registration form loads"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.get('/register-team')
        assert response.status_code == 200

    def test_register_team_success(self, client, tournament):
        """Test successful team registration"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.post('/register-team', data={
            'team_name': 'New Team',
            'team_id': 'NT001',
            'department': 'CSE',
            'manager_name': 'Manager Name',
            'manager_contact': '9876543210',
            'password': 'Team@123'
        })
        
        assert response.status_code == 302
        
        new_team = Team.query.filter_by(team_id='NT001').first()
        assert new_team is not None
        assert new_team.name == 'New Team'

    def test_register_team_with_players(self, client, tournament):
        """Test team registration with players"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.post('/register-team', data={
            'team_name': 'Team With Players',
            'team_id': 'TWP001',
            'department': 'CSE',
            'manager_name': 'Manager',
            'manager_contact': '9876543210',
            'password': 'Team@123',
            'player_1_name': 'Player 1',
            'player_1_roll': '101',
            'player_1_dept': 'CSE',
            'player_1_year': '3',
            'player_1_contact': '1234567890',
            'player_2_name': 'Player 2',
            'player_2_roll': '102',
            'player_2_dept': 'CSE',
            'player_2_year': '3',
            'player_2_contact': '1234567891'
        })
        
        assert response.status_code == 302
        
        new_team = Team.query.filter_by(team_id='TWP001').first()
        assert new_team is not None
        assert len(new_team.players) == 2

    def test_register_team_duplicate_team_id(self, client, tournament, team):
        """Test cannot register team with existing team_id"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.post('/register-team', data={
            'team_name': 'Different Team',
            'team_id': team.team_id,
            'department': 'ECE',
            'manager_name': 'Different Manager',
            'password': 'team_pass'
        }, follow_redirects=True)
        
        assert b'already exists' in response.data.lower()

    def test_register_team_duplicate_name(self, client, tournament, team):
        """Test cannot register team with duplicate name in same tournament"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.post('/register-team', data={
            'team_name': team.name,
            'team_id': 'DIFF001',
            'department': 'ECE',
            'manager_name': 'Manager',
            'manager_contact': '1234567890',
            'password': 'team_pass'
        }, follow_redirects=True)
        
        # Check that the user is still on the form or sees error message
        assert response.status_code == 200

    def test_register_team_missing_required_fields(self, client, tournament):
        """Test team registration validation for missing fields"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.post('/register-team', data={
            'team_name': 'Incomplete Team',
            'department': 'CSE',
            'manager_name': 'Manager',
            'password': 'team_pass'
        }, follow_redirects=True)
        
        assert b'required' in response.data.lower()


class TestScheduleMatchesRoute:
    """Test match scheduling route"""

    def test_schedule_matches_requires_login(self, client):
        """Test match scheduling requires SMC login"""
        response = client.get('/schedule-matches')
        assert response.status_code == 302

    def test_schedule_matches_requires_smc_role(self, client, team):
        """Test schedule matches rejects team login"""
        client.post('/login-team', data={
            'team_id': team.team_id,
            'password': 'Team@123'
        })
        
        response = client.get('/schedule-matches')
        assert response.status_code == 302

    def test_schedule_matches_page_loads(self, client):
        """Test schedule matches form loads"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.get('/schedule-matches')
        assert response.status_code == 200

    def test_schedule_match_success(self, client, tournament, team, team2):
        """Test successful match scheduling"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.post('/schedule-matches', data={
            'team1_id': team.id,
            'team2_id': team2.id,
            'date': '2025-10-20',
            'time': '14:00',
            'venue': 'Main Field'
        })
        
        assert response.status_code == 302
        
        match = Match.query.filter_by(venue='Main Field').first()
        assert match is not None

    def test_schedule_match_team_cannot_play_itself(self, client, tournament, team):
        """Test cannot schedule team against itself"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.post('/schedule-matches', data={
            'team1_id': team.id,
            'team2_id': team.id,
            'date': '2025-12-20',
            'time': '14:00',
            'venue': 'Main Field'
        }, follow_redirects=True)
        
        assert b'cannot play against itself' in response.data.lower()

    def test_schedule_match_venue_conflict(self, client, tournament, team, team2):
        """Test cannot schedule matches with venue conflict"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        team3 = Team(
            team_id='T003',
            name='Team 3',
            department='MECH',
            manager_name='Manager 3',
            tournament_id=tournament.id
        )
        team3.set_password('pass3')
        db.session.add(team3)
        db.session.commit()
        
        client.post('/schedule-matches', data={
            'team1_id': team.id,
            'team2_id': team2.id,
            'date': '2025-10-20',
            'time': '14:00',
            'venue': 'Main Field'
        })
        
        response = client.post('/schedule-matches', data={
            'team1_id': team2.id,
            'team2_id': team3.id,
            'date': '2025-10-20',
            'time': '14:00',
            'venue': 'Main Field'
        }, follow_redirects=True)
        
        assert b'already booked' in response.data.lower()

    def test_schedule_match_team_conflict(self, client, tournament, team, team2):
        """Test cannot schedule team in two matches at same time"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        team3 = Team(
            team_id='T003',
            name='Team 3',
            department='MECH',
            manager_name='Manager 3',
            tournament_id=tournament.id
        )
        team3.set_password('pass3')
        db.session.add(team3)
        db.session.commit()
        
        client.post('/schedule-matches', data={
            'team1_id': team.id,
            'team2_id': team2.id,
            'date': '2025-10-20',
            'time': '14:00',
            'venue': 'Field 1'
        })
        
        response = client.post('/schedule-matches', data={
            'team1_id': team.id,
            'team2_id': team3.id,
            'date': '2025-10-20',
            'time': '14:00',
            'venue': 'Field 2'
        }, follow_redirects=True)
        
        assert b'already has a match' in response.data.lower()

    def test_schedule_match_outside_tournament_dates(self, client, tournament, team, team2):
        """Test cannot schedule match outside tournament dates"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.post('/schedule-matches', data={
            'team1_id': team.id,
            'team2_id': team2.id,
            'date': '2025-01-01',
            'time': '14:00',
            'venue': 'Main Field'
        }, follow_redirects=True)
        
        assert b'must be between' in response.data.lower()


class TestAddResultsRoute:
    """Test result entry route"""

    def test_add_results_requires_login(self, client):
        """Test result entry requires SMC login"""
        response = client.get('/add-results')
        assert response.status_code == 302

    def test_add_results_requires_smc_role(self, client, team):
        """Test add results rejects team login"""
        client.post('/login-team', data={
            'team_id': team.team_id,
            'password': 'Team@123'
        })
        
        response = client.get('/add-results')
        assert response.status_code == 302

    def test_add_results_page_loads(self, client):
        """Test add results form loads"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.get('/add-results')
        assert response.status_code == 200

    def test_add_result_success(self, client, past_match):
        """Test successful result entry"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.post('/add-results', data={
            'match_id': past_match.id,
            'team1_score': '5',
            'team2_score': '3',
            'winner_id': past_match.team1_id
        })
        
        assert response.status_code == 302

        updated_match = Match.query.get(past_match.id)
        assert updated_match.status == 'completed'
        assert updated_match.team1_score == '5'
        assert updated_match.team2_score == '3'
        assert updated_match.winner_id == past_match.team1_id

    def test_add_result_draw(self, client, past_match):
        """Test entering result without winner (draw)"""
        
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.post('/add-results', data={
            'match_id': past_match.id,
            'team1_score': '2',
            'team2_score': '2',
            'winner_id': ''
        })
        
        assert response.status_code == 302

        updated_match = Match.query.get(past_match.id)
        assert updated_match.status == 'completed'
        assert updated_match.winner_id is None

    def test_add_result_already_completed(self, client, match):
        """Test cannot enter results for already completed match"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        match.status = 'completed'
        match.team1_score = '5'
        match.team2_score = '3'
        db.session.commit()
        
        response = client.post('/add-results', data={
            'match_id': match.id,
            'team1_score': '6',
            'team2_score': '4',
            'winner_id': match.team1_id
        }, follow_redirects=True)
        
        assert b'already been entered' in response.data.lower()

    def test_add_result_invalid_winner(self, client, past_match):
        """Test cannot add result with invalid winner"""
        
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.post('/add-results', data={
            'match_id': past_match.id,
            'team1_score': '5',
            'team2_score': '3',
            'winner_id': 'INVALID_TEAM'
        }, follow_redirects=True)
        
        assert b'must be one of the participating teams' in response.data.lower()


class TestTeamDashboard:
    """Test team dashboard route"""

    def test_team_dashboard_requires_login(self, client):
        """Test team dashboard is protected"""
        response = client.get('/team-dashboard')
        assert response.status_code == 302

    def test_team_dashboard_requires_team_role(self, client):
        """Test team dashboard rejects SMC login"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.get('/team-dashboard')
        assert response.status_code == 302

    def test_team_dashboard_shows_team_info(self, client, team):
        """Test team dashboard shows team information"""
        client.post('/login-team', data={
            'team_id': team.team_id,
            'password': 'Team@123'
        })
        
        response = client.get('/team-dashboard')
        assert response.status_code == 200

    def test_team_dashboard_shows_fixtures(self, client, team, team2, tournament):
        """Test team dashboard shows upcoming matches"""
        future_match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() + timedelta(days=5),
            time=time(14, 0),
            venue='Field',
            status='scheduled'
        )
        db.session.add(future_match)
        db.session.commit()
        
        client.post('/login-team', data={
            'team_id': team.team_id,
            'password': 'Team@123'
        })
        
        response = client.get('/team-dashboard')
        assert response.status_code == 200

    def test_team_dashboard_shows_results(self, client, team, team2, tournament):
        """Test team dashboard shows completed matches"""
        completed_match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() - timedelta(days=5),
            time=time(14, 0),
            venue='Field',
            status='completed',
            winner_id=team.team_id,
            team1_score='5',
            team2_score='3'
        )
        db.session.add(completed_match)
        db.session.commit()
        
        client.post('/login-team', data={
            'team_id': team.team_id,
            'password': 'Team@123'
        })
        
        response = client.get('/team-dashboard')
        assert response.status_code == 200


class TestUpdateProfileRoute:
    """Test team profile update route"""

    def test_update_profile_requires_login(self, client):
        """Test profile update requires team login"""
        response = client.get('/update-profile')
        assert response.status_code == 302

    def test_update_profile_requires_team_role(self, client):
        """Test profile update rejects SMC login"""
        client.post('/login-smc', data={
            'username': 'admin',
            'password': 'admin123'
        })
        
        response = client.get('/update-profile')
        assert response.status_code == 302

    def test_update_profile_page_loads(self, client, team):
        """Test profile update form loads"""
        client.post('/login-team', data={
            'team_id': team.team_id,
            'password': 'Team@123'
        })
        
        response = client.get('/update-profile')
        assert response.status_code == 200

    def test_update_team_details(self, client, team):
        """Test updating team details"""
        client.post('/login-team', data={
            'team_id': team.team_id,
            'password': 'Team@123'
        })
        
        response = client.post('/update-profile', data={
            'action': 'update_team',
            'manager_name': 'New Manager Name',
            'manager_contact': '1111111111'
        })
        
        assert response.status_code == 302
        
        updated_team = Team.query.filter_by(team_id=team.team_id).first()
        assert updated_team.manager_name == 'New Manager Name'
        assert updated_team.manager_contact == '1111111111'

    def test_add_player_to_team(self, client, team):
        """Test adding player to team"""
        client.post('/login-team', data={
            'team_id': team.team_id,
            'password': 'Team@123'
        })
        
        response = client.post('/update-profile', data={
            'action': 'add_player',
            'new_player_name': 'New Player',
            'new_player_roll': '999',
            'new_player_contact': '9999999999'
        })
        
        assert response.status_code == 302
        
        player = Player.query.filter_by(name='New Player').first()
        assert player is not None
        assert player.team_id == team.team_id

    def test_update_existing_player(self, client, team, player):
        """Test updating existing player details"""
        client.post('/login-team', data={
            'team_id': team.team_id,
            'password': 'Team@123'
        })
        
        response = client.post('/update-profile', data={
            'action': 'update_players',
            f'player_{player.id}_name': 'Updated Player Name',
            f'player_{player.id}_contact': '5555555555'
        })
        
        assert response.status_code == 302
        
        updated_player = Player.query.get(player.id)
        assert updated_player.name == 'Updated Player Name'
        assert updated_player.contact == '5555555555'

    def test_remove_player_from_team(self, client, team, player):
        """Test removing player from team"""
        client.post('/login-team', data={
            'team_id': team.team_id,
            'password': 'Team@123'
        })
        
        response = client.post('/update-profile', data={
            'action': 'remove_player',
            'player_id': player.id
        })
        
        assert response.status_code == 302
        
        removed_player = Player.query.get(player.id)
        assert removed_player.is_active is False


class TestPublicViewRoute:
    """Test public fixtures and results view"""

    def test_public_view_loads(self, client):
        """Test public view page loads without authentication"""
    response = client.get('/public-view')
    assert response.status_code == 200

    def test_public_view_shows_upcoming_fixtures(self, client, tournament, team, team2):
        """Test public view shows upcoming fixtures"""
        match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() + timedelta(days=5),
            time=time(14, 0),
            venue='Field',
            status='scheduled'
        )
        db.session.add(match)
        db.session.commit()
        
        response = client.get('/public-view')
        assert response.status_code == 200

    def test_public_view_shows_completed_results(self, client, tournament, team, team2):
        """Test public view shows recent results"""
        match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() - timedelta(days=1),
            time=time(14, 0),
            venue='Field',
            status='completed',
            winner_id=team.team_id,
            team1_score='5',
            team2_score='3'
        )
        db.session.add(match)
        db.session.commit()
        
        response = client.get('/public-view')
        assert response.status_code == 200

    def test_public_view_empty_state(self, client):
        """Test public view with no matches"""
        response = client.get('/public-view')
        assert response.status_code == 200
'''

from models import Team, TournamentTeam, get_default_tournament


def test_index_page_shows_default_tournament_name(client):
    """Legacy home page should render default tournament summary."""
    response = client.get('/')
    assert response.status_code == 200
    assert b'Welcome to' in response.data
    assert b'Inter-Department Sports Tournament 2025' in response.data
    assert b'Total Teams' in response.data


def test_legacy_smc_login_sets_session(client):
    """Old /login-smc route should still authenticate SMC via admin user."""
    response = client.post('/login-smc', data={
        'username': 'admin',
        'password': 'admin123',
    })

    assert response.status_code == 302
    assert '/smc-dashboard' in response.headers.get('Location', '')

    with client.session_transaction() as sess:
        assert sess.get('user_type') == 'smc'
        assert sess.get('username') == 'admin'


def test_legacy_team_login_redirects_to_new_auth(client):
    """Deprecated team login should redirect to modern auth flow."""
    response = client.get('/login-team')
    assert response.status_code == 302
    assert '/auth/login' in response.headers.get('Location', '')


def test_register_team_requires_smc_session(client):
    """Register team route should enforce SMC authentication."""
    response = client.get('/register-team')
    assert response.status_code == 302
    assert '/login-smc' in response.headers.get('Location', '')


def test_register_team_creates_team_and_enrols_in_default_tournament(authenticated_smc, flask_app):
    """Back-compat registration should create team and tournament link."""
    payload = {
        'team_name': 'Legacy Lions',
        'team_id': 'LEGACY01',
        'department': 'CSE',
        'manager_name': 'Legacy Manager',
        'manager_contact': '9876543210',
    }

    response = authenticated_smc.post('/register-team', data=payload)
    assert response.status_code == 302
    assert '/smc-dashboard' in response.headers.get('Location', '')

    with flask_app.app_context():
        team = Team.query.filter_by(team_id='LEGACY01').first()
        assert team is not None
        default_tournament = get_default_tournament()
        assert default_tournament is not None
        association = TournamentTeam.query.filter_by(team_id='LEGACY01').first()
        assert association is not None
        assert association.tournament_id == default_tournament.id


def test_logout_clears_legacy_session(client):
    """Legacy logout route should wipe session and redirect home."""
    with client.session_transaction() as sess:
        sess['user_type'] = 'smc'
        sess['username'] = 'admin'
        sess['role'] = 'smc'

    response = client.get('/logout')
    assert response.status_code == 302
    assert response.headers.get('Location', '').endswith('/')

    with client.session_transaction() as sess:
        # Flask keeps a session container object; ensure legacy keys are gone.
        assert 'user_type' not in sess
        assert 'username' not in sess
        assert 'role' not in sess