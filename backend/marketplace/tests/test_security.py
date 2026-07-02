import pytest
from django.contrib.auth.models import User


@pytest.mark.django_db
class TestPasswordSecurity:
    """TC-022 (part 1): password policy and hashing."""

    def test_weak_password_rejected_on_registration(self, api_client):
        resp = api_client.post('/api/customers/register/', {
            'username': 'weakpass', 'email': 'weak@example.com', 'password': '123',
            'address': '1 St', 'postcode': 'BS1 1AA',
        }, format='json')
        assert resp.status_code == 400

    def test_all_lowercase_password_rejected(self, api_client):
        resp = api_client.post('/api/customers/register/', {
            'username': 'lowerpass', 'email': 'lower@example.com', 'password': 'alllowercase',
            'address': '1 St', 'postcode': 'BS1 1AA',
        }, format='json')
        assert resp.status_code == 400

    def test_password_stored_hashed(self, api_client):
        api_client.post('/api/customers/register/', {
            'username': 'hashcheck', 'email': 'hc@example.com', 'password': 'ValidPass22',
            'address': '1 St', 'postcode': 'BS1 1AA',
        }, format='json')
        user = User.objects.get(username='hashcheck')
        assert user.password != 'ValidPass22'


@pytest.mark.django_db
class TestLoginSecurity:
    """TC-022 (part 2): login attempts and session handling."""

    def test_wrong_password_rejected(self, api_client, customer_user):
        resp = api_client.post('/api/auth/login/', {
            'username': customer_user.user.username, 'password': 'wrong-password',
        }, format='json')
        assert resp.status_code == 400

    def test_correct_credentials_succeed(self, api_client, customer_user):
        resp = api_client.post('/api/auth/login/', {
            'username': customer_user.user.username, 'password': 'Password123!',
        }, format='json')
        assert resp.status_code == 200

    def test_error_does_not_reveal_whether_username_exists(self, api_client, customer_user):
        real_user_resp = api_client.post('/api/auth/login/', {
            'username': customer_user.user.username, 'password': 'wrong',
        }, format='json')
        fake_user_resp = api_client.post('/api/auth/login/', {
            'username': 'does_not_exist_xyz', 'password': 'wrong',
        }, format='json')
        assert real_user_resp.json() == fake_user_resp.json()

    def test_logout_ends_session(self, api_client, customer_user):
        # Uses a real session login/logout cycle (not force_authenticate,
        # which bypasses sessions entirely) to prove the session is
        # actually terminated, not just that the client forgot its token.
        api_client.login(username=customer_user.user.username, password='Password123!')
        authenticated_resp = api_client.get('/api/orders/')
        assert authenticated_resp.status_code == 200

        api_client.logout()
        after_logout_resp = api_client.get(f'/api/cart/{customer_user.id}/')
        assert after_logout_resp.status_code in (401, 403)


@pytest.mark.django_db
class TestAuthorisation:
    """TC-022 (part 3): role-based access control."""

    def test_customer_cannot_access_producer_only_endpoint(self, api_client, customer_user, category):
        api_client.force_authenticate(user=customer_user.user)
        resp = api_client.post('/api/products/', {
            'category': category.id, 'name': 'x', 'price': '1.00', 'unit': 'kg',
        }, format='json')
        assert resp.status_code == 403

    def test_producer_cannot_view_another_producers_order_details(self, api_client, producer_user, producer2_user):
        api_client.force_authenticate(user=producer2_user.user)
        resp = api_client.get(f'/api/producer-orders/{producer_user.id}/')
        assert resp.status_code == 200
        assert resp.json() == []

    def test_anonymous_user_cannot_access_cart(self, api_client, customer_user):
        resp = api_client.get(f'/api/cart/{customer_user.id}/')
        assert resp.status_code in (401, 403)

    def test_customer_cannot_access_admin_dashboard(self, api_client, customer_user):
        api_client.force_authenticate(user=customer_user.user)
        resp = api_client.get('/api/admin-dashboard/')
        assert resp.status_code == 403

    def test_producer_cannot_access_admin_dashboard(self, api_client, producer_user):
        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.get('/api/admin-dashboard/')
        assert resp.status_code == 403