from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

class AccountsAuthenticationTests(TestCase):
    """
    Test suite for the authentication system, covering registration, login, 
    and path access protections (TC-01 through TC-05).
    """

    def setUp(self):
        # Create a test user for login cases
        self.username = "testuser"
        self.password = "ValidPass123!"
        self.email = "test@example.com"
        self.user = User.objects.create_user(
            username=self.username,
            password=self.password,
            email=self.email
        )

    def test_tc_01_user_signup_success(self):
        """TC-01: Valid user signup creates account, hashes password, and authenticates."""
        signup_url = reverse('signup')
        signup_data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': 'NewPassWord123!',
            'password2': 'NewPassWord123!'
        }
        response = self.client.post(signup_url, signup_data)
        
        # Verify redirect to home/dashboard
        self.assertEqual(response.status_code, 302)
        
        # Verify user exists in database
        user_exists = User.objects.filter(username='newuser').exists()
        self.assertTrue(user_exists)
        
        # Verify password is hashed properly
        new_user = User.objects.get(username='newuser')
        self.assertNotEqual(new_user.password, 'NewPassWord123!')
        self.assertTrue(new_user.check_password('NewPassWord123!'))

    def test_tc_02_invalid_signup_mismatched_passwords(self):
        """TC-02: Invalid signup with mismatched passwords fails registration."""
        signup_url = reverse('signup')
        signup_data = {
            'username': 'baduser',
            'email': 'bad@example.com',
            'password1': 'PassOne123!',
            'password2': 'PassTwo123!'
        }
        response = self.client.post(signup_url, signup_data)
        
        # Verify page reloads with form errors (status 200)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='baduser').exists())
        self.assertFormError(response.context['form'], 'password2', "The two password fields didn’t match.")

    def test_tc_03_login_success(self):
        """TC-03: Login with correct credentials establishes user session."""
        login_url = reverse('login')
        login_data = {
            'username': self.username,
            'password': self.password
        }
        response = self.client.post(login_url, login_data)
        
        # Verify redirect
        self.assertEqual(response.status_code, 302)
        
        # Verify user session is authenticated
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.id)

    def test_tc_04_login_failure(self):
        """TC-04: Login with incorrect password rejects session setup."""
        login_url = reverse('login')
        login_data = {
            'username': self.username,
            'password': 'wrongpassword'
        }
        response = self.client.post(login_url, login_data)
        
        # Should stay on page and render form error
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_tc_05_protected_route_redirects_unauthenticated_user(self):
        """TC-05: Unauthenticated access to protected routes redirects to login page."""
        protected_routes = [
            'manage_categories',
            'upload_transactions',
            'ai_sorting',
            'analytics_dashboard'
        ]
        for route_name in protected_routes:
            url = reverse(route_name)
            response = self.client.get(url)
            
            # Verify redirect to login page with next parameter
            self.assertEqual(response.status_code, 302)
            expected_redirect = f"{reverse('login')}?next={url}"
            self.assertRedirects(response, expected_redirect)
