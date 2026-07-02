from datetime import date, timedelta

import pytest


def _future_date(days):
    return (date.today() + timedelta(days=days)).isoformat()


def _place_order(api_client, customer_user, product, days=3):
    api_client.force_authenticate(user=customer_user.user)
    api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 2}, format='json')
    resp = api_client.post('/api/orders/create/', {
        'customer_id': customer_user.id,
        'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(days)}],
    }, format='json')
    return resp.json()


@pytest.mark.django_db
class TestProducerOrderView:
    """TC-009: producers see their incoming orders with customer/delivery details."""

    def test_producer_sees_own_incoming_order(self, api_client, customer_user, producer_user, product):
        _place_order(api_client, customer_user, product)
        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.get(f'/api/producer-orders/{producer_user.id}/')
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]['customer_name'] == customer_user.user.username
        assert data[0]['delivery_address'] == customer_user.address

    def test_producer_cannot_see_another_producers_orders(
        self, api_client, customer_user, producer_user, producer2_user, product,
    ):
        _place_order(api_client, customer_user, product)
        api_client.force_authenticate(user=producer2_user.user)
        resp = api_client.get(f'/api/producer-orders/{producer_user.id}/')
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.django_db
class TestOrderStatusProgression:
    """TC-010: producers update sub-order status one step at a time."""

    def test_producer_can_advance_status_one_step(self, api_client, customer_user, producer_user, product):
        order_data = _place_order(api_client, customer_user, product)
        suborder_id = order_data['suborders'][0]['id']

        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.patch(
            f'/api/producer-suborders/{suborder_id}/status/', {'status': 'confirmed'}, format='json',
        )
        assert resp.status_code == 200
        assert resp.json()['status'] == 'confirmed'

    def test_cannot_skip_a_status_step(self, api_client, customer_user, producer_user, product):
        order_data = _place_order(api_client, customer_user, product)
        suborder_id = order_data['suborders'][0]['id']

        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.patch(
            f'/api/producer-suborders/{suborder_id}/status/', {'status': 'ready'}, format='json',
        )
        assert resp.status_code == 400  # pending -> ready skips "confirmed"

    def test_full_progression_pending_to_delivered(self, api_client, customer_user, producer_user, product):
        order_data = _place_order(api_client, customer_user, product)
        suborder_id = order_data['suborders'][0]['id']
        api_client.force_authenticate(user=producer_user.user)

        for next_status in ['confirmed', 'ready', 'delivered']:
            resp = api_client.patch(
                f'/api/producer-suborders/{suborder_id}/status/', {'status': next_status}, format='json',
            )
            assert resp.status_code == 200
            assert resp.json()['status'] == next_status

    def test_other_producer_cannot_update_suborder_status(
        self, api_client, customer_user, producer_user, producer2_user, product,
    ):
        order_data = _place_order(api_client, customer_user, product)
        suborder_id = order_data['suborders'][0]['id']
        api_client.force_authenticate(user=producer2_user.user)
        resp = api_client.patch(
            f'/api/producer-suborders/{suborder_id}/status/', {'status': 'confirmed'}, format='json',
        )
        assert resp.status_code == 403