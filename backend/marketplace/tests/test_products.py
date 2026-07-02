import pytest

from marketplace.models import Product


@pytest.mark.django_db
class TestProductListing:
    """TC-003: producers list products; product is linked to the authenticated producer only."""

    def test_producer_can_create_product(self, api_client, producer_user, category):
        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.post('/api/products/', {
            'category': category.id, 'name': 'Organic Free Range Eggs',
            'description': 'Fresh organic eggs.', 'price': '3.50', 'unit': 'dozen',
            'stock_quantity': 50, 'availability': 'available', 'allergen_info': 'Contains eggs',
        }, format='json')
        assert resp.status_code == 201
        product = Product.objects.get(name='Organic Free Range Eggs')
        assert product.producer == producer_user

    def test_customer_cannot_create_product(self, api_client, customer_user, category):
        api_client.force_authenticate(user=customer_user.user)
        resp = api_client.post('/api/products/', {
            'category': category.id, 'name': 'Not Allowed', 'price': '1.00', 'unit': 'kg',
        }, format='json')
        assert resp.status_code == 403

    def test_anonymous_cannot_create_product(self, api_client, category):
        resp = api_client.post('/api/products/', {
            'category': category.id, 'name': 'Not Allowed', 'price': '1.00', 'unit': 'kg',
        }, format='json')
        assert resp.status_code in (401, 403)


@pytest.mark.django_db
class TestCategoryBrowsing:
    """TC-004: browse by category; unavailable/out-of-stock items hidden."""

    def test_category_filter_returns_only_matching_products(self, api_client, product, dairy_product):
        resp = api_client.get(f'/api/products/?category={product.category.slug}')
        names = [p['name'] for p in resp.json()]
        assert product.name in names
        assert dairy_product.name not in names

    def test_out_of_stock_product_hidden_when_visible_only(self, api_client, product):
        product.stock_quantity = 0
        product.save()
        resp = api_client.get('/api/products/?visible_only=true')
        assert product.name not in [p['name'] for p in resp.json()]

    def test_unavailable_status_hidden_when_visible_only(self, api_client, product):
        product.availability = 'unavailable'
        product.save()
        resp = api_client.get('/api/products/?visible_only=true')
        assert product.name not in [p['name'] for p in resp.json()]

    def test_available_in_stock_product_shown_when_visible_only(self, api_client, product):
        resp = api_client.get('/api/products/?visible_only=true')
        assert product.name in [p['name'] for p in resp.json()]


@pytest.mark.django_db
class TestSearch:
    """TC-005: search by name/description/producer, case-insensitive."""

    def test_search_matches_product_name(self, api_client, product):
        resp = api_client.get('/api/products/?search=carrots')
        assert product.name in [p['name'] for p in resp.json()]

    def test_search_is_case_insensitive(self, api_client, product):
        resp = api_client.get('/api/products/?search=CARROTS')
        assert product.name in [p['name'] for p in resp.json()]

    def test_search_matches_producer_business_name(self, api_client, product):
        resp = api_client.get(f'/api/products/?search={product.producer.business_name}')
        assert product.name in [p['name'] for p in resp.json()]

    def test_search_no_match_returns_empty_not_error(self, api_client, product):
        resp = api_client.get('/api/products/?search=nonexistentproductxyz')
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.django_db
class TestInventoryUpdate:
    """TC-011: producers update stock/availability, only for their own products."""

    def test_producer_can_update_own_stock(self, api_client, producer_user, product):
        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.patch(f'/api/products/{product.id}/', {'stock_quantity': 35}, format='json')
        assert resp.status_code == 200
        product.refresh_from_db()
        assert product.stock_quantity == 35

    def test_producer_cannot_update_another_producers_product(self, api_client, producer2_user, product):
        api_client.force_authenticate(user=producer2_user.user)
        resp = api_client.patch(f'/api/products/{product.id}/', {'stock_quantity': 999}, format='json')
        assert resp.status_code == 403
        product.refresh_from_db()
        assert product.stock_quantity != 999

    def test_availability_change_takes_effect_immediately(self, api_client, producer_user, product):
        api_client.force_authenticate(user=producer_user.user)
        api_client.patch(f'/api/products/{product.id}/', {'availability': 'unavailable'}, format='json')
        resp = api_client.get('/api/products/?visible_only=true')
        assert product.name not in [p['name'] for p in resp.json()]


@pytest.mark.django_db
class TestOrganicFilter:
    """TC-014: filter by organic certification."""

    def test_organic_only_returns_only_certified_products(self, api_client, product, dairy_product):
        # `product` is organic_certified=True, `dairy_product` is False.
        resp = api_client.get('/api/products/?organic_only=true')
        data = resp.json()
        assert all(p['organic_certified'] for p in data)
        assert product.name in [p['name'] for p in data]
        assert dairy_product.name not in [p['name'] for p in data]

    def test_without_filter_both_organic_and_non_organic_shown(self, api_client, product, dairy_product):
        resp = api_client.get('/api/products/')
        names = [p['name'] for p in resp.json()]
        assert product.name in names
        assert dairy_product.name in names