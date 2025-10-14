"""
Integration tests for auth blueprint - testing new user registration and login routes added in Stage 1
Tests /auth/register, /auth/login, /auth/logout routes
"""
from models import db, User


class TestAuthRegistrationRoute:
    """Test new /auth/register route (Stage 1)"""

    def test_register_page_loads(self, client):
        """Test registration page renders"""
        response = client.get('/auth/register')
        assert response.status_code == 200
        assert b'register' in response.data.lower() or b'role' in response.data.lower()

    def test_smc_registration_success(self, client):
        """Test successful SMC registration via new route"""
        response = client.post('/auth/register', data={
            'username': 'newsmc',
            'email': 'newsmc@test.com',
            'password': 'NewSmc@123',  # Meets validation
            'role': 'smc',
            'institution': 'Tech University',
        })
        
        # Should redirect after success
        assert response.status_code == 302
        
        # Verify user created with correct role
        user = User.query.filter_by(username='newsmc').first()
        assert user is not None
        assert user.role == 'smc'
        assert user.email == 'newsmc@test.com'

    def test_smc_registration_allows_missing_institution(self, client):
        """SMC registration should allow optional institution field."""
        response = client.post('/auth/register', data={
            'username': 'missinginst',
            'email': 'missing@test.com',
            'password': 'Valid@123',
            'role': 'smc',
        })

        assert response.status_code == 302
        user = User.query.filter_by(username='missinginst').first()
        assert user is not None
        assert user.institution is None

    def test_team_manager_registration_success(self, client):
        """Test successful team manager registration via new route"""
        response = client.post('/auth/register', data={
            'username': 'newmanager',
            'email': 'newmanager@test.com',
            'password': 'Manager@123',  # Meets validation
            'role': 'team_manager'
        })
        
        assert response.status_code == 302
        
        user = User.query.filter_by(username='newmanager').first()
        assert user is not None
        assert user.role == 'team_manager'

    def test_registration_duplicate_username(self, client, smc_user):
        """Test cannot register with existing username"""
        response = client.post('/auth/register', data={
            'username': 'test_smc',  # Already exists
            'email': 'different@test.com',
            'password': 'Test@123',
            'role': 'smc',
            'institution': 'Tech University',
        }, follow_redirects=True)
        
        assert b'Username already exists' in response.data

    def test_registration_duplicate_email(self, client, smc_user):
        """Test cannot register with existing email"""
        response = client.post('/auth/register', data={
            'username': 'differentuser',
            'email': 'smc@test.com',  # Already exists
            'password': 'Test@123',
            'role': 'smc',
            'institution': 'Tech University',
        }, follow_redirects=True)
        
        assert b'Email already registered' in response.data

    def test_registration_short_username(self, client):
        """Test registration validates username length"""
        response = client.post('/auth/register', data={
            'username': 'ab',  # Too short
            'email': 'user@test.com',
            'password': 'Test@123',
            'role': 'smc',
            'institution': 'Tech University',
        }, follow_redirects=True)
        
        assert b'at least 3 characters' in response.data.lower()

    def test_registration_short_password(self, client):
        """Test registration validates password length"""
        response = client.post('/auth/register', data={
            'username': 'newuser',
            'email': 'user@test.com',
            'password': 'Short1!',  # Only 7 chars
            'role': 'smc',
            'institution': 'Tech University',
        }, follow_redirects=True)
        
        assert b'at least 8 characters' in response.data.lower()

    def test_registration_password_no_uppercase(self, client):
        """Test registration validates password has uppercase"""
        response = client.post('/auth/register', data={
            'username': 'newuser',
            'email': 'user@test.com',
            'password': 'test@123',  # No uppercase
            'role': 'smc',
            'institution': 'Tech University',
        }, follow_redirects=True)
        
        assert b'uppercase' in response.data.lower()

    def test_registration_password_no_lowercase(self, client):
        """Test registration validates password has lowercase"""
        response = client.post('/auth/register', data={
            'username': 'newuser',
            'email': 'user@test.com',
            'password': 'TEST@123',  # No lowercase
            'role': 'smc',
            'institution': 'Tech University',
        }, follow_redirects=True)
        
        assert b'lowercase' in response.data.lower()

    def test_registration_password_no_digit(self, client):
        """Test registration validates password has digit"""
        response = client.post('/auth/register', data={
            'username': 'newuser',
            'email': 'user@test.com',
            'password': 'Test@test',  # No digit
            'role': 'smc',
            'institution': 'Tech University',
        }, follow_redirects=True)
        
        assert b'number' in response.data.lower() or b'digit' in response.data.lower()

    def test_registration_password_no_special(self, client):
        """Test registration validates password has special character"""
        response = client.post('/auth/register', data={
            'username': 'newuser',
            'email': 'user@test.com',
            'password': 'Test1234',  # No special char
            'role': 'smc',
            'institution': 'Tech University',
        }, follow_redirects=True)
        
        assert b'special character' in response.data.lower()

    def test_registration_invalid_email(self, client):
        """Test registration validates email format"""
        response = client.post('/auth/register', data={
            'username': 'newuser',
            'email': 'notanemail',  # Invalid email
            'password': 'Test@123',
            'role': 'smc',
            'institution': 'Tech University',
        }, follow_redirects=True)
        
        assert b'email' in response.data.lower()

    def test_registration_invalid_role(self, client):
        """Test registration validates role"""
        response = client.post('/auth/register', data={
            'username': 'newuser',
            'email': 'user@test.com',
            'password': 'Test@123',
            'role': 'invalid_role'
        }, follow_redirects=True)
        
        assert b'role' in response.data.lower()


class TestAuthLoginRoute:
    """Test new /auth/login route (Stage 1)"""

    def test_login_page_loads(self, client):
        """Test login page renders"""
        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'login' in response.data.lower() or b'username' in response.data.lower()

    def test_smc_login_success_via_new_route(self, client, smc_user):
        """Test successful SMC login via new unified route"""
        response = client.post('/auth/login', data={
            'username': 'test_smc',
            'password': 'Test@123'
        })
        
        # Should redirect to SMC dashboard
        assert response.status_code == 302
        assert 'smc' in response.location.lower()

    def test_team_manager_login_success_via_new_route(self, client, team_manager_user):
        """Test successful team manager login via new unified route"""
        response = client.post('/auth/login', data={
            'username': 'test_manager',
            'password': 'Manager@123'
        })
        
        assert response.status_code == 302
        assert 'team' in response.location.lower()

    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials"""
        response = client.post('/auth/login', data={
            'username': 'nonexistent',
            'password': 'Test@123'
        }, follow_redirects=True)
        
        assert b'Invalid username or password' in response.data

    def test_login_wrong_password(self, client, smc_user):
        """Test login with wrong password"""
        response = client.post('/auth/login', data={
            'username': 'test_smc',
            'password': 'Wrong@123'
        }, follow_redirects=True)
        
        assert b'Invalid username or password' in response.data

    def test_login_sets_session_keys(self, client, smc_user):
        """Test login sets session variables correctly"""
        client.post('/auth/login', data={
            'username': 'test_smc',
            'password': 'Test@123'
        })
        
        # Verify can access protected SMC page
        response = client.get('/smc-dashboard')
        assert response.status_code == 200

    def test_login_role_based_redirect_smc(self, client, smc_user):
        """Test SMC login redirects to SMC dashboard"""
        response = client.post('/auth/login', data={
            'username': 'test_smc',
            'password': 'Test@123'
        }, follow_redirects=True)
        
        assert response.status_code == 200

    def test_login_role_based_redirect_team_manager(self, client, team_manager_user):
        """Test team manager login redirects to team dashboard"""
        response = client.post('/auth/login', data={
            'username': 'test_manager',
            'password': 'Manager@123'
        }, follow_redirects=True)
        
        assert response.status_code == 200


class TestAuthLogoutRoute:
    """Test new /auth/logout route (Stage 1)"""

    def test_logout_clears_session_smc(self, client, smc_user):
        """Test logout clears SMC session"""
        # Login first
        client.post('/auth/login', data={
            'username': 'test_smc',
            'password': 'Test@123'
        })
        
        # Logout
        response = client.get('/auth/logout', follow_redirects=True)
        assert b'logged out' in response.data.lower()
        
        # Verify session cleared by trying to access protected page
        response = client.get('/smc-dashboard')
        assert response.status_code == 302  # Should redirect to login

    def test_logout_clears_session_team_manager(self, client, team_manager_user):
        """Test logout clears team manager session"""
        # Login first
        client.post('/auth/login', data={
            'username': 'test_manager',
            'password': 'Manager@123'
        })
        
        # Logout
        response = client.get('/auth/logout', follow_redirects=True)
        assert b'logged out' in response.data.lower()
        
        # Verify session cleared by trying to access protected page
        response = client.get('/team-dashboard')
        assert response.status_code == 302  # Should redirect to login


class TestUserModel:
    """Test User model - validation methods (Stage 1)"""

    def test_validate_format_valid_data(self):
        """Test validate_format passes for valid input"""
        errors = User.validate_format(
            username='newuser',
            email='user@test.com',
            password='Test@123',
            role='smc'
        )
        
        assert errors == []

    def test_validate_format_short_username(self):
        """Test validate_format catches short username"""
        errors = User.validate_format(
            username='ab',
            email='user@test.com',
            password='Test@123',
            role='smc'
        )
        
        assert len(errors) > 0
        assert any('Username must be at least 3 characters' in e for e in errors)

    def test_validate_format_short_password(self):
        """Test validate_format catches short password"""
        errors = User.validate_format(
            username='validuser',
            email='user@test.com',
            password='Test@1',  # Only 6 chars
            role='smc'
        )
        
        assert len(errors) > 0
        assert any('at least 8 characters' in e for e in errors)

    def test_validate_format_password_no_uppercase(self):
        """Test validate_format catches password without uppercase"""
        errors = User.validate_format(
            username='validuser',
            email='user@test.com',
            password='test@123',
            role='smc'
        )
        
        assert len(errors) > 0
        assert any('uppercase' in e.lower() for e in errors)

    def test_validate_format_password_no_lowercase(self):
        """Test validate_format catches password without lowercase"""
        errors = User.validate_format(
            username='validuser',
            email='user@test.com',
            password='TEST@123',
            role='smc'
        )
        
        assert len(errors) > 0
        assert any('lowercase' in e.lower() for e in errors)

    def test_validate_format_password_no_digit(self):
        """Test validate_format catches password without digit"""
        errors = User.validate_format(
            username='validuser',
            email='user@test.com',
            password='Test@test',
            role='smc'
        )
        
        assert len(errors) > 0
        assert any('number' in e.lower() or 'digit' in e.lower() for e in errors)

    def test_validate_format_password_no_special(self):
        """Test validate_format catches password without special character"""
        errors = User.validate_format(
            username='validuser',
            email='user@test.com',
            password='Test1234',
            role='smc'
        )
        
        assert len(errors) > 0
        assert any('special character' in e.lower() for e in errors)

    def test_validate_format_invalid_email(self):
        """Test validate_format catches invalid email"""
        errors = User.validate_format(
            username='validuser',
            email='notanemail',
            password='Test@123',
            role='smc'
        )
        
        assert len(errors) > 0
        assert any('email' in e.lower() for e in errors)

    def test_validate_format_invalid_role(self):
        """Test validate_format catches invalid role"""
        errors = User.validate_format(
            username='validuser',
            email='user@test.com',
            password='Test@123',
            role='invalid'
        )
        
        assert len(errors) > 0
        assert any('role' in e.lower() for e in errors)

    def test_user_password_hashing(self):
        """Test user password is hashed correctly"""
        user = User(username='test', email='test@test.com', role='smc')
        user.set_password('Test@123')
        
        assert user.password_hash != 'Test@123'
        assert len(user.password_hash) > 50

    def test_user_check_password_correct(self):
        """Test check_password returns True for correct password"""
        user = User(username='test', email='test@test.com', role='smc')
        user.set_password('Test@123')
        
        assert user.check_password('Test@123') is True

    def test_user_check_password_incorrect(self):
        """Test check_password returns False for incorrect password"""
        user = User(username='test', email='test@test.com', role='smc')
        user.set_password('Test@123')
        
        assert user.check_password('Wrong@123') is False