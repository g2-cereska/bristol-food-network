from datetime import date, timedelta
from decimal import Decimal

import pytest


def _future_date(days):
    return (date.today() + timedelta(days=days)).isoformat()


@pytest.mark.django_db
class TestSingleProducerCheckout:
    """TC-007: checkout from a single producer, with correct 5%/95% commission split."""

    def test_checkout_creates_order_with_correct_commission_split(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 4}, format='json')  # £2.50 x 4

        resp = api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
        }, format='json')

        assert resp.status_code == 201
        data = resp.json()
        assert Decimal(data['total_amount']) == Decimal('10.00')
        assert Decimal(data['commission_amount']) == Decimal('0.50')
        assert data['status'] == 'pending'
        assert len(data['suborders']) == 1
        assert Decimal(data['suborders'][0]['producer_payout']) == Decimal('9.50')

    def test_checkout_rejects_delivery_date_before_lead_time(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        resp = api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(0)}],
        }, format='json')
        assert resp.status_code == 400  # this producer needs 48h notice — "today" is too soon

    def test_checkout_with_empty_cart_rejected(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        resp = api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
        }, format='json')
        assert resp.status_code == 400

    def test_checkout_decrements_stock(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        original_stock = product.stock_quantity
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 3}, format='json')
        api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
        }, format='json')
        product.refresh_from_db()
        assert product.stock_quantity == original_stock - 3

    def test_checkout_empties_cart(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
        }, format='json')
        cart_resp = api_client.get(f'/api/cart/{customer_user.id}/')
        assert cart_resp.json()['items'] == []


@pytest.mark.django_db
class TestMultiProducerCheckout:
    """TC-008: checkout spanning multiple producers, split into independent sub-orders."""

    def test_checkout_splits_into_one_suborder_per_producer(self, api_client, customer_user, product, dairy_product):
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 2}, format='json')        # £5.00
        api_client.post('/api/cart/add/', {'product_id': dairy_product.id, 'quantity': 3}, format='json')  # £4.20

        resp = api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [
                {'producer_id': product.producer.id, 'delivery_date': _future_date(3)},
                {'producer_id': dairy_product.producer.id, 'delivery_date': _future_date(2)},
            ],
        }, format='json')

        assert resp.status_code == 201
        data = resp.json()
        assert len(data['suborders']) == 2
        assert Decimal(data['total_amount']) == Decimal('9.20')
        assert Decimal(data['commission_amount']) == Decimal('0.46')

    def test_checkout_missing_delivery_date_for_one_producer_rejected(self, api_client, customer_user, product, dairy_product):
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        api_client.post('/api/cart/add/', {'product_id': dairy_product.id, 'quantity': 1}, format='json')
        resp = api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
            # no delivery date supplied for dairy_product's producer
        }, format='json')
        assert resp.status_code == 400

    def test_each_suborder_has_independent_subtotal(self, api_client, customer_user, product, dairy_product):
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 2}, format='json')
        api_client.post('/api/cart/add/', {'product_id': dairy_product.id, 'quantity': 1}, format='json')
        resp = api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [
                {'producer_id': product.producer.id, 'delivery_date': _future_date(3)},
                {'producer_id': dairy_product.producer.id, 'delivery_date': _future_date(2)},
            ],
        }, format='json')
        subtotals = {s['producer']: Decimal(s['subtotal']) for s in resp.json()['suborders']}
        assert subtotals[product.producer.id] == Decimal('5.00')
        assert subtotals[dairy_product.producer.id] == Decimal('1.40')