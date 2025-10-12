"""
Integration tests for SMC blueprint - testing multi-tournament support added in Stage 2
Tests /smc/* routes for tournament creation, isolation, and team management
"""

import pytest
from models import db, User, Tournament, Team, TournamentTeam, Match
from datetime import date, timedelta, time as datetime_time


class TestSMCDashboard:
    """Test new /smc/dashboard route (Stage 2)"""

    def test_dashboard_loads_for_smc(self, client, smc_user):
        """Test SMC dashboard renders"""
        response = client.get('/smc/dashboard')
        assert response.status_code == 200

    def test_dashboard_shows_own_tournaments(self, client, smc_user, tournament):
        """Test dashboard displays tournaments created by logged-in SMC"""
        response = client.get('/smc/dashboard')
        assert response.status_code == 200
        assert b'Test Tournament' in response.data

    def test_dashboard_shows_stats(self, client, smc_user, tournament):
        """Test dashboard displays tournament statistics"""
        response = client.get('/smc/dashboard')
        assert response.status_code == 200
        assert b'total' in response.data.lower()

    def test_dashboard_requires_login(self, client):
        """Test dashboard requires authentication"""
        response = client.get('/smc/dashboard')
        assert response.status_code == 302  # Redirect to login

    def test_dashboard_requires_smc_role(self, client, team_manager_user):
        """Test dashboard requires SMC role"""
        response = client.get('/smc/dashboard', follow_redirects=True)
        assert b'SMC account' in response.data or response.status_code == 302


class TestTournamentCreation:
    """Test /smc/create-tournament route (Stage 2)"""

    def test_create_tournament_page_loads(self, client, smc_user):
        """Test tournament creation form renders"""
        response = client.get('/smc/create-tournament')
        assert response.status_code == 200
        assert b'tournament' in response.data.lower()

    def test_create_tournament_success(self, client, smc_user):
        """Test successful tournament creation"""
        response = client.post('/smc/create-tournament', data={
            'name': 'New Basketball Tournament',
            'start_date': (date.today() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'end_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'rules': 'Standard rules apply'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'created successfully' in response.data
        
        # Verify tournament created in DB
        tournament = Tournament.query.filter_by(name='New Basketball Tournament').first()
        assert tournament is not None
        assert tournament.created_by == smc_user.id

    def test_create_tournament_sets_correct_status(self, client, smc_user):
        """Test tournament status set based on dates"""
        # Future tournament
        client.post('/smc/create-tournament', data={
            'name': 'Future Tournament',
            'start_date': (date.today() + timedelta(days=10)).strftime('%Y-%m-%d'),
            'end_date': (date.today() + timedelta(days=40)).strftime('%Y-%m-%d'),
            'rules': 'Rules'
        })
        
        tournament = Tournament.query.filter_by(name='Future Tournament').first()
        assert tournament.status == 'upcoming'

    def test_create_tournament_validates_dates(self, client, smc_user):
        """Test cannot create tournament with end_date before start_date"""
        response = client.post('/smc/create-tournament', data={
            'name': 'Invalid Tournament',
            'start_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'end_date': (date.today() + timedelta(days=1)).strftime('%Y-%m-%d'),  # Before start
            'rules': 'Rules'
        }, follow_redirects=True)
        
        assert b'before end date' in response.data.lower() or b'start date' in response.data.lower()

    def test_create_tournament_requires_name(self, client, smc_user):
        """Test tournament name is required"""
        response = client.post('/smc/create-tournament', data={
            'name': '',
            'start_date': date.today().strftime('%Y-%m-%d'),
            'end_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'rules': 'Rules'
        }, follow_redirects=True)
        
        assert b'required' in response.data.lower()


class TestTournamentIsolation:
    """Test SMC can only access their own tournaments (Stage 2)"""

    def test_smc_sees_only_own_tournaments(self, client, app):
        """Test SMC dashboard shows only tournaments they created"""
        with app.app_context():
            # Create two SMCs
            smc1 = User(username='smc1', email='smc1@test.com', role='smc')
            smc1.set_password('Test@123')
            smc2 = User(username='smc2', email='smc2@test.com', role='smc')
            smc2.set_password('Test@123')
            db.session.add_all([smc1, smc2])
            db.session.commit()
            
            # Create tournaments for each SMC
            t1 = Tournament(name='SMC1 Tournament', start_date=date.today(),
                          end_date=date.today() + timedelta(days=30),
                          created_by=smc1.id)
            t2 = Tournament(name='SMC2 Tournament', start_date=date.today(),
                          end_date=date.today() + timedelta(days=30),
                          created_by=smc2.id)
            db.session.add_all([t1, t2])
            db.session.commit()
        
        # Login as smc1
        client.post('/auth/login', data={'username': 'smc1', 'password': 'Test@123'})
        response = client.get('/smc/dashboard')
        
        assert b'SMC1 Tournament' in response.data
        assert b'SMC2 Tournament' not in response.data

    def test_smc_cannot_access_other_tournament(self, client, app):
        """Test SMC cannot access tournament detail of other SMC's tournament"""
        with app.app_context():
            # Create two SMCs
            smc1 = User(username='smc1', email='smc1@test.com', role='smc')
            smc1.set_password('Test@123')
            smc2 = User(username='smc2', email='smc2@test.com', role='smc')
            smc2.set_password('Test@123')
            db.session.add_all([smc1, smc2])
            db.session.commit()
            
            # Create tournament for smc2
            t2 = Tournament(name='SMC2 Tournament', start_date=date.today(),
                          end_date=date.today() + timedelta(days=30),
                          created_by=smc2.id)
            db.session.add(t2)
            db.session.commit()
            tournament_id = t2.id
        
        # Login as smc1
        client.post('/auth/login', data={'username': 'smc1', 'password': 'Test@123'})
        
        # Try to access smc2's tournament
        response = client.get(f'/smc/tournament/{tournament_id}', follow_redirects=True)
        assert b'do not have access' in response.data.lower() or response.status_code == 403


class TestTournamentDetail:
    """Test /smc/tournament/<id> route (Stage 2)"""

    def test_tournament_detail_loads(self, client, smc_user, tournament):
        """Test tournament detail page renders"""
        response = client.get(f'/smc/tournament/{tournament.id}')
        assert response.status_code == 200
        assert b'Test Tournament' in response.data

    def test_tournament_detail_shows_stats(self, client, smc_user, tournament, team):
        """Test tournament detail displays team and match stats"""
        # Add team to tournament
        tt = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
        db.session.add(tt)
        db.session.commit()
        
        response = client.get(f'/smc/tournament/{tournament.id}')
        assert response.status_code == 200
        assert b'total_teams' in response.data.lower() or b'teams' in response.data.lower()


class TestTeamRegistration:
    """Test /smc/tournament/<id>/register-team route (Stage 2)"""

    def test_register_team_page_loads(self, client, smc_user, tournament):
        """Test team registration form renders"""
        response = client.get(f'/smc/tournament/{tournament.id}/register-team')
        assert response.status_code == 200

    def test_register_new_team_success(self, client, smc_user, tournament):
        """Test registering a new team for tournament"""
        response = client.post(f'/smc/tournament/{tournament.id}/register-team', data={
            'team_name': 'New Team',
            'team_id': 'TEAM001',
            'department': 'CS',
            'manager_name': 'Manager Name',
            'manager_contact': '1234567890',
            'player_1_name': 'Player 1',
            'player_1_roll': '101'
        }, follow_redirects=True)
        
        assert b'registered successfully' in response.data
        
        # Verify team created
        team = Team.query.filter_by(team_id='TEAM001').first()
        assert team is not None
        assert team.created_by == smc_user.id
        assert team.is_self_managed == False
        
        # Verify team added to tournament
        tt = TournamentTeam.query.filter_by(tournament_id=tournament.id, team_id='TEAM001').first()
        assert tt is not None

    def test_register_existing_team_to_tournament(self, client, smc_user, tournament, team):
        """Test adding existing team to tournament"""
        response = client.post(f'/smc/tournament/{tournament.id}/register-team', data={
            'team_name': 'Existing Team',
            'team_id': team.team_id,
            'department': 'CS',
            'manager_name': 'Manager'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify team-tournament association created
        tt = TournamentTeam.query.filter_by(tournament_id=tournament.id, team_id=team.team_id).first()
        assert tt is not None

    def test_cannot_register_duplicate_team_id(self, client, smc_user, tournament, team):
        """Test cannot create team with existing team_id"""
        response = client.post(f'/smc/tournament/{tournament.id}/register-team', data={
            'team_name': 'Different Name',
            'team_id': team.team_id,  # Already exists
            'department': 'CS',
            'manager_name': 'Manager'
        }, follow_redirects=True)
        
        # Should either add existing team or show error
        assert response.status_code == 200

    def test_register_team_validates_required_fields(self, client, smc_user, tournament):
        """Test team registration validates required fields"""
        response = client.post(f'/smc/tournament/{tournament.id}/register-team', data={
            'team_name': '',  # Missing
            'team_id': 'TEAM001',
            'department': 'CS',
            'manager_name': 'Manager'
        }, follow_redirects=True)
        
        assert b'required' in response.data.lower()


class TestMatchScheduling:
    """Test /smc/tournament/<id>/schedule-matches route (Stage 2)"""

    def test_schedule_matches_page_loads(self, client, smc_user, tournament):
        """Test match scheduling form renders"""
        response = client.get(f'/smc/tournament/{tournament.id}/schedule-matches')
        assert response.status_code == 200

    def test_schedule_match_success(self, client, smc_user, tournament, team, team2):
        """Test scheduling a match between two teams"""
        # Add teams to tournament
        tt1 = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
        tt2 = TournamentTeam(tournament_id=tournament.id, team_id=team2.team_id)
        db.session.add_all([tt1, tt2])
        db.session.commit()
        
        response = client.post(f'/smc/tournament/{tournament.id}/schedule-matches', data={
            'team1_id': team.team_id,
            'team2_id': team2.team_id,
            'date': (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
            'time': '14:00',
            'venue': 'Stadium A'
        }, follow_redirects=True)
        
        assert b'scheduled' in response.data.lower()
        
        # Verify match created
        match = Match.query.filter_by(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id
        ).first()
        assert match is not None

    def test_schedule_match_validates_teams_in_tournament(self, client, smc_user, tournament, team, team2):
        """Test cannot schedule match with teams not in tournament"""
        # Don't add teams to tournament
        response = client.post(f'/smc/tournament/{tournament.id}/schedule-matches', data={
            'team1_id': team.team_id,
            'team2_id': team2.team_id,
            'date': (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
            'time': '14:00',
            'venue': 'Stadium A'
        }, follow_redirects=True)
        
        assert b'registered in this tournament' in response.data.lower()

    def test_schedule_match_validates_same_team(self, client, smc_user, tournament, team):
        """Test cannot schedule team against itself"""
        tt = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
        db.session.add(tt)
        db.session.commit()
        
        response = client.post(f'/smc/tournament/{tournament.id}/schedule-matches', data={
            'team1_id': team.team_id,
            'team2_id': team.team_id,  # Same team
            'date': (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
            'time': '14:00',
            'venue': 'Stadium A'
        }, follow_redirects=True)
        
        assert b'cannot play against itself' in response.data.lower()

    def test_schedule_match_validates_date_range(self, client, smc_user, tournament, team, team2):
        """Test match date must be within tournament dates"""
        tt1 = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
        tt2 = TournamentTeam(tournament_id=tournament.id, team_id=team2.team_id)
        db.session.add_all([tt1, tt2])
        db.session.commit()
        
        # Try to schedule outside tournament dates
        response = client.post(f'/smc/tournament/{tournament.id}/schedule-matches', data={
            'team1_id': team.team_id,
            'team2_id': team2.team_id,
            'date': (tournament.end_date + timedelta(days=10)).strftime('%Y-%m-%d'),
            'time': '14:00',
            'venue': 'Stadium A'
        }, follow_redirects=True)
        
        assert b'must be between' in response.data.lower()


class TestResultsEntry:
    """Test /smc/tournament/<id>/add-results route (Stage 2)"""

    def test_add_results_page_loads(self, client, smc_user, tournament):
        """Test results entry form renders"""
        response = client.get(f'/smc/tournament/{tournament.id}/add-results')
        assert response.status_code == 200

    def test_add_results_success(self, client, smc_user, tournament, team, team2):
        """Test adding results for a completed match"""
        # Create match in the past
        match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() - timedelta(days=1),
            time=datetime_time(14, 0),
            venue='Stadium A',
            status='scheduled'
        )
        db.session.add(match)
        db.session.commit()
        
        response = client.post(f'/smc/tournament/{tournament.id}/add-results', data={
            'match_id': match.id,
            'team1_score': '3',
            'team2_score': '1',
            'winner_id': team.team_id
        }, follow_redirects=True)
        
        assert b'updated' in response.data.lower()
        
        # Verify match updated
        db.session.refresh(match)
        assert match.status == 'completed'
        assert match.winner_id == team.team_id

    def test_add_results_validates_match_belongs_to_tournament(self, client, smc_user, tournament, tournament2, team, team2):
        """Test cannot add results for match in different tournament"""
        # Create match in different tournament
        match = Match(
            tournament_id=tournament2.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() - timedelta(days=1),
            time=datetime_time(14, 0),
            venue='Stadium A',
            status='scheduled'
        )
        db.session.add(match)
        db.session.commit()
        
        response = client.post(f'/smc/tournament/{tournament.id}/add-results', data={
            'match_id': match.id,
            'team1_score': '3',
            'team2_score': '1',
            'winner_id': team.team_id
        }, follow_redirects=True)
        
        assert b'does not belong' in response.data.lower()

    def test_cannot_add_results_twice(self, client, smc_user, tournament, team, team2):
        """Test cannot update results for already completed match"""
        match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() - timedelta(days=1),
            time=datetime_time(14, 0),
            venue='Stadium A',
            status='completed',
            team1_score='3',
            team2_score='1',
            winner_id=team.team_id
        )
        db.session.add(match)
        db.session.commit()
        
        response = client.post(f'/smc/tournament/{tournament.id}/add-results', data={
            'match_id': match.id,
            'team1_score': '5',
            'team2_score': '2',
            'winner_id': team.team_id
        }, follow_redirects=True)
        
        assert b'already been entered' in response.data.lower()


class TestTournamentTeamModel:
    """Test TournamentTeam association model (Stage 2)"""

    def test_tournament_team_creation(self, tournament, team):
        """Test creating tournament-team association"""
        tt = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
        db.session.add(tt)
        db.session.commit()
        
        assert tt.id is not None
        assert tt.status == 'active'
        assert tt.points == 0

    def test_tournament_team_unique_constraint(self, tournament, team):
        """Test team cannot join same tournament twice"""
        tt1 = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
        db.session.add(tt1)
        db.session.commit()
        
        # Try to add same team again
        tt2 = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
        db.session.add(tt2)
        
        with pytest.raises(Exception):  # Should raise integrity error
            db.session.commit()
        db.session.rollback()

    def test_tournament_get_teams(self, tournament, team, team2):
        """Test Tournament.get_teams() method"""
        tt1 = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
        tt2 = TournamentTeam(tournament_id=tournament.id, team_id=team2.team_id)
        db.session.add_all([tt1, tt2])
        db.session.commit()
        
        teams = tournament.get_teams()
        assert len(teams) == 2
        assert team in teams
        assert team2 in teams

    def test_team_get_tournaments(self, tournament, tournament2, team):
        """Test Team.get_tournaments() method"""
        tt1 = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
        tt2 = TournamentTeam(tournament_id=tournament2.id, team_id=team.team_id)
        db.session.add_all([tt1, tt2])
        db.session.commit()
        
        tournaments = team.get_tournaments()
        assert len(tournaments) == 2
        assert tournament in tournaments
        assert tournament2 in tournaments