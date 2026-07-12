from datetime import date, timedelta

import pytest


def _future_date(days):
    return (date.today() + timedelta(days=days)).isoformat()


@pytest.mark.django_db
class TestBulkOrders:
    """
    TC-017: a community group (or restaurant, or any institutional buyer)
    registers with an organisation name and segment, places a
    multi-producer order with delivery instructions, and producers can
    see who they're really dealing with.
    """

    def test_registration_accepts_organisation_name_and_segment(self, api_client):
        resp = api_client.post('/api/customers/register/', {
            'username': 'st_marys_kitchen',
            'email': 'catering@stmarysschool.org.uk',
            'password': 'SchoolMeals2026',
            'address': "St Mary's School, Whiteladies Road, Bristol",
            'postcode': 'BS8 2NN',
            'organisation_name': "St Mary's School",
            'segment': 'community_group',
        }, format='json')

        assert resp.status_code == 201
        from marketplace.models import CustomerProfile
        customer = CustomerProfile.objects.get(user__username='st_marys_kitchen')
        assert customer.organisation_name == "St Mary's School"
        assert customer.segment == 'community_group'

    def test_segment_defaults_to_household_when_not_given(self, api_client):
        resp = api_client.post('/api/customers/register/', {
            'username': 'ordinary_shopper',
            'email': 'shopper@example.com',
            'password': 'Password2026',
            'address': '1 Some Street, Bristol',
            'postcode': 'BS1 1AA',
        }, format='json')
        assert resp.status_code == 201
        from marketplace.models import CustomerProfile
        customer = CustomerProfile.objects.get(user__username='ordinary_shopper')
        assert customer.segment == 'household'
        assert customer.organisation_name == ''

    def test_special_instructions_saved_and_returned(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 2}, format='json')

        resp = api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
            'special_instructions': 'Deliver to the kitchen entrance, ask for the kitchen manager.',
        }, format='json')

        assert resp.status_code == 201
        assert resp.json()['special_instructions'] == (
            'Deliver to the kitchen entrance, ask for the kitchen manager.'
        )

    def test_special_instructions_blank_by_default(self, api_client, customer_user, product):
        """An ordinary household order shouldn't need to think about this field at all."""
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        resp = api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
        }, format='json')
        assert resp.status_code == 201
        assert resp.json()['special_instructions'] == ''

    def test_producer_sees_customer_organisation_and_instructions(
        self, api_client, customer_user, product,
    ):
        """
        The whole point of this feature: a producer fulfilling the order
        needs to know it's for an institution, not a household, and needs
        to see the delivery notes — without that, TC-017's "producers
        receive bulk order notifications" acceptance criterion is just
        cosmetic on the customer side.
        """
        customer_user.organisation_name = "St Mary's School"
        customer_user.segment = 'community_group'
        customer_user.save()

        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 5}, format='json')
        api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
            'special_instructions': 'Contact kitchen manager on arrival.',
        }, format='json')

        api_client.force_authenticate(user=product.producer.user)
        resp = api_client.get(f'/api/producer-orders/{product.producer.id}/')

        assert resp.status_code == 200
        suborder = resp.json()[0]
        assert suborder['customer_organisation'] == "St Mary's School"
        assert suborder['customer_segment'] == 'community_group'
        assert suborder['special_instructions'] == 'Contact kitchen manager on arrival.'

    def test_bulk_multi_producer_order_splits_correctly(
        self, api_client, customer_user, product, dairy_product,
    ):
        """
        Nothing about a "bulk" order actually needs new checkout logic —
        this just confirms a large, multi-producer institutional order
        goes through the same per-producer split as any other
        multi-vendor order (TC-008), at a bulk-sized quantity.
        """
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 20}, format='json')
        api_client.post('/api/cart/add/', {'product_id': dairy_product.id, 'quantity': 30}, format='json')

        resp = api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [
                {'producer_id': product.producer.id, 'delivery_date': _future_date(3)},
                {'producer_id': dairy_product.producer.id, 'delivery_date': _future_date(2)},
            ],
            'special_instructions': 'Delivery to school kitchen entrance only.',
        }, format='json')

        assert resp.status_code == 201
        data = resp.json()
        assert len(data['suborders']) == 2
        assert data['special_instructions'] == 'Delivery to school kitchen entrance only.'