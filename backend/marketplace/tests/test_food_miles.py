from datetime import date, timedelta
from decimal import Decimal

import pytest


def _future_date(days):
    return (date.today() + timedelta(days=days)).isoformat()


@pytest.mark.django_db
class TestFoodMiles:
    """
    TC-013 (partial — see README 'Known limitations'): food miles are
    calculated correctly at order level. Per-product display on the
    catalogue page before purchase is a documented, deliberate gap and
    is not covered here.
    """

    def test_order_records_food_miles_for_known_postcodes(self, api_client, customer_user, product):
        # producer_user's postcode is 'BS1 4DJ' and customer_user's is
        # 'BS1 5JG'. It's tempting to assume these share the 'BS1'
        # outward code and so resolve to the same lookup-table sector —
        # but the sector matcher tries a 4-character prefix first, and
        # Bristol has real, distinct sectors keyed 'BS14' and 'BS15' in
        # the lookup table, so these two postcodes actually match two
        # different sectors and get a real haversine distance between
        # them, not the "same sector" 0.5-mile shortcut.
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        resp = api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
        }, format='json')
        assert Decimal(resp.json()['food_miles_total']) == Decimal('4.66')

    def test_food_miles_is_zero_hop_within_the_same_lookup_sector(self, api_client, customer_user, product):
        # Move the producer to a postcode that genuinely shares customer_user's
        # 'BS15' sector, to also exercise the actual same-sector shortcut.
        product.producer.postcode = 'BS15 9YY'
        product.producer.save()
        customer_user.postcode = 'BS15 2AA'
        customer_user.save()

        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        resp = api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
        }, format='json')
        assert Decimal(resp.json()['food_miles_total']) == Decimal('0.5')