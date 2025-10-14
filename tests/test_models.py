"""Stage 3 model tests aligned with updated architecture."""

from datetime import date, time, timedelta

import pytest

from models import (
    db,
    User,
    Tournament,
    Team,
    Player,
    Match,
    TournamentTeam,
    Notification,
    current_time,
)


class TestUserModel:
    def test_user_password_roundtrip(self, flask_app):
        with flask_app.app_context():
            user = User(
                username='pw_tester',
                email='pw@test.com',
                role='team_manager',
            )
            user.set_password('Strong@123')
            db.session.add(user)
            db.session.commit()

            stored = User.query.filter_by(username='pw_tester').first()
            assert stored is not None
            assert stored.check_password('Strong@123') is True
            assert stored.check_password('Wrong@123') is False

    def test_notify_creates_notification(self, flask_app, smc_user):
        with flask_app.app_context():
            smc = db.session.merge(smc_user)
            note = smc.notify('Stage 3 alert', category='info', commit=True)
            assert note.id is not None

            stored = Notification.query.filter_by(user_id=smc.id).first()
            assert stored is not None
            assert stored.message == 'Stage 3 alert'

    def test_validate_format_rejects_invalid_role(self):
        errors = User.validate_format(
            username='validuser',
            email='valid@test.com',
            password='Valid@123',
            role='invalid_role',
        )

        assert any('Invalid role selected' in err for err in errors)


class TestTournamentModel:

    def test_tournament_creation_records_creator(self, flask_app, smc_user):
        with flask_app.app_context():
            smc = db.session.merge(smc_user)
            tournament = Tournament(
                name='Stage3 Cup',
                start_date=date.today(),
                end_date=date.today() + timedelta(days=5),
                status='active',
                rules='Rulebook',
                created_by=smc.id,
                institution=smc.institution,
            )
            db.session.add(tournament)
            db.session.commit()

            stored = Tournament.query.filter_by(name='Stage3 Cup').first()
            assert stored is not None
            assert stored.creator.id == smc.id
            assert stored.institution == smc.institution
            assert stored.status == 'active'

    def test_add_team_enforces_institution_match(self, flask_app, smc_user):
        with flask_app.app_context():
            smc = db.session.merge(smc_user)
            tournament = Tournament(
                name='Closed League',
                start_date=date.today(),
                end_date=date.today() + timedelta(days=10),
                created_by=smc.id,
                institution='Tech University',
            )
            mismatched_team = Team(
                team_id='MIS01',
                name='Mismatch',
                department='ECE',
                manager_name='Mismatch Manager',
                manager_contact='1234567890',
                created_by=smc.id,
                institution='Commerce College',
            )
            db.session.add_all([tournament, mismatched_team])
            db.session.commit()

            tournament = db.session.merge(tournament)
            mismatched_team = db.session.merge(mismatched_team)

            with pytest.raises(ValueError):
                tournament.add_team(mismatched_team, added_by=smc)

    def test_add_team_allows_public_entries(self, flask_app, smc_user):
        with flask_app.app_context():
            smc = db.session.merge(smc_user)
            open_tournament = Tournament(
                name='Open League',
                start_date=date.today(),
                end_date=date.today() + timedelta(days=7),
                created_by=smc.id,
                institution=None,
            )
            team = Team(
                team_id='OPEN01',
                name='Open Squad',
                department='CSE',
                manager_name='Open Manager',
                manager_contact='5555555555',
                created_by=smc.id,
                institution='General Institution',
            )
            db.session.add_all([open_tournament, team])
            db.session.commit()

            open_tournament = db.session.merge(open_tournament)
            team = db.session.merge(team)
            assoc = open_tournament.add_team(team, added_by=smc, method='smc_added', auto_commit=True)

            assert assoc.status == 'active'
            assert assoc.registration_method == 'smc_added'
            assert assoc.approved_at is not None
            assert assoc.approved_by == smc.id

    def test_add_team_invite_remains_pending(self, flask_app, smc_user, team):
        with flask_app.app_context():
            smc = db.session.merge(smc_user)
            team = db.session.merge(team)
            invite_tournament = Tournament(
                name='Invite League',
                start_date=date.today(),
                end_date=date.today() + timedelta(days=14),
                created_by=smc.id,
                institution=team.institution,
            )
            db.session.add(invite_tournament)
            db.session.commit()

            invite_tournament = db.session.merge(invite_tournament)
            assoc = invite_tournament.add_team(
                team,
                added_by=smc,
                method='smc_invited',
                auto_commit=True,
            )

            assert assoc.status == 'pending'
            assert assoc.approved_at is None
            assert assoc.approved_by is None
            assert assoc.requested_at is not None
            assert assoc.status_updated_at is not None

    def test_validate_end_date_requires_chronology(self, flask_app, smc_user):
        with flask_app.app_context():
            smc = db.session.merge(smc_user)
            tournament = Tournament(
                name='Chronology Check',
                start_date=date.today(),
                end_date=date.today() + timedelta(days=3),
                created_by=smc.id,
                institution=smc.institution,
            )
            db.session.add(tournament)
            db.session.commit()

            with pytest.raises(ValueError):
                tournament.end_date = tournament.start_date - timedelta(days=1)


class TestTournamentTeamModel:

    def test_defaults_to_pending_status(self, flask_app, tournament, team):
        with flask_app.app_context():
            tournament = db.session.merge(tournament)
            team = db.session.merge(team)

            assoc = TournamentTeam(
                tournament_id=tournament.id,
                team_id=team.team_id,
            )
            db.session.add(assoc)
            db.session.commit()

            stored = TournamentTeam.query.filter_by(tournament_id=tournament.id, team_id=team.team_id).first()
            assert stored is not None
            assert stored.status == 'pending'
            assert stored.requested_at is not None
            assert stored.status_updated_at is not None

    def test_set_status_active_records_approver(self, flask_app, tournament, team, smc_user):
        with flask_app.app_context():
            tournament = db.session.merge(tournament)
            team = db.session.merge(team)
            smc = db.session.merge(smc_user)

            assoc = TournamentTeam(
                tournament_id=tournament.id,
                team_id=team.team_id,
            )
            db.session.add(assoc)
            db.session.commit()

            assoc.set_status('active', actor=smc)
            db.session.commit()

            assert assoc.status == 'active'
            assert assoc.approved_at is not None
            assert assoc.approved_by == smc.id
            assert assoc.status_updated_at is not None


class TestTeamModel:

    def test_team_self_managed_default(self, flask_app, smc_user):
        with flask_app.app_context():
            smc = db.session.merge(smc_user)
            team = Team(
                team_id='SELFM1',
                name='Self Managed',
                department='CSE',
                manager_name='Owner Manager',
                manager_contact='9999999999',
                created_by=smc.id,
                institution=smc.institution,
            )
            db.session.add(team)
            db.session.commit()

            assert team.managed_by == smc.id
            assert team.is_self_managed is True

    def test_assign_manager_updates_and_notifies(self, flask_app, smc_user, team_manager_user):
        with flask_app.app_context():
            smc = db.session.merge(smc_user)
            manager = db.session.merge(team_manager_user)
            team = Team(
                team_id='ASSIGN1',
                name='Assigned Team',
                department='ECE',
                manager_name='Temp Manager',
                manager_contact='8888888888',
                created_by=smc.id,
                institution=smc.institution,
            )
            db.session.add(team)
            db.session.commit()

            team.assign_manager(manager)
            db.session.commit()

            assert team.managed_by == manager.id
            assert team.is_self_managed is False

            notifications = Notification.query.filter_by(user_id=manager.id, kind='team_assignment').all()
            assert len(notifications) == 1
            assert 'Assigned Team' in notifications[0].message

    def test_get_tournaments_returns_associations(self, flask_app, tournament, team, smc_user):
        with flask_app.app_context():
            tournament = db.session.merge(tournament)
            team = db.session.merge(team)
            smc = db.session.merge(smc_user)

            tournament.add_team(team, added_by=smc, method='smc_added', auto_commit=True)

            tournaments = team.get_tournaments()
            assert len(tournaments) == 1
            assert tournaments[0].id == tournament.id

    def test_get_upcoming_matches_filters(self, flask_app, tournament, team, team2):
        with flask_app.app_context():
            tournament = db.session.merge(tournament)
            team = db.session.merge(team)
            team2 = db.session.merge(team2)

            future_match = Match(
                tournament_id=tournament.id,
                team1_id=team.team_id,
                team2_id=team2.team_id,
                date=date.today() + timedelta(days=5),
                time=time(14, 0),
                venue='Field 1',
                status='scheduled',
            )
            past_match = Match(
                tournament_id=tournament.id,
                team1_id=team.team_id,
                team2_id=team2.team_id,
                date=date.today() - timedelta(days=5),
                time=time(14, 0),
                venue='Field 2',
                status='scheduled',
            )
            completed_match = Match(
                tournament_id=tournament.id,
                team1_id=team.team_id,
                team2_id=team2.team_id,
                date=date.today(),
                time=time(14, 0),
                venue='Field 3',
                status='completed',
            )

            db.session.add_all([future_match, past_match, completed_match])
            db.session.commit()

            upcoming = team.get_upcoming_matches()
            assert len(upcoming) == 1
            assert upcoming[0].id == future_match.id

    def test_get_completed_matches_only_completed(self, flask_app, tournament, team, team2):
        with flask_app.app_context():
            tournament = db.session.merge(tournament)
            team = db.session.merge(team)
            team2 = db.session.merge(team2)

            completed1 = Match(
                tournament_id=tournament.id,
                team1_id=team.team_id,
                team2_id=team2.team_id,
                date=date.today(),
                time=time(14, 0),
                venue='Field 1',
                status='completed',
            )
            completed2 = Match(
                tournament_id=tournament.id,
                team1_id=team.team_id,
                team2_id=team2.team_id,
                date=date.today() - timedelta(days=1),
                time=time(15, 0),
                venue='Field 2',
                status='completed',
            )
            scheduled = Match(
                tournament_id=tournament.id,
                team1_id=team.team_id,
                team2_id=team2.team_id,
                date=date.today() + timedelta(days=1),
                time=time(16, 0),
                venue='Field 3',
                status='scheduled',
            )

            db.session.add_all([completed1, completed2, scheduled])
            db.session.commit()

            completed = team.get_completed_matches()
            assert len(completed) == 2
            assert {m.id for m in completed} == {completed1.id, completed2.id}

    def test_get_match_record_counts(self, flask_app, tournament, team, team2):
        with flask_app.app_context():
            tournament = db.session.merge(tournament)
            team = db.session.merge(team)
            team2 = db.session.merge(team2)

            win = Match(
                tournament_id=tournament.id,
                team1_id=team.team_id,
                team2_id=team2.team_id,
                date=date.today(),
                time=time(14, 0),
                venue='Field 1',
                status='completed',
                winner_id=team.team_id,
            )
            loss = Match(
                tournament_id=tournament.id,
                team1_id=team.team_id,
                team2_id=team2.team_id,
                date=date.today(),
                time=time(15, 0),
                venue='Field 2',
                status='completed',
                winner_id=team2.team_id,
            )
            draw = Match(
                tournament_id=tournament.id,
                team1_id=team.team_id,
                team2_id=team2.team_id,
                date=date.today(),
                time=time(16, 0),
                venue='Field 3',
                status='completed',
            )

            db.session.add_all([win, loss, draw])
            db.session.commit()

            record = team.get_match_record()
            assert record == {'wins': 1, 'losses': 1, 'draws': 1, 'total': 3}

    def test_get_match_record_empty(self, flask_app, team):
        with flask_app.app_context():
            team = db.session.merge(team)
            record = team.get_match_record()
            assert record == {'wins': 0, 'losses': 0, 'draws': 0, 'total': 0}


class TestNotificationModel:

    def test_active_for_user_skips_expired(self, flask_app, smc_user):
        with flask_app.app_context():
            smc = db.session.merge(smc_user)
            active_note = Notification(
                user_id=smc.id,
                message='Still active',
                expires_at=current_time() + timedelta(days=1),
            )
            expired_note = Notification(
                user_id=smc.id,
                message='Already expired',
                expires_at=current_time() - timedelta(days=1),
            )
            db.session.add_all([active_note, expired_note])
            db.session.commit()

            results = Notification.active_for_user(smc.id).all()
            assert len(results) == 1
            assert results[0].message == 'Still active'

    def test_cleanup_expired_deletes_records(self, flask_app, smc_user):
        with flask_app.app_context():
            smc = db.session.merge(smc_user)
            expired_note = Notification(
                user_id=smc.id,
                message='Remove me',
                expires_at=current_time() - timedelta(minutes=1),
            )
            db.session.add(expired_note)
            db.session.commit()

            removed = Notification.cleanup_expired()
            assert removed == 1
            remaining = Notification.query.filter_by(user_id=smc.id).all()
            assert remaining == []


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

    def test_update_player(self, flask_app, player):
        """Test update_player method updates fields"""
        with flask_app.app_context():
            player = db.session.merge(player)
            player.update_player(name='Updated Name', contact='1111111111')
            db.session.commit()

            updated = Player.query.get(player.id)
            assert updated.name == 'Updated Name'
            assert updated.contact == '1111111111'

    def test_update_player_partial(self, flask_app, player):
        """Test update_player only updates provided fields"""
        with flask_app.app_context():
            player = db.session.merge(player)
            original_name = player.name
            player.update_player(contact='2222222222')
            db.session.commit()

            updated = Player.query.get(player.id)
            assert updated.name == original_name
            assert updated.contact == '2222222222'

    def test_update_player_ignores_empty_values(self, flask_app, player):
        """Test update_player ignores empty string values"""
        with flask_app.app_context():
            player = db.session.merge(player)
            original_contact = player.contact
            player.update_player(contact='')  # Empty string should be ignored
            db.session.commit()

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

    def test_versus_display(self, flask_app, match):
        """Test versus_display property formats team names correctly"""
        with flask_app.app_context():
            match = db.session.merge(match)
            display = match.versus_display
            assert 'vs' in display
            assert match.team1.name in display
            assert match.team2.name in display

    def test_score_display_not_completed(self, flask_app, match):
        """Test score_display for non-completed match"""
        with flask_app.app_context():
            match = db.session.merge(match)
            assert match.score_display == "Match not completed"

    def test_score_display_completed(self, flask_app, match):
        """Test score_display for completed match"""
        with flask_app.app_context():
            match = db.session.merge(match)
            match.status = 'completed'
            match.team1_score = '5'
            match.team2_score = '3'
            db.session.commit()

            display = match.score_display
            assert '5' in display
            assert '3' in display
            assert match.team1.name in display
            assert match.team2.name in display

    def test_result_display_not_completed(self, flask_app, match):
        """Test result_display for non-completed match"""
        with flask_app.app_context():
            match = db.session.merge(match)
            assert match.result_display == "Match not completed"

    def test_result_display_winner(self, flask_app, match):
        """Test result_display shows winner"""
        with flask_app.app_context():
            match = db.session.merge(match)
            match.status = 'completed'
            match.winner_id = match.team1_id
            db.session.commit()

            assert 'Winner' in match.result_display
            assert match.team1.name in match.result_display

    def test_result_display_draw(self, flask_app, match):
        """Test result_display for draw"""
        with flask_app.app_context():
            match = db.session.merge(match)
            match.status = 'completed'
            match.winner_id = None
            db.session.commit()

            assert match.result_display == "Match drawn"

    def test_opponent_of_team1(self, flask_app, match):
        """Test opponent_of method returns correct opponent for team1"""
        with flask_app.app_context():
            match = db.session.merge(match)
            opponent = match.opponent_of(match.team1_id)
            assert opponent.team_id == match.team2_id

    def test_opponent_of_team2(self, flask_app, match):
        """Test opponent_of method returns correct opponent for team2"""
        with flask_app.app_context():
            match = db.session.merge(match)
            opponent = match.opponent_of(match.team2_id)
            assert opponent.team_id == match.team1_id

    def test_opponent_of_invalid_team(self, db_session, match):
        """Test opponent_of returns None for team not in match"""
        opponent = match.opponent_of('NONEXISTENT')
        assert opponent is None

    def test_match_creation_timestamp(self, db_session, match):
        """Test match creation timestamp is set"""
        assert match.created_at is not None


class TestDefaultData:
    """Test default data initialization - Stage 1 updates"""

    def test_default_admin_has_email(self, db_session):
        """Test default admin user has email field (Stage 1)"""
        admin = User.query.filter_by(username='admin').first()
        
        assert admin is not None
        assert admin.email is not None
        assert admin.email == 'admin@tourneytrack.local'

    def test_default_admin_has_role(self, db_session):
        """Test default admin user has SMC role (Stage 1)"""
        admin = User.query.filter_by(username='admin').first()
        
        assert admin is not None
        assert admin.role == 'smc'

    def test_default_admin_password_works(self, db_session):
        """Test default admin password is correctly set"""
        admin = User.query.filter_by(username='admin').first()
        
        assert admin is not None
        assert admin.check_password('admin123') is True

    def test_default_tournament_exists(self, db_session):
        """Test default tournament is created"""
        tournament = Tournament.query.filter_by(
            name='Inter-Department Sports Tournament 2025'
        ).first()
        
        assert tournament is not None
        assert tournament.status == 'active'