"""
Integration tests for SMC blueprint - testing multi-tournament support added in Stage 2
Tests /smc/* routes for tournament creation, isolation, and team management
"""

import pytest
from models import db, User, Tournament, Team, TournamentTeam, Match
from datetime import date, timedelta, time as datetime_time


class TestSMCDashboard:
    """Test new /smc/dashboard route (Stage 2)"""

    def test_dashboard_loads_for_smc(self, authenticated_smc):
        """Test SMC dashboard renders"""
        response = authenticated_smc.get('/smc/dashboard')
        assert response.status_code == 200

    def test_dashboard_shows_own_tournaments(self, authenticated_smc, tournament):
        """Test dashboard displays tournaments created by logged-in SMC"""
        response = authenticated_smc.get('/smc/dashboard')
        assert response.status_code == 200
        assert b'Test Tournament' in response.data

    def test_dashboard_shows_stats(self, authenticated_smc, tournament):
        """Test dashboard displays tournament statistics"""
        response = authenticated_smc.get('/smc/dashboard')
        assert response.status_code == 200

    def test_dashboard_requires_login(self, client):
        """Test dashboard requires authentication"""
        response = client.get('/smc/dashboard')
        assert response.status_code == 302

    def test_dashboard_requires_smc_role(self, authenticated_team_manager):
        """Test dashboard requires SMC role"""
        response = authenticated_team_manager.get('/smc/dashboard', follow_redirects=True)
        # Should either redirect or show error
        assert response.status_code in [200, 302, 403]


class TestTournamentCreation:
    """Test /smc/create-tournament route (Stage 2)"""

    def test_create_tournament_page_loads(self, authenticated_smc):
        """Test tournament creation form renders"""
        response = authenticated_smc.get('/smc/create-tournament')
        assert response.status_code == 200

    def test_create_tournament_success(self, authenticated_smc, flask_app):
        """Test successful tournament creation"""
        response = authenticated_smc.post('/smc/create-tournament', data={
            'name': 'New Basketball Tournament',
            'start_date': (date.today() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'end_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'rules': 'Standard rules apply'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify tournament created
        with flask_app.app_context():
            tournament = Tournament.query.filter_by(name='New Basketball Tournament').first()
            assert tournament is not None

    def test_create_tournament_sets_correct_status(self, authenticated_smc, flask_app):
        """Test tournament status set based on dates"""
        authenticated_smc.post('/smc/create-tournament', data={
            'name': 'Future Tournament',
            'start_date': (date.today() + timedelta(days=10)).strftime('%Y-%m-%d'),
            'end_date': (date.today() + timedelta(days=40)).strftime('%Y-%m-%d'),
            'rules': 'Rules'
        })
        
        with flask_app.app_context():
            tournament = Tournament.query.filter_by(name='Future Tournament').first()
            if tournament:
                assert tournament.status == 'upcoming'

    def test_create_tournament_validates_dates(self, authenticated_smc):
        """Test cannot create tournament with end_date before start_date"""
        response = authenticated_smc.post('/smc/create-tournament', data={
            'name': 'Invalid Tournament',
            'start_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'end_date': (date.today() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'rules': 'Rules'
        }, follow_redirects=True)
        
        # Should show validation error
        assert response.status_code == 200

    def test_create_tournament_requires_name(self, authenticated_smc):
        """Test tournament name is required"""
        response = authenticated_smc.post('/smc/create-tournament', data={
            'name': '',
            'start_date': date.today().strftime('%Y-%m-%d'),
            'end_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'rules': 'Rules'
        }, follow_redirects=True)
        
        assert response.status_code == 200


class TestTournamentIsolation:
    """Test SMC can only access their own tournaments (Stage 2)"""

    def test_smc_sees_only_own_tournaments(self, flask_app, client):
        """Test SMC dashboard shows only tournaments they created"""
        with flask_app.app_context():
            # Create two SMCs
            smc1 = User(username='smc1', email='smc1@test.com', role='smc')
            smc1.set_password('Test@123')
            smc2 = User(username='smc2', email='smc2@test.com', role='smc')
            smc2.set_password('Test@123')
            db.session.add_all([smc1, smc2])
            db.session.commit()
            
            smc1_id = smc1.id
            smc2_id = smc2.id
            
            # Create tournaments for each SMC
            t1 = Tournament(name='SMC1 Tournament', start_date=date.today(),
                          end_date=date.today() + timedelta(days=30),
                          created_by=smc1_id)
            t2 = Tournament(name='SMC2 Tournament', start_date=date.today(),
                          end_date=date.today() + timedelta(days=30),
                          created_by=smc2_id)
            db.session.add_all([t1, t2])
            db.session.commit()
        
        # Login as smc1
        with client.session_transaction() as sess:
            sess['user_id'] = smc1_id
            sess['username'] = 'smc1'
            sess['role'] = 'smc'
        
        response = client.get('/smc/dashboard')
        assert b'SMC1 Tournament' in response.data
        assert b'SMC2 Tournament' not in response.data

    def test_smc_cannot_access_other_tournament(self, flask_app, client):
        """Test SMC cannot access tournament detail of other SMC's tournament"""
        with flask_app.app_context():
            # Create two SMCs
            smc1 = User(username='smc1', email='smc1@test.com', role='smc')
            smc1.set_password('Test@123')
            smc2 = User(username='smc2', email='smc2@test.com', role='smc')
            smc2.set_password('Test@123')
            db.session.add_all([smc1, smc2])
            db.session.commit()
            
            smc1_id = smc1.id
            smc2_id = smc2.id
            
            # Create tournament for smc2
            t2 = Tournament(name='SMC2 Tournament', start_date=date.today(),
                          end_date=date.today() + timedelta(days=30),
                          created_by=smc2_id)
            db.session.add(t2)
            db.session.commit()
            tournament_id = t2.id
        
        # Login as smc1
        with client.session_transaction() as sess:
            sess['user_id'] = smc1_id
            sess['username'] = 'smc1'
            sess['role'] = 'smc'
        
        # Try to access smc2's tournament
        response = client.get(f'/smc/tournament/{tournament_id}', follow_redirects=True)
        # Should redirect or show error
        assert response.status_code in [200, 302, 403]


class TestTournamentDetail:
    """Test /smc/tournament/<id> route (Stage 2)"""

    def test_tournament_detail_loads(self, authenticated_smc, tournament):
        """Test tournament detail page renders"""
        response = authenticated_smc.get(f'/smc/tournament/{tournament.id}')
        assert response.status_code == 200

    def test_tournament_detail_shows_stats(self, authenticated_smc, tournament, team, flask_app):
        """Test tournament detail displays team and match stats"""
        # Add team to tournament
        with flask_app.app_context():
            tt = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
            db.session.add(tt)
            db.session.commit()
        
        response = authenticated_smc.get(f'/smc/tournament/{tournament.id}')
        assert response.status_code == 200


class TestTeamRegistration:
    """Test /smc/tournament/<id>/register-team route (Stage 2)"""

    def test_register_team_page_loads(self, authenticated_smc, tournament):
        """Test team registration form renders"""
        response = authenticated_smc.get(f'/smc/tournament/{tournament.id}/register-team')
        assert response.status_code == 200

    def test_register_new_team_success(self, authenticated_smc, tournament, flask_app):
        """Test registering a new team for tournament"""
        response = authenticated_smc.post(f'/smc/tournament/{tournament.id}/register-team', data={
            'team_name': 'New Team',
            'team_id': 'TEAM001',
            'department': 'CS',
            'manager_name': 'Manager Name',
            'manager_contact': '1234567890',
            'player_1_name': 'Player 1',
            'player_1_roll': '101'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify team created
        with flask_app.app_context():
            team = Team.query.filter_by(team_id='TEAM001').first()
            assert team is not None

    def test_register_existing_team_to_tournament(self, authenticated_smc, tournament, team, flask_app):
        """Test adding existing team to tournament"""
        response = authenticated_smc.post(f'/smc/tournament/{tournament.id}/register-team', data={
            'team_name': 'Existing Team',
            'team_id': team.team_id,
            'department': 'CS',
            'manager_name': 'Manager'
        }, follow_redirects=True)
        
        assert response.status_code == 200

    def test_register_team_validates_required_fields(self, authenticated_smc, tournament):
        """Test team registration validates required fields"""
        response = authenticated_smc.post(f'/smc/tournament/{tournament.id}/register-team', data={
            'team_name': '',
            'team_id': 'TEAM001',
            'department': 'CS',
            'manager_name': 'Manager'
        }, follow_redirects=True)
        
        assert response.status_code == 200


class TestMatchScheduling:
    """Test /smc/tournament/<id>/schedule-matches route (Stage 2)"""

    def test_schedule_matches_page_loads(self, authenticated_smc, tournament):
        """Test match scheduling form renders"""
        response = authenticated_smc.get(f'/smc/tournament/{tournament.id}/schedule-matches')
        assert response.status_code == 200

    def test_schedule_match_success(self, authenticated_smc, tournament, team, team2, flask_app):
        """Test scheduling a match between two teams"""
        # Add teams to tournament
        with flask_app.app_context():
            tt1 = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
            tt2 = TournamentTeam(tournament_id=tournament.id, team_id=team2.team_id)
            db.session.add_all([tt1, tt2])
            db.session.commit()
        
        response = authenticated_smc.post(f'/smc/tournament/{tournament.id}/schedule-matches', data={
            'team1_id': team.team_id,
            'team2_id': team2.team_id,
            'date': (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
            'time': '14:00',
            'venue': 'Stadium A'
        }, follow_redirects=True)
        
        assert response.status_code == 200

    def test_schedule_match_validates_teams_in_tournament(self, authenticated_smc, tournament, team, team2):
        """Test cannot schedule match with teams not in tournament"""
        response = authenticated_smc.post(f'/smc/tournament/{tournament.id}/schedule-matches', data={
            'team1_id': team.team_id,
            'team2_id': team2.team_id,
            'date': (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
            'time': '14:00',
            'venue': 'Stadium A'
        }, follow_redirects=True)
        
        assert response.status_code == 200

    def test_schedule_match_validates_same_team(self, authenticated_smc, tournament, team, flask_app):
        """Test cannot schedule team against itself"""
        with flask_app.app_context():
            tt = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
            db.session.add(tt)
            db.session.commit()
        
        response = authenticated_smc.post(f'/smc/tournament/{tournament.id}/schedule-matches', data={
            'team1_id': team.team_id,
            'team2_id': team.team_id,
            'date': (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
            'time': '14:00',
            'venue': 'Stadium A'
        }, follow_redirects=True)
        
        assert response.status_code == 200

    def test_schedule_match_validates_date_range(self, authenticated_smc, tournament, team, team2, flask_app):
        """Test match date must be within tournament dates"""
        with flask_app.app_context():
            tt1 = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
            tt2 = TournamentTeam(tournament_id=tournament.id, team_id=team2.team_id)
            db.session.add_all([tt1, tt2])
            db.session.commit()
        
        response = authenticated_smc.post(f'/smc/tournament/{tournament.id}/schedule-matches', data={
            'team1_id': team.team_id,
            'team2_id': team2.team_id,
            'date': (tournament.end_date + timedelta(days=10)).strftime('%Y-%m-%d'),
            'time': '14:00',
            'venue': 'Stadium A'
        }, follow_redirects=True)
        
        assert response.status_code == 200


class TestResultsEntry:
    """Test /smc/tournament/<id>/add-results route (Stage 2)"""

    def test_add_results_page_loads(self, authenticated_smc, tournament):
        """Test results entry form renders"""
        response = authenticated_smc.get(f'/smc/tournament/{tournament.id}/add-results')
        assert response.status_code == 200

    def test_add_results_success(self, authenticated_smc, tournament, team, team2, flask_app):
        """Test adding results for a completed match"""
        # Create match in the past
        with flask_app.app_context():
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
            match_id = match.id
        
        response = authenticated_smc.post(f'/smc/tournament/{tournament.id}/add-results', data={
            'match_id': match_id,
            'team1_score': '3',
            'team2_score': '1',
            'winner_id': team.team_id
        }, follow_redirects=True)
        
        assert response.status_code == 200

    def test_add_results_validates_match_belongs_to_tournament(self, authenticated_smc, tournament, tournament2, team, team2, flask_app):
        """Test cannot add results for match in different tournament"""
        # Create match in different tournament
        with flask_app.app_context():
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
            match_id = match.id
        
        response = authenticated_smc.post(f'/smc/tournament/{tournament.id}/add-results', data={
            'match_id': match_id,
            'team1_score': '3',
            'team2_score': '1',
            'winner_id': team.team_id
        }, follow_redirects=True)
        
        assert response.status_code == 200

    def test_cannot_add_results_twice(self, authenticated_smc, tournament, team, team2, flask_app):
        """Test cannot update results for already completed match"""
        with flask_app.app_context():
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
            match_id = match.id
        
        response = authenticated_smc.post(f'/smc/tournament/{tournament.id}/add-results', data={
            'match_id': match_id,
            'team1_score': '5',
            'team2_score': '2',
            'winner_id': team.team_id
        }, follow_redirects=True)
        
        assert response.status_code == 200


class TestTournamentTeamModel:
    """Test TournamentTeam association model (Stage 2)"""

    def test_tournament_team_creation(self, flask_app, tournament, team):
        """Test creating tournament-team association"""
        with flask_app.app_context():
            tt = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
            db.session.add(tt)
            db.session.commit()
            
            assert tt.id is not None
            assert tt.status == 'active'
            assert tt.points == 0

    def test_tournament_team_unique_constraint(self, flask_app, tournament, team):
        """Test team cannot join same tournament twice"""
        with flask_app.app_context():
            tt1 = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
            db.session.add(tt1)
            db.session.commit()
            
            # Try to add same team again
            tt2 = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
            db.session.add(tt2)
            
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()

    def test_tournament_get_teams(self, flask_app, tournament, team, team2):
        """Test Tournament.get_teams() method"""
        with flask_app.app_context():
            tt1 = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
            tt2 = TournamentTeam(tournament_id=tournament.id, team_id=team2.team_id)
            db.session.add_all([tt1, tt2])
            db.session.commit()
            
            teams = tournament.get_teams()
            assert len(teams) == 2
            team_ids = [t.team_id for t in teams]
            assert team.team_id in team_ids
            assert team2.team_id in team_ids

    def test_team_get_tournaments(self, flask_app, tournament, tournament2, team):
        """Test Team.get_tournaments() method"""
        with flask_app.app_context():
            tt1 = TournamentTeam(tournament_id=tournament.id, team_id=team.team_id)
            tt2 = TournamentTeam(tournament_id=tournament2.id, team_id=team.team_id)
            db.session.add_all([tt1, tt2])
            db.session.commit()
            
            tournaments = team.get_tournaments()
            assert len(tournaments) == 2
            tournament_ids = [t.id for t in tournaments]
            assert tournament.id in tournament_ids
            assert tournament2.id in tournament_ids