import pytest


@pytest.mark.django_db
class TestLowStockAlerts:
    """TC-023: producers get notified when a product's stock runs low."""

    def test_producer_can_set_threshold(self, api_client, producer_user, product):
        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.patch(f'/api/products/{product.id}/', {
            'low_stock_threshold': 10,
        }, format='json')
        assert resp.status_code == 200
        assert resp.json()['low_stock_threshold'] == 10

    def test_stock_above_threshold_is_not_flagged(self, api_client, producer_user, product):
        # Fixture starts at 20 units in stock.
        product.low_stock_threshold = 10
        product.save()
        resp = api_client.get(f'/api/products/{product.id}/')
        assert resp.json()['is_low_stock'] is False

    def test_stock_at_or_below_threshold_is_flagged(self, api_client, producer_user, product):
        product.low_stock_threshold = 10
        product.stock_quantity = 9
        product.save()
        resp = api_client.get(f'/api/products/{product.id}/')
        assert resp.json()['is_low_stock'] is True

    def test_checkout_pushing_stock_below_threshold_triggers_the_flag(
        self, api_client, customer_user, producer_user, product,
    ):
        """
        The regression case this feature actually exists for: stock
        crossing the threshold *as a side effect of a checkout*, not just
        a manual stock edit — proving the alert is genuinely live rather
        than only updated when a producer happens to save the product.
        """
        from datetime import date, timedelta

        product.low_stock_threshold = 15
        product.save()  # stock_quantity=20, threshold=15 — not low yet

        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 6}, format='json')
        api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{
                'producer_id': product.producer.id,
                'delivery_date': (date.today() + timedelta(days=3)).isoformat(),
            }],
        }, format='json')

        product.refresh_from_db()
        assert product.stock_quantity == 14  # 20 - 6, now at/below threshold of 15
        resp = api_client.get(f'/api/products/{product.id}/')
        assert resp.json()['is_low_stock'] is True

    def test_no_threshold_set_never_flags_as_low_stock(self, api_client, producer_user, product):
        product.stock_quantity = 0
        product.save()
        resp = api_client.get(f'/api/products/{product.id}/')
        assert resp.json()['low_stock_threshold'] is None
        assert resp.json()['is_low_stock'] is False

    def test_low_stock_only_filter_scoped_to_one_producer(
        self, api_client, producer_user, producer2_user, category, dairy_category,
    ):
        from marketplace.models import Product

        low = Product.objects.create(
            producer=producer_user, category=category, name='Low Stock Carrots',
            price='2.00', unit='kg', stock_quantity=2, availability='available',
            low_stock_threshold=5,
        )
        Product.objects.create(
            producer=producer_user, category=category, name='Well Stocked Apples',
            price='2.00', unit='kg', stock_quantity=50, availability='available',
            low_stock_threshold=5,
        )
        # Another producer's own low-stock product — included when querying
        # without a producer filter, excluded once ?producer= narrows it.
        Product.objects.create(
            producer=producer2_user, category=dairy_category, name='Low Stock Milk',
            price='1.40', unit='unit', stock_quantity=1, availability='available',
            low_stock_threshold=3,
        )

        resp = api_client.get(f'/api/products/?low_stock_only=true&producer={producer_user.id}')
        assert resp.status_code == 200
        names = {item['name'] for item in resp.json()}
        assert names == {low.name}