"""
Unit tests for database models - testing model methods, properties, validation logic
Tests Sprint 1 implementations only
"""

import pytest
from models import User, Tournament, Team, Player, Match
from datetime import date, time, timedelta


class TestUserModel:
    """Test User model - password hashing and authentication"""

    def test_user_creation(self, db_session):
        """Test basic user creation"""
        user = User(username='testuser', role='smc')
        user.set_password('password123')
        db_session.add(user)
        db_session.commit()
        
        assert user.id is not None
        assert user.username == 'testuser'
        assert user.role == 'smc'

    def test_password_hashing(self):
        """Test password is hashed, not stored in plaintext"""
        user = User(username='test', role='smc')
        user.set_password('mypassword')
        
        # Password should not be plaintext
        assert user.password_hash != 'mypassword'
        # Hash should be reasonably long
        assert len(user.password_hash) > 50

    def test_check_password_correct(self):
        """Test check_password returns True for correct password"""
        user = User(username='test', role='smc')
        user.set_password('correctpassword')
        
        assert user.check_password('correctpassword') is True

    def test_check_password_incorrect(self):
        """Test check_password returns False for incorrect password"""
        user = User(username='test', role='smc')
        user.set_password('correctpassword')
        
        assert user.check_password('wrongpassword') is False

    def test_user_default_creation_time(self, db_session):
        """Test user creation timestamp is set"""
        user = User(username='testuser', role='smc')
        user.set_password('password123')
        db_session.add(user)
        db_session.commit()
        
        assert user.created_at is not None


class TestTournamentModel:
    """Test Tournament model - creation, relationships, properties"""

    def test_tournament_creation(self, db_session):
        """Test basic tournament creation"""
        tournament = Tournament(
            name='Test Tournament',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            status='active'
        )
        db_session.add(tournament)
        db_session.commit()
        
        assert tournament.id is not None
        assert tournament.name == 'Test Tournament'
        assert tournament.status == 'active'

    def test_tournament_status_default(self, db_session):
        """Test tournament status defaults to 'upcoming'"""
        tournament = Tournament(
            name='Test Tournament',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30)
        )
        db_session.add(tournament)
        db_session.commit()
        
        assert tournament.status == 'upcoming'

    def test_tournament_date_fields(self, db_session):
        """Test tournament date fields are stored correctly"""
        start = date(2025, 11, 1)
        end = date(2025, 11, 30)
        tournament = Tournament(
            name='Test Tournament',
            start_date=start,
            end_date=end
        )
        db_session.add(tournament)
        db_session.commit()
        
        assert tournament.start_date == start
        assert tournament.end_date == end

    def test_tournament_teams_relationship(self, db_session, tournament):
        """Test tournament can have multiple teams"""
        team1 = Team(
            team_id='T001',
            name='Team 1',
            department='CSE',
            manager_name='Manager 1',
            tournament_id=tournament.id
        )
        team1.set_password('pass1')
        team2 = Team(
            team_id='T002',
            name='Team 2',
            department='ECE',
            manager_name='Manager 2',
            tournament_id=tournament.id
        )
        team2.set_password('pass2')
        
        db_session.add_all([team1, team2])
        db_session.commit()
        
        assert len(tournament.teams) == 2

    def test_tournament_matches_relationship(self, db_session, tournament, team, team2):
        """Test tournament can have multiple matches"""
        match1 = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today(),
            time=time(14, 0),
            venue='Field 1'
        )
        match2 = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() + timedelta(days=1),
            time=time(15, 0),
            venue='Field 2'
        )
        
        db_session.add_all([match1, match2])
        db_session.commit()
        
        assert len(tournament.matches) == 2

    def test_tournament_creation_timestamp(self, db_session):
        """Test tournament creation timestamp is set"""
        tournament = Tournament(
            name='Test Tournament',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30)
        )
        db_session.add(tournament)
        db_session.commit()
        
        assert tournament.created_at is not None


class TestTeamModel:
    """Test Team model - creation, relationships, methods"""

    def test_team_creation(self, db_session, tournament):
        """Test basic team creation"""
        team = Team(
            team_id='CSE-001',
            name='CSE Team',
            department='CSE',
            manager_name='John Doe',
            manager_contact='9876543210',
            tournament_id=tournament.id
        )
        team.set_password('password123')
        db_session.add(team)
        db_session.commit()
        
        assert team.id is not None
        assert team.team_id == 'CSE-001'
        assert team.name == 'CSE Team'

    def test_team_is_active_default(self, db_session, tournament):
        """Test team is_active defaults to True"""
        team = Team(
            team_id='T001',
            name='Team',
            department='CSE',
            manager_name='Manager',
            tournament_id=tournament.id
        )
        team.set_password('password123')
        db_session.add(team)
        db_session.commit()
        
        assert team.is_active is True

    def test_team_password_hashing(self, db_session, tournament):
        """Test team password is hashed correctly"""
        team = Team(
            team_id='T001',
            name='Team',
            department='CSE',
            manager_name='Manager',
            tournament_id=tournament.id
        )
        team.set_password('team_password')
        db_session.add(team)
        db_session.commit()
        
        assert team.password_hash != 'team_password'
        assert len(team.password_hash) > 50

    def test_team_check_password(self, db_session, tournament):
        """Test team password verification"""
        team = Team(
            team_id='T001',
            name='Team',
            department='CSE',
            manager_name='Manager',
            tournament_id=tournament.id
        )
        team.set_password('mypassword')
        db_session.add(team)
        db_session.commit()
        
        assert team.check_password('mypassword') is True
        assert team.check_password('wrongpassword') is False

    def test_team_players_relationship(self, db_session, team):
        """Test team can have multiple players"""
        player1 = Player(
            name='Player 1',
            roll_number=101,
            department='CSE',
            year='3',
            team_id=team.team_id
        )
        player2 = Player(
            name='Player 2',
            roll_number=102,
            department='CSE',
            year='3',
            team_id=team.team_id
        )
        
        db_session.add_all([player1, player2])
        db_session.commit()
        
        assert len(team.players) == 2

    def test_get_upcoming_matches(self, db_session, team, team2, tournament):
        """Test get_upcoming_matches returns only scheduled future matches"""
        # Future match
        future_match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() + timedelta(days=5),
            time=time(14, 0),
            venue='Field 1',
            status='scheduled'
        )
        # Past match
        past_match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() - timedelta(days=5),
            time=time(14, 0),
            venue='Field 2',
            status='scheduled'
        )
        # Completed match
        completed_match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today(),
            time=time(14, 0),
            venue='Field 3',
            status='completed'
        )
        
        db_session.add_all([future_match, past_match, completed_match])
        db_session.commit()
        
        upcoming = team.get_upcoming_matches()
        assert len(upcoming) == 1
        assert upcoming[0].date == date.today() + timedelta(days=5)

    def test_get_completed_matches(self, db_session, team, team2, tournament):
        """Test get_completed_matches returns only completed matches"""
        completed1 = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today(),
            time=time(14, 0),
            venue='Field 1',
            status='completed'
        )
        completed2 = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() - timedelta(days=1),
            time=time(15, 0),
            venue='Field 2',
            status='completed'
        )
        scheduled = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() + timedelta(days=1),
            time=time(16, 0),
            venue='Field 3',
            status='scheduled'
        )
        
        db_session.add_all([completed1, completed2, scheduled])
        db_session.commit()
        
        completed = team.get_completed_matches()
        assert len(completed) == 2

    def test_get_match_record_wins_losses_draws(self, db_session, team, team2, tournament):
        """Test get_match_record calculates wins, losses, draws correctly"""
        # Win for team
        win = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today(),
            time=time(14, 0),
            venue='Field 1',
            status='completed',
            winner_id=team.team_id
        )
        # Loss for team
        loss = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today(),
            time=time(15, 0),
            venue='Field 2',
            status='completed',
            winner_id=team2.team_id
        )
        # Draw (no winner)
        draw = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today(),
            time=time(16, 0),
            venue='Field 3',
            status='completed'
        )
        
        db_session.add_all([win, loss, draw])
        db_session.commit()
        
        record = team.get_match_record()
        assert record['wins'] == 1
        assert record['losses'] == 1
        assert record['draws'] == 1
        assert record['total'] == 3

    def test_get_match_record_no_matches(self, db_session, team):
        """Test get_match_record with no completed matches"""
        record = team.get_match_record()
        assert record['wins'] == 0
        assert record['losses'] == 0
        assert record['draws'] == 0
        assert record['total'] == 0

    def test_team_creation_timestamp(self, db_session, tournament):
        """Test team creation timestamp is set"""
        team = Team(
            team_id='T001',
            name='Team',
            department='CSE',
            manager_name='Manager',
            tournament_id=tournament.id
        )
        team.set_password('password123')
        db_session.add(team)
        db_session.commit()
        
        assert team.created_at is not None


class TestPlayerModel:
    """Test Player model - creation, relationships, methods"""

    def test_player_creation(self, db_session, team):
        """Test basic player creation"""
        player = Player(
            name='John Doe',
            roll_number=12345,
            contact='9876543210',
            department='CSE',
            year='3',
            team_id=team.team_id
        )
        db_session.add(player)
        db_session.commit()
        
        assert player.id is not None
        assert player.name == 'John Doe'
        assert player.roll_number == 12345

    def test_player_is_active_default(self, db_session, team):
        """Test player is_active defaults to True"""
        player = Player(
            name='Player',
            roll_number=101,
            team_id=team.team_id
        )
        db_session.add(player)
        db_session.commit()
        
        assert player.is_active is True

    def test_player_team_relationship(self, db_session, team):
        """Test player belongs to correct team"""
        player = Player(
            name='Player',
            roll_number=101,
            team_id=team.team_id
        )
        db_session.add(player)
        db_session.commit()
        
        assert player.team_id == team.team_id
        assert player.team.name == team.name

    def test_player_roll_number_unique(self, db_session, team):
        """Test roll_number is unique across all players"""
        player1 = Player(
            name='Player 1',
            roll_number=12345,
            team_id=team.team_id
        )
        db_session.add(player1)
        db_session.commit()
        
        player2 = Player(
            name='Player 2',
            roll_number=12345,  # Duplicate roll number
            team_id=team.team_id
        )
        db_session.add(player2)
        
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()

    def test_update_player(self, db_session, player):
        """Test update_player method updates fields"""
        player.update_player(name='Updated Name', contact='1111111111')
        db_session.commit()
        
        updated = Player.query.get(player.id)
        assert updated.name == 'Updated Name'
        assert updated.contact == '1111111111'

    def test_update_player_partial(self, db_session, player):
        """Test update_player only updates provided fields"""
        original_name = player.name
        player.update_player(contact='2222222222')
        db_session.commit()
        
        updated = Player.query.get(player.id)
        assert updated.name == original_name
        assert updated.contact == '2222222222'

    def test_update_player_ignores_empty_values(self, db_session, player):
        """Test update_player ignores empty string values"""
        original_contact = player.contact
        player.update_player(contact='')  # Empty string should be ignored
        db_session.commit()
        
        updated = Player.query.get(player.id)
        assert updated.contact == original_contact

    def test_player_creation_timestamp(self, db_session, team):
        """Test player creation timestamp is set"""
        player = Player(
            name='Player',
            roll_number=101,
            team_id=team.team_id
        )
        db_session.add(player)
        db_session.commit()
        
        assert player.created_at is not None


class TestMatchModel:
    """Test Match model - creation, relationships, properties, methods"""

    def test_match_creation(self, db_session, tournament, team, team2):
        """Test basic match creation"""
        match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date(2025, 11, 15),
            time=time(14, 0),
            venue='Main Field'
        )
        db_session.add(match)
        db_session.commit()
        
        assert match.id is not None
        assert match.status == 'scheduled'

    def test_match_status_default(self, db_session, match):
        """Test match status defaults to 'scheduled'"""
        assert match.status == 'scheduled'

    def test_is_upcoming_true_for_future_match(self, db_session, tournament, team, team2):
        """Test is_upcoming property returns True for future scheduled matches"""
        future_match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() + timedelta(days=5),
            time=time(14, 0),
            venue='Field',
            status='scheduled'
        )
        db_session.add(future_match)
        db_session.commit()
        
        assert future_match.is_upcoming is True

    def test_is_upcoming_false_for_completed_match(self, db_session, tournament, team, team2):
        """Test is_upcoming returns False for completed matches"""
        completed_match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today(),
            time=time(14, 0),
            venue='Field',
            status='completed'
        )
        db_session.add(completed_match)
        db_session.commit()
        
        assert completed_match.is_upcoming is False

    def test_is_upcoming_false_for_past_match(self, db_session, tournament, team, team2):
        """Test is_upcoming returns False for past scheduled matches"""
        past_match = Match(
            tournament_id=tournament.id,
            team1_id=team.team_id,
            team2_id=team2.team_id,
            date=date.today() - timedelta(days=5),
            time=time(14, 0),
            venue='Field',
            status='scheduled'
        )
        db_session.add(past_match)
        db_session.commit()
        
        assert past_match.is_upcoming is False

    def test_versus_display(self, db_session, match):
        """Test versus_display property formats team names correctly"""
        display = match.versus_display
        assert 'vs' in display
        assert match.team1.name in display
        assert match.team2.name in display

    def test_score_display_not_completed(self, db_session, match):
        """Test score_display for non-completed match"""
        assert match.score_display == "Match not completed"

    def test_score_display_completed(self, db_session, match):
        """Test score_display for completed match"""
        match.status = 'completed'
        match.team1_score = '5'
        match.team2_score = '3'
        db_session.commit()
        
        display = match.score_display
        assert '5' in display
        assert '3' in display
        assert match.team1.name in display
        assert match.team2.name in display

    def test_result_display_not_completed(self, db_session, match):
        """Test result_display for non-completed match"""
        assert match.result_display == "Match not completed"

    def test_result_display_winner(self, db_session, match):
        """Test result_display shows winner"""
        match.status = 'completed'
        match.winner_id = match.team1_id
        db_session.commit()
        
        assert 'Winner' in match.result_display
        assert match.team1.name in match.result_display

    def test_result_display_draw(self, db_session, match):
        """Test result_display for draw"""
        match.status = 'completed'
        match.winner_id = None
        db_session.commit()
        
        assert match.result_display == "Match drawn"

    def test_opponent_of_team1(self, db_session, match):
        """Test opponent_of method returns correct opponent for team1"""
        opponent = match.opponent_of(match.team1_id)
        assert opponent.team_id == match.team2_id

    def test_opponent_of_team2(self, db_session, match):
        """Test opponent_of method returns correct opponent for team2"""
        opponent = match.opponent_of(match.team2_id)
        assert opponent.team_id == match.team1_id

    def test_opponent_of_invalid_team(self, db_session, match):
        """Test opponent_of returns None for team not in match"""
        opponent = match.opponent_of('NONEXISTENT')
        assert opponent is None

    def test_match_creation_timestamp(self, db_session, match):
        """Test match creation timestamp is set"""
        assert match.created_at is not None