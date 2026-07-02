from datetime import date, timedelta

import pytest


def _future_date(days):
    return (date.today() + timedelta(days=days)).isoformat()


@pytest.mark.django_db
class TestOrderHistory:
    """TC-021: customer can view their own order history, and only their own."""

    def test_customer_sees_own_orders(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
        }, format='json')

        resp = api_client.get('/api/orders/')
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_customer_cannot_see_other_customers_orders(
        self, api_client, customer_user, product, django_user_model,
    ):
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
        }, format='json')

        from marketplace.models import Cart, CustomerProfile
        other_user = django_user_model.objects.create_user(username='other_cust', password='Password123!')
        other_customer = CustomerProfile.objects.create(user=other_user, address='2 Other St', postcode='BS2 1AA')
        Cart.objects.create(customer=other_customer)

        api_client.force_authenticate(user=other_user)
        resp = api_client.get('/api/orders/')
        assert resp.json() == []

    def test_orders_sorted_most_recent_first(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        for _ in range(2):
            product.refresh_from_db()
            api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
            api_client.post('/api/orders/create/', {
                'customer_id': customer_user.id,
                'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
            }, format='json')
        resp = api_client.get('/api/orders/')
        ids = [o['id'] for o in resp.json()]
        assert ids == sorted(ids, reverse=True)