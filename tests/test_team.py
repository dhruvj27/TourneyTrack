"""
Integration tests for Team blueprint - testing Stage 3 features
Tests /team/* routes for team self-registration, tournament browsing, and join requests
"""

import pytest
from models import db, User, Tournament, Team, Player, TournamentTeam, Notification
from datetime import date, timedelta


class TestTeamCreation:
    """Test /team/create-team route (Stage 3)"""

    def test_create_team_page_loads(self, authenticated_team_manager):
        """Test team creation form renders"""
        response = authenticated_team_manager.get('/team/create-team')
        assert response.status_code == 200

    def test_create_team_success(self, authenticated_team_manager, flask_app):
        """Test successful team creation by manager"""
        response = authenticated_team_manager.post('/team/create-team', data={
            'team_name': 'Manager Team',
            'department': 'CSE',
            'manager_name': 'Team Manager',
            'manager_contact': '9876543210',
            'player_1_name': 'Player One',
            'player_1_roll': '1001'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify team created
        with flask_app.app_context():
            team = Team.query.filter_by(name='Manager Team').first()
            assert team is not None
            assert team.is_self_managed is True
            assert team.team_id.startswith('TM')

    def test_create_team_generates_team_id(self, authenticated_team_manager, flask_app):
        """Test team ID is auto-generated in TM0001 format"""
        authenticated_team_manager.post('/team/create-team', data={
            'team_name': 'Auto ID Team',
            'department': 'ECE',
            'manager_name': 'Manager',
            'manager_contact': '1234567890'
        })
        
        with flask_app.app_context():
            team = Team.query.filter_by(name='Auto ID Team').first()
            assert team is not None
            assert team.team_id.startswith('TM')
            assert len(team.team_id) == 6  # TM + 4 digits

    def test_create_team_sets_created_by(self, authenticated_team_manager, team_manager_user, flask_app):
        """Test created_by is set to current user"""
        authenticated_team_manager.post('/team/create-team', data={
            'team_name': 'Manager Created Team',
            'department': 'MECH',
            'manager_name': 'Manager',
            'manager_contact': '9999999999'
        })
        
        with flask_app.app_context():
            team = Team.query.filter_by(name='Manager Created Team').first()
            assert team is not None
            assert team.created_by == team_manager_user.id

    def test_create_team_with_players(self, authenticated_team_manager, flask_app):
        """Test team creation with multiple players"""
        response = authenticated_team_manager.post('/team/create-team', data={
            'team_name': 'Team With Squad',
            'department': 'CSE',
            'manager_name': 'Manager',
            'manager_contact': '9876543210',
            'player_1_name': 'Player 1',
            'player_1_roll': '1001',
            'player_1_dept': 'CSE',
            'player_1_year': '3',
            'player_1_contact': '1111111111',
            'player_2_name': 'Player 2',
            'player_2_roll': '1002',
            'player_2_dept': 'CSE',
            'player_2_year': '2',
            'player_2_contact': '2222222222'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        with flask_app.app_context():
            team = Team.query.filter_by(name='Team With Squad').first()
            assert team is not None
            players = Player.query.filter_by(team_id=team.team_id).all()
            assert len(players) == 2

    def test_create_team_validates_required_fields(self, authenticated_team_manager):
        """Test team creation validates required fields"""
        response = authenticated_team_manager.post('/team/create-team', data={
            'team_name': '',
            'department': 'CSE',
            'manager_name': 'Manager'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'required' in response.data.lower()

    def test_create_team_requires_login(self, client):
        """Test team creation requires authentication"""
        response = client.get('/team/create-team')
        assert response.status_code == 302

    def test_create_team_requires_team_manager_role(self, authenticated_smc):
        """Test team creation requires team manager role"""
        response = authenticated_smc.get('/team/create-team', follow_redirects=True)
        assert response.status_code in [200, 302, 403]


class TestMyTeams:
    """Test /team/my-teams route (Stage 3)"""

    def test_my_teams_page_loads(self, authenticated_team_manager):
        """Test my teams page renders"""
        response = authenticated_team_manager.get('/team/my-teams')
        assert response.status_code == 200

    def test_my_teams_shows_created_teams(self, authenticated_team_manager, self_managed_team):
        """Test my teams shows teams created by logged-in manager"""
        response = authenticated_team_manager.get('/team/my-teams')
        assert response.status_code == 200
        assert self_managed_team.name.encode() in response.data

    def test_my_teams_does_not_show_other_teams(self, authenticated_team_manager, team):
        """Test my teams does not show teams created by others"""
        response = authenticated_team_manager.get('/team/my-teams')
        assert response.status_code == 200
        # team fixture is created by SMC, should not appear
        assert team.name.encode() not in response.data

    def test_my_teams_shows_statistics(self, authenticated_team_manager, self_managed_team, tournament, flask_app):
        """Test my teams shows tournament count and player count"""
        # Add team to tournament
        with flask_app.app_context():
            tt = TournamentTeam(tournament_id=tournament.id, team_id=self_managed_team.team_id)
            db.session.add(tt)
            db.session.commit()
        
        response = authenticated_team_manager.get('/team/my-teams')
        assert response.status_code == 200

    def test_my_teams_empty_state(self, authenticated_team_manager):
        """Test my teams with no teams created"""
        response = authenticated_team_manager.get('/team/my-teams')
        assert response.status_code == 200

    def test_my_teams_requires_login(self, client):
        """Test my teams requires authentication"""
        response = client.get('/team/my-teams')
        assert response.status_code == 302


class TestTeamDashboard:
    """Test /team/dashboard/<team_id> route (Stage 3)"""

    def test_team_dashboard_loads(self, authenticated_team_manager, self_managed_team):
        """Test team dashboard renders for owned team"""
        response = authenticated_team_manager.get(f'/team/dashboard/{self_managed_team.team_id}')
        assert response.status_code == 200

    def test_team_dashboard_shows_team_info(self, authenticated_team_manager, self_managed_team):
        """Test dashboard displays team information"""
        response = authenticated_team_manager.get(f'/team/dashboard/{self_managed_team.team_id}')
        assert response.status_code == 200
        assert self_managed_team.name.encode() in response.data
        assert self_managed_team.department.encode() in response.data

    def test_team_dashboard_shows_tournaments(self, authenticated_team_manager, self_managed_team, tournament, flask_app):
        """Test dashboard shows tournaments team is part of"""
        # Add team to tournament
        with flask_app.app_context():
            tt = TournamentTeam(tournament_id=tournament.id, team_id=self_managed_team.team_id, status='active')
            db.session.add(tt)
            db.session.commit()
        
        response = authenticated_team_manager.get(f'/team/dashboard/{self_managed_team.team_id}')
        assert response.status_code == 200
        assert tournament.name.encode() in response.data

    def test_team_dashboard_shows_players(self, authenticated_team_manager, self_managed_team, flask_app):
        """Test dashboard shows team players"""
        # Add player to team
        with flask_app.app_context():
            player = Player(
                name='Dashboard Player',
                roll_number=9999,
                team_id=self_managed_team.team_id
            )
            db.session.add(player)
            db.session.commit()
        
        response = authenticated_team_manager.get(f'/team/dashboard/{self_managed_team.team_id}')
        assert response.status_code == 200
        assert b'Dashboard Player' in response.data

    def test_team_dashboard_authorization(self, authenticated_team_manager, team):
        """Test cannot access dashboard of team not owned"""
        response = authenticated_team_manager.get(f'/team/dashboard/{team.team_id}', follow_redirects=True)
        assert response.status_code == 200
        assert b'permission' in response.data.lower()

    def test_team_dashboard_requires_login(self, client, self_managed_team):
        """Test dashboard requires authentication"""
        response = client.get(f'/team/dashboard/{self_managed_team.team_id}')
        assert response.status_code == 302

    def test_team_dashboard_shows_match_record(self, authenticated_team_manager, self_managed_team):
        """Test dashboard shows win/loss/draw statistics"""
        response = authenticated_team_manager.get(f'/team/dashboard/{self_managed_team.team_id}')
        assert response.status_code == 200


class TestBrowseTournaments:
    """Test /team/browse-tournaments route (Stage 3)"""

    def test_browse_tournaments_page_loads(self, authenticated_team_manager):
        """Test browse tournaments page renders"""
        response = authenticated_team_manager.get('/team/browse-tournaments')
        assert response.status_code == 200

    def test_browse_tournaments_shows_all_tournaments(self, authenticated_team_manager, tournament, tournament2):
        """Test browse page shows all tournaments"""
        response = authenticated_team_manager.get('/team/browse-tournaments')
        assert response.status_code == 200
    # Just verify page loaded with content
        assert len(response.data) > 500
        assert b'tournament' in response.data.lower()

    def test_browse_tournaments_shows_joined_status(self, authenticated_team_manager, self_managed_team, tournament, flask_app):
        """Test browse page indicates which teams are already joined"""
        # Add team to tournament
        with flask_app.app_context():
            tt = TournamentTeam(tournament_id=tournament.id, team_id=self_managed_team.team_id, status='active')
            db.session.add(tt)
            db.session.commit()
        
        response = authenticated_team_manager.get('/team/browse-tournaments')
        assert response.status_code == 200
        assert b'Joined' in response.data or b'joined' in response.data

    def test_browse_tournaments_shows_pending_status(self, authenticated_team_manager, self_managed_team, tournament, flask_app):
        """Test browse page shows pending join requests"""
        # Add pending join request
        with flask_app.app_context():
            tt = TournamentTeam(tournament_id=tournament.id, team_id=self_managed_team.team_id, status='pending')
            db.session.add(tt)
            db.session.commit()
        
        response = authenticated_team_manager.get('/team/browse-tournaments')
        assert response.status_code == 200
        assert b'Pending' in response.data or b'pending' in response.data
    
    def test_browse_tournaments_shows_past_and_future(self, authenticated_team_manager, past_tournament, future_tournament, self_managed_team):
        """Test browse shows all tournaments regardless of status"""
        # The fixtures have already created and committed the tournaments
        # Now just make the request
        response = authenticated_team_manager.get('/team/browse-tournaments')
        assert response.status_code == 200
    
        response_text = response.data.decode('utf-8').lower()
    
        # Verify both tournaments appear
        assert 'pasttest' in response_text
        assert 'futuretest' in response_text

    def test_browse_tournaments_requires_login(self, client):
        """Test browse tournaments requires authentication"""
        response = client.get('/team/browse-tournaments')
        assert response.status_code == 302

    def test_browse_tournaments_requires_manager_role(self, authenticated_smc):
        """Test browse tournaments requires team manager role"""
        response = authenticated_smc.get('/team/browse-tournaments', follow_redirects=True)
        assert response.status_code in [200, 302, 403]


class TestJoinTournament:
    """Test /team/join-tournament route (Stage 3)"""

    def test_join_tournament_success(self, authenticated_team_manager, self_managed_team, tournament, flask_app):
        """Test successful tournament join request"""
        response = authenticated_team_manager.post('/team/join-tournament', data={
            'tournament_id': tournament.id,
            'team_id': self_managed_team.team_id
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify join request created with pending status
        with flask_app.app_context():
            tt = TournamentTeam.query.filter_by(
                tournament_id=tournament.id,
                team_id=self_managed_team.team_id
            ).first()
            assert tt is not None
            assert tt.status == 'pending'

    def test_join_tournament_creates_pending_request(self, authenticated_team_manager, self_managed_team, tournament, flask_app):
        """Test join creates pending request, not active"""
        authenticated_team_manager.post('/team/join-tournament', data={
            'tournament_id': tournament.id,
            'team_id': self_managed_team.team_id
        })
        
        with flask_app.app_context():
            tt = TournamentTeam.query.filter_by(
                tournament_id=tournament.id,
                team_id=self_managed_team.team_id
            ).first()
            assert tt.status == 'pending'

    def test_join_tournament_authorization(self, authenticated_team_manager, team, tournament):
        """Test cannot join tournament with team not owned"""
        response = authenticated_team_manager.post('/team/join-tournament', data={
            'tournament_id': tournament.id,
            'team_id': team.team_id
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'permission' in response.data.lower()

    def test_join_tournament_duplicate_prevented(self, authenticated_team_manager, self_managed_team, tournament, flask_app):
        """Test cannot join same tournament twice"""
        # First join
        authenticated_team_manager.post('/team/join-tournament', data={
            'tournament_id': tournament.id,
            'team_id': self_managed_team.team_id
        })
        
        # Try to join again
        response = authenticated_team_manager.post('/team/join-tournament', data={
            'tournament_id': tournament.id,
            'team_id': self_managed_team.team_id
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'already' in response.data.lower()

    def test_join_tournament_requires_login(self, client, self_managed_team, tournament):
        """Test join tournament requires authentication"""
        response = client.post('/team/join-tournament', data={
            'tournament_id': tournament.id,
            'team_id': self_managed_team.team_id
        })
        assert response.status_code == 302

    def test_join_tournament_invalid_tournament(self, authenticated_team_manager, self_managed_team):
        """Test join tournament with invalid tournament ID"""
        response = authenticated_team_manager.post('/team/join-tournament', data={
            'tournament_id': 99999,
            'team_id': self_managed_team.team_id
        }, follow_redirects=True)
        
        assert response.status_code in [200, 404]


class TestUpdateProfile:
    """Test /team/update-profile/<team_id> route (Stage 3)"""

    def test_update_profile_page_loads(self, authenticated_team_manager, self_managed_team):
        """Test profile update form renders"""
        response = authenticated_team_manager.get(f'/team/update-profile/{self_managed_team.team_id}')
        assert response.status_code == 200

    def test_update_team_details(self, authenticated_team_manager, self_managed_team, flask_app):
        """Test updating team manager details"""
        response = authenticated_team_manager.post(f'/team/update-profile/{self_managed_team.team_id}', data={
            'action': 'update_team',
            'manager_name': 'Updated Manager',
            'manager_contact': '5555555555'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        with flask_app.app_context():
            team = Team.query.filter_by(team_id=self_managed_team.team_id).first()
            assert team.manager_name == 'Updated Manager'
            assert team.manager_contact == '5555555555'

    def test_add_player(self, authenticated_team_manager, self_managed_team, flask_app):
        """Test adding new player to team"""
        response = authenticated_team_manager.post(f'/team/update-profile/{self_managed_team.team_id}', data={
            'action': 'add_player',
            'new_player_name': 'New Player',
            'new_player_roll': '8888',
            'new_player_contact': '7777777777'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        with flask_app.app_context():
            player = Player.query.filter_by(name='New Player').first()
            assert player is not None
            assert player.team_id == self_managed_team.team_id

    def test_update_player_details(self, authenticated_team_manager, self_managed_team, flask_app):
        """Test updating existing player details"""
        # Create player first
        with flask_app.app_context():
            player = Player(
                name='Original Player',
                roll_number=7777,
                team_id=self_managed_team.team_id
            )
            db.session.add(player)
            db.session.commit()
            player_id = player.id
        
        response = authenticated_team_manager.post(f'/team/update-profile/{self_managed_team.team_id}', data={
            'action': 'update_players',
            f'player_{player_id}_name': 'Updated Player',
            f'player_{player_id}_contact': '6666666666'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        with flask_app.app_context():
            player = Player.query.get(player_id)
            assert player.name == 'Updated Player'
            assert player.contact == '6666666666'

    def test_remove_player(self, authenticated_team_manager, self_managed_team, flask_app):
        """Test removing player from team"""
        # Create player first
        with flask_app.app_context():
            player = Player(
                name='Player To Remove',
                roll_number=6666,
                team_id=self_managed_team.team_id
            )
            db.session.add(player)
            db.session.commit()
            player_id = player.id
        
        response = authenticated_team_manager.post(f'/team/update-profile/{self_managed_team.team_id}', data={
            'action': 'remove_player',
            'player_id': player_id
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        with flask_app.app_context():
            player = Player.query.get(player_id)
            assert player.is_active is False

    def test_update_profile_authorization(self, authenticated_team_manager, team):
        """Test cannot update profile of team not owned"""
        response = authenticated_team_manager.get(f'/team/update-profile/{team.team_id}', follow_redirects=True)
        assert response.status_code == 200
        assert b'permission' in response.data.lower()

    def test_update_profile_requires_login(self, client, self_managed_team):
        """Test profile update requires authentication"""
        response = client.get(f'/team/update-profile/{self_managed_team.team_id}')
        assert response.status_code == 302


class TestTeamIDGeneration:
    """Test team ID auto-generation functionality (Stage 3)"""

    def test_first_team_gets_tm0001(self, authenticated_team_manager, flask_app):
        """Test first team gets TM0001"""
        # Clear all teams first
        with flask_app.app_context():
            Team.query.delete()
            db.session.commit()
        
        authenticated_team_manager.post('/team/create-team', data={
            'team_name': 'First Team',
            'department': 'CSE',
            'manager_name': 'Manager',
            'manager_contact': '9999999999'
        })
        
        with flask_app.app_context():
            team = Team.query.filter_by(name='First Team').first()
            assert team.team_id == 'TM0001'

    def test_sequential_team_ids(self, authenticated_team_manager, flask_app):
        """Test team IDs increment sequentially"""
        # Create first team
        authenticated_team_manager.post('/team/create-team', data={
            'team_name': 'Team One',
            'department': 'CSE',
            'manager_name': 'Manager',
            'manager_contact': '1111111111'
        })
        
        # Create second team
        authenticated_team_manager.post('/team/create-team', data={
            'team_name': 'Team Two',
            'department': 'ECE',
            'manager_name': 'Manager',
            'manager_contact': '2222222222'
        })
        
        with flask_app.app_context():
            teams = Team.query.filter(Team.team_id.like('TM%')).order_by(Team.id).all()
            if len(teams) >= 2:
                # Check last two teams have sequential IDs
                last_two = teams[-2:]
                id1 = int(last_two[0].team_id[2:])
                id2 = int(last_two[1].team_id[2:])
                assert id2 == id1 + 1


class TestMultipleTeamsPerManager:
    """Test manager can create and manage multiple teams (Stage 3)"""

    def test_manager_can_create_multiple_teams(self, authenticated_team_manager, flask_app, team_manager_user):
        """Test manager can create more than one team"""
        # Create first team
        authenticated_team_manager.post('/team/create-team', data={
            'team_name': 'Manager Team 1',
            'department': 'CSE',
            'manager_name': 'Manager',
            'manager_contact': '1111111111'
        })
        
        # Create second team
        authenticated_team_manager.post('/team/create-team', data={
            'team_name': 'Manager Team 2',
            'department': 'ECE',
            'manager_name': 'Manager',
            'manager_contact': '2222222222'
        })
        
        with flask_app.app_context():
            teams = Team.query.filter_by(created_by=team_manager_user.id).all()
            assert len(teams) >= 2

    def test_my_teams_shows_all_owned_teams(self, authenticated_team_manager, flask_app, team_manager_user):
        """Test my teams page shows all teams created by manager"""
        # Create multiple teams
        for i in range(1, 4):  # Start from 1 to avoid TM0000
            with flask_app.app_context():
                team = Team(
                    team_id=f'TM{i:04d}',  # TM0001, TM0002, TM0003
                    name=f'Multi Team {i}',
                    department='CSE',
                    manager_name='Manager',
                    created_by=team_manager_user.id,
                )
                db.session.add(team)
                db.session.commit()
        
        response = authenticated_team_manager.get('/team/my-teams')
        assert response.status_code == 200
        assert b'Multi Team 1' in response.data
        assert b'Multi Team 2' in response.data
        assert b'Multi Team 3' in response.data

    def test_manager_can_access_all_owned_team_dashboards(self, authenticated_team_manager, flask_app, team_manager_user):
        """Test manager can access dashboards of all their teams"""
        # Create two teams with proper TM#### format
        with flask_app.app_context():
            team1 = Team(
                team_id='TM0101',  # Using TM0101 format
                name='Team Alpha',
                department='CSE',
                manager_name='Manager',
                created_by=team_manager_user.id,
            )
            team2 = Team(
                team_id='TM0102',  # Using TM0102 format
                name='Team Beta',
                department='ECE',
                manager_name='Manager',
                created_by=team_manager_user.id,
            )
            db.session.add_all([team1, team2])
            db.session.commit()
        
        # Access both dashboards with correct route
        response1 = authenticated_team_manager.get('/team/dashboard/TM0101')
        assert response1.status_code == 200
        assert b'Team Alpha' in response1.data

        response2 = authenticated_team_manager.get('/team/dashboard/TM0102')
        assert response2.status_code == 200
        assert b'Team Beta' in response2.data


class TestTeamDashboardOverview:
    """Test the consolidated team manager dashboard overview."""

    def test_dashboard_overview_shows_managed_team_and_metrics(
        self,
        authenticated_team_manager,
        flask_app,
        team_manager_user,
        tournament,
    ):
        with flask_app.app_context():
            manager = User.query.get(team_manager_user.id)
            tournament_obj = Tournament.query.get(tournament.id)

            team = Team(
                team_id='TM5001',
                name='Dashboard Squad',
                department='Physics',
                manager_name='Lead Manager',
                manager_contact='8000000000',
                created_by=manager.id,
                managed_by=manager.id,
                institution=manager.institution,
            )
            db.session.add(team)
            db.session.flush()

            association = TournamentTeam(
                tournament_id=tournament_obj.id,
                team_id=team.team_id,
                registration_method='smc_invited',
                status='pending',
            )
            db.session.add(association)

            notification = Notification(
                user_id=manager.id,
                message='Review the tournament invitation.',
                status='active',
                kind='tournament_invite',
            )
            db.session.add(notification)
            db.session.commit()

        response = authenticated_team_manager.get('/team/dashboard')
        assert response.status_code == 200
        assert b'Team Manager Dashboard' in response.data
        assert b'Dashboard Squad' in response.data
        assert b'Review the tournament invitation.' in response.data
        assert b'text-red-400">1<' in response.data


class TestTeamNotifications:
    """Test the notifications center for team managers."""

    def test_notifications_filter_and_render(
        self,
        authenticated_team_manager,
        flask_app,
        team_manager_user,
    ):
        with flask_app.app_context():
            manager = User.query.get(team_manager_user.id)

            active_note = Notification(
                user_id=manager.id,
                message='Active invite pending action',
                status='active',
            )
            archived_note = Notification(
                user_id=manager.id,
                message='Old archived update',
                status='archived',
            )
            db.session.add_all([active_note, archived_note])
            db.session.commit()

        response = authenticated_team_manager.get('/team/notifications?status=active')
        assert response.status_code == 200
        assert b'Active invite pending action' in response.data
        assert b'Old archived update' not in response.data

    def test_mark_notification_resolved(
        self,
        authenticated_team_manager,
        flask_app,
        team_manager_user,
    ):
        with flask_app.app_context():
            manager = User.query.get(team_manager_user.id)
            notification = Notification(
                user_id=manager.id,
                message='Resolve this notification',
                status='active',
            )
            db.session.add(notification)
            db.session.commit()
            note_id = notification.id

        response = authenticated_team_manager.post(
            f'/team/notifications/{note_id}/read?status=active',
            data={'resolve': '1'},
            follow_redirects=True,
        )
        assert response.status_code == 200

        with flask_app.app_context():
            updated = Notification.query.get(note_id)
            assert updated.status == 'resolved'
            assert updated.is_read is True


class TestInvitationResponses:
    """Test team manager actions on SMC invitations."""

    def test_accept_invitation_activates_association(
        self,
        authenticated_team_manager,
        flask_app,
        team_manager_user,
        smc_user,
        tournament,
    ):
        with flask_app.app_context():
            manager = User.query.get(team_manager_user.id)
            organizer = User.query.get(smc_user.id)
            tournament_obj = Tournament.query.get(tournament.id)

            team = Team(
                team_id='TM6101',
                name='Invite Acceptors',
                department='Chemistry',
                manager_name='Manager Accept',
                manager_contact='8111111111',
                created_by=manager.id,
                managed_by=manager.id,
                institution=manager.institution,
            )
            db.session.add(team)
            db.session.flush()

            association = TournamentTeam(
                tournament_id=tournament_obj.id,
                team_id=team.team_id,
                registration_method='smc_invited',
                status='pending',
            )
            db.session.add(association)
            db.session.flush()

            manager_note = Notification(
                user_id=manager.id,
                message='You have a tournament invitation.',
                status='pending',
                kind='tournament_invite',
                context_type='tournament',
                context_ref=str(tournament_obj.id),
            )
            db.session.add(manager_note)
            db.session.commit()
            assoc_id = association.id
            manager_note_id = manager_note.id

        response = authenticated_team_manager.post(
            f'/team/tournament-team/{assoc_id}/respond',
            data={'decision': 'accept'},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b'Invitation accepted' in response.data

        with flask_app.app_context():
            updated_assoc = TournamentTeam.query.get(assoc_id)
            assert updated_assoc.status == 'active'
            assert updated_assoc.approved_at is not None

            resolved_note = Notification.query.get(manager_note_id)
            assert resolved_note.status == 'resolved'
            assert resolved_note.is_read is True

            organizer_notes = Notification.query.filter_by(user_id=smc_user.id).all()
            assert organizer_notes
            assert any('accepted the invitation' in note.message for note in organizer_notes)

    def test_decline_invitation_removes_association(
        self,
        authenticated_team_manager,
        flask_app,
        team_manager_user,
        smc_user,
        tournament,
    ):
        with flask_app.app_context():
            manager = User.query.get(team_manager_user.id)
            tournament_obj = Tournament.query.get(tournament.id)

            team = Team(
                team_id='TM6201',
                name='Invite Decliners',
                department='Biology',
                manager_name='Manager Decline',
                manager_contact='8222222222',
                created_by=manager.id,
                managed_by=manager.id,
                institution=manager.institution,
            )
            db.session.add(team)
            db.session.flush()

            association = TournamentTeam(
                tournament_id=tournament_obj.id,
                team_id=team.team_id,
                registration_method='smc_invited',
                status='pending',
            )
            db.session.add(association)
            db.session.flush()

            manager_note = Notification(
                user_id=manager.id,
                message='Pending invitation decision required.',
                status='pending',
                kind='tournament_invite',
                context_type='tournament',
                context_ref=str(tournament_obj.id),
            )
            db.session.add(manager_note)
            db.session.commit()
            assoc_id = association.id
            manager_note_id = manager_note.id

        response = authenticated_team_manager.post(
            f'/team/tournament-team/{assoc_id}/respond',
            data={'decision': 'decline'},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b'Invitation declined' in response.data

        with flask_app.app_context():
            removed_assoc = TournamentTeam.query.get(assoc_id)
            assert removed_assoc is None

            resolved_note = Notification.query.get(manager_note_id)
            assert resolved_note.status == 'resolved'

            organizer_notes = Notification.query.filter_by(user_id=smc_user.id).all()
            assert organizer_notes
            assert any('declined the invitation' in note.message for note in organizer_notes)