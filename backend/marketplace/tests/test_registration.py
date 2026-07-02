import pytest
from django.contrib.auth.models import User

from marketplace.models import CustomerProfile, ProducerProfile


@pytest.mark.django_db
class TestProducerRegistration:
    """TC-001: producer registration."""

    def test_valid_registration_creates_producer_account(self, api_client):
        resp = api_client.post('/api/producers/register/', {
            'username': 'jane_valley',
            'email': 'jane@bristolvalleyfarm.com',
            'password': 'GrowFresh2026',
            'business_name': 'Bristol Valley Farm',
            'contact_name': 'Jane Smith',
            'phone': '01179123456',
            'business_address': '1 Farm Lane, Bristol',
            'postcode': 'bs1 4dj',
        }, format='json')
        assert resp.status_code == 201
        assert ProducerProfile.objects.filter(business_name='Bristol Valley Farm').exists()

    def test_password_is_hashed_not_plaintext(self, api_client):
        api_client.post('/api/producers/register/', {
            'username': 'hash_check', 'email': 'hash@example.com', 'password': 'GrowFresh2026',
            'business_name': 'Hash Farm',
        }, format='json')
        user = User.objects.get(username='hash_check')
        assert user.password != 'GrowFresh2026'
        assert user.check_password('GrowFresh2026')

    def test_postcode_is_normalised(self, api_client):
        api_client.post('/api/producers/register/', {
            'username': 'postcode_check', 'email': 'pc@example.com', 'password': 'GrowFresh2026',
            'business_name': 'Postcode Farm', 'postcode': 'bs1 4dj',
        }, format='json')
        producer = ProducerProfile.objects.get(business_name='Postcode Farm')
        # .upper().strip() uppercases and trims outer whitespace, but does
        # NOT remove the internal space — 'bs1 4dj' -> 'BS1 4DJ'.
        assert producer.postcode == 'BS1 4DJ'

    def test_registered_producer_can_log_in(self, api_client):
        api_client.post('/api/producers/register/', {
            'username': 'login_check', 'email': 'lc@example.com', 'password': 'GrowFresh2026',
            'business_name': 'Login Farm',
        }, format='json')
        resp = api_client.post('/api/auth/login/', {
            'username': 'login_check', 'password': 'GrowFresh2026',
        }, format='json')
        assert resp.status_code == 200
        assert resp.json()['role'] == 'producer'

    def test_duplicate_username_rejected(self, api_client, producer_user):
        resp = api_client.post('/api/producers/register/', {
            'username': producer_user.user.username, 'email': 'other@example.com',
            'password': 'GrowFresh2026', 'business_name': 'Duplicate Farm',
        }, format='json')
        assert resp.status_code == 400


@pytest.mark.django_db
class TestCustomerRegistration:
    """TC-002: customer registration."""

    def test_valid_registration_creates_customer_and_cart(self, api_client):
        resp = api_client.post('/api/customers/register/', {
            'username': 'robert_j', 'email': 'robert@example.com', 'password': 'BasketFull22',
            'address': '45 Park Street, Bristol', 'postcode': 'bs1 5jg',
        }, format='json')
        assert resp.status_code == 201
        customer = CustomerProfile.objects.get(user__username='robert_j')
        assert hasattr(customer, 'cart')  # every new customer gets an empty cart, ready to use

    def test_missing_address_rejected(self, api_client):
        resp = api_client.post('/api/customers/register/', {
            'username': 'no_address', 'email': 'na@example.com', 'password': 'BasketFull22',
            'postcode': 'bs1 5jg',
        }, format='json')
        assert resp.status_code == 400

    def test_duplicate_email_rejected(self, api_client, customer_user):
        resp = api_client.post('/api/customers/register/', {
            'username': 'someone_new', 'email': customer_user.user.email,
            'password': 'BasketFull22', 'address': '1 St', 'postcode': 'BS1 1AA',
        }, format='json')
        assert resp.status_code == 400