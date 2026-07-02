from datetime import date

import pytest

from django.utils import timezone


@pytest.mark.django_db
class TestSeasonalAvailability:
    """
    TC-016: seasonal availability with automatic date-based visibility.

    All tests are written relative to the real current month
    (`timezone.localdate().month`) rather than hard-coded months, so the
    suite stays correct no matter when it's run.
    """

    def test_year_round_product_has_no_season_label(self, api_client, product):
        resp = api_client.get('/api/products/')
        data = next(p for p in resp.json() if p['name'] == product.name)
        assert data['season_label'] is None
        assert data['is_in_season_now'] is True

    def test_product_in_current_season_is_visible(self, api_client, producer_user, product):
        current_month = timezone.localdate().month
        api_client.force_authenticate(user=producer_user.user)
        api_client.patch(f'/api/products/{product.id}/', {
            'season_start_month': current_month, 'season_end_month': current_month,
        }, format='json')

        resp = api_client.get('/api/products/?visible_only=true')
        assert product.name in [p['name'] for p in resp.json()]

    def test_product_outside_current_season_is_hidden(self, api_client, producer_user, product):
        # Pick the month exactly opposite the current one on the calendar,
        # so it's never accidentally the current month.
        current_month = timezone.localdate().month
        other_month = ((current_month + 5) % 12) + 1

        api_client.force_authenticate(user=producer_user.user)
        api_client.patch(f'/api/products/{product.id}/', {
            'season_start_month': other_month, 'season_end_month': other_month,
        }, format='json')

        resp = api_client.get('/api/products/?visible_only=true')
        assert product.name not in [p['name'] for p in resp.json()]

    def test_season_wraps_correctly_across_year_end(self, api_client, producer_user, product):
        # November through February, going "backwards" through the year
        # boundary. Whatever today's real month is, check the wraparound
        # logic gives the mathematically correct answer for it directly
        # via the model property (more reliable than picking a month that
        # might coincidentally be in Nov-Feb when the suite runs).
        product.season_start_month = 11
        product.season_end_month = 2
        expected = timezone.localdate().month in (11, 12, 1, 2)
        assert product.is_in_season_now == expected

    def test_season_label_is_human_readable(self, api_client, producer_user, product):
        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.patch(f'/api/products/{product.id}/', {
            'season_start_month': 6, 'season_end_month': 8,
        }, format='json')
        assert resp.json()['season_label'] == 'June \u2013 August'

    def test_setting_only_one_season_field_rejected(self, api_client, producer_user, product):
        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.patch(f'/api/products/{product.id}/', {
            'season_start_month': 3,
        }, format='json')
        assert resp.status_code == 400

    def test_out_of_stock_still_hides_regardless_of_season(self, api_client, producer_user, product):
        current_month = timezone.localdate().month
        api_client.force_authenticate(user=producer_user.user)
        api_client.patch(f'/api/products/{product.id}/', {
            'season_start_month': current_month, 'season_end_month': current_month,
            'stock_quantity': 0,
        }, format='json')
        resp = api_client.get('/api/products/?visible_only=true')
        assert product.name not in [p['name'] for p in resp.json()]

    def test_customer_cannot_add_out_of_season_product_to_cart(
        self, api_client, producer_user, customer_user, product,
    ):
        # This is the acceptance criterion that matters most for TC-016:
        # "customers cannot order out-of-season products." Cart
        # validation already keys off Product.is_visible, so this proves
        # the seasonal restriction is enforced at the point of purchase,
        # not just on the browse page.
        current_month = timezone.localdate().month
        other_month = ((current_month + 5) % 12) + 1

        api_client.force_authenticate(user=producer_user.user)
        api_client.patch(f'/api/products/{product.id}/', {
            'season_start_month': other_month, 'season_end_month': other_month,
        }, format='json')

        api_client.force_authenticate(user=customer_user.user)
        resp = api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        assert resp.status_code == 400