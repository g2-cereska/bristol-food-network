from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone


@pytest.mark.django_db
class TestSurplusDeals:
    """TC-019: producers mark surplus stock as a discounted, time-limited deal."""

    def test_producer_can_mark_product_as_surplus(self, api_client, producer_user, product):
        api_client.force_authenticate(user=producer_user.user)
        expires_at = (timezone.now() + timedelta(hours=48)).isoformat()

        resp = api_client.patch(f'/api/products/{product.id}/', {
            'is_surplus': 'true',
            'discount_percent': 30,
            'surplus_expires_at': expires_at,
            'surplus_note': 'Perfect condition, must sell quickly to avoid waste',
        }, format='json')

        assert resp.status_code == 200
        data = resp.json()
        assert data['is_surplus'] is True
        assert data['is_surplus_active'] is True
        # £2.50 - 30% = £1.75
        assert Decimal(data['current_price']) == Decimal('1.75')

    def test_discount_outside_ten_to_fifty_percent_rejected(self, api_client, producer_user, product):
        api_client.force_authenticate(user=producer_user.user)
        expires_at = (timezone.now() + timedelta(hours=48)).isoformat()

        too_low = api_client.patch(f'/api/products/{product.id}/', {
            'is_surplus': 'true', 'discount_percent': 5, 'surplus_expires_at': expires_at,
        }, format='json')
        assert too_low.status_code == 400

        too_high = api_client.patch(f'/api/products/{product.id}/', {
            'is_surplus': 'true', 'discount_percent': 75, 'surplus_expires_at': expires_at,
        }, format='json')
        assert too_high.status_code == 400

    def test_surplus_without_expiry_rejected(self, api_client, producer_user, product):
        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.patch(f'/api/products/{product.id}/', {
            'is_surplus': 'true', 'discount_percent': 30,
        }, format='json')
        assert resp.status_code == 400

    def test_surplus_expiry_in_the_past_rejected(self, api_client, producer_user, product):
        api_client.force_authenticate(user=producer_user.user)
        expired = (timezone.now() - timedelta(hours=1)).isoformat()
        resp = api_client.patch(f'/api/products/{product.id}/', {
            'is_surplus': 'true', 'discount_percent': 30, 'surplus_expires_at': expired,
        }, format='json')
        assert resp.status_code == 400

    def test_surplus_only_filter_excludes_expired_deals(self, api_client, producer_user, category):
        from marketplace.models import Product

        active = Product.objects.create(
            producer=producer_user, category=category, name='Active Deal Lettuce',
            price=Decimal('2.00'), unit='head', stock_quantity=10, availability='available',
            is_surplus=True, discount_percent=30,
            surplus_expires_at=timezone.now() + timedelta(hours=24),
        )
        # Expired deal — is_surplus is still True, but the expiry has passed.
        # This is the "deal expiry is enforced automatically" case: nothing
        # ever flips is_surplus back to False, the query just stops
        # matching once surplus_expires_at is in the past.
        Product.objects.create(
            producer=producer_user, category=category, name='Expired Deal Bread',
            price=Decimal('3.00'), unit='loaf', stock_quantity=5, availability='available',
            is_surplus=True, discount_percent=30,
            surplus_expires_at=timezone.now() - timedelta(hours=1),
        )
        # Not a surplus deal at all.
        Product.objects.create(
            producer=producer_user, category=category, name='Regular Potatoes',
            price=Decimal('1.50'), unit='kg', stock_quantity=20, availability='available',
        )

        resp = api_client.get('/api/products/?surplus_only=true')
        assert resp.status_code == 200
        names = {item['name'] for item in resp.json()}
        assert names == {active.name}

    def test_producer_cannot_mark_another_producers_product_surplus(
        self, api_client, producer2_user, product,
    ):
        api_client.force_authenticate(user=producer2_user.user)
        expires_at = (timezone.now() + timedelta(hours=48)).isoformat()
        resp = api_client.patch(f'/api/products/{product.id}/', {
            'is_surplus': 'true', 'discount_percent': 30, 'surplus_expires_at': expires_at,
        }, format='json')
        assert resp.status_code == 403