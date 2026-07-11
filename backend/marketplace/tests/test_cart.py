from decimal import Decimal

import pytest

from marketplace.models import CartItem


@pytest.mark.django_db
class TestCart:
    """TC-006: add to cart, modify quantities, view cart contents, stock-aware."""

    def test_add_to_cart_creates_item(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        resp = api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 2}, format='json')
        assert resp.status_code == 201
        assert CartItem.objects.get(cart__customer=customer_user, product=product).quantity == 2

    def test_adding_same_product_twice_accumulates_quantity(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 2}, format='json')
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 3}, format='json')
        item = CartItem.objects.get(cart__customer=customer_user, product=product)
        assert item.quantity == 5

    def test_cannot_add_more_than_stock_in_one_request(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        resp = api_client.post('/api/cart/add/', {
            'product_id': product.id, 'quantity': product.stock_quantity + 1,
        }, format='json')
        assert resp.status_code == 400

    def test_cannot_exceed_stock_cumulatively_across_two_additions(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {
            'product_id': product.id, 'quantity': product.stock_quantity - 2,
        }, format='json')
        resp = api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 5}, format='json')
        assert resp.status_code == 400

    def test_update_quantity_updates_cart_total(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        add_resp = api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        item_id = add_resp.json()['items'][0]['id']
        resp = api_client.patch(f'/api/cart/items/{item_id}/', {'quantity': 4}, format='json')
        assert resp.status_code == 200
        assert Decimal(resp.json()['total']) == product.current_price * 4

    def test_remove_item_from_cart(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        add_resp = api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        item_id = add_resp.json()['items'][0]['id']
        resp = api_client.delete(f'/api/cart/items/{item_id}/')
        assert resp.status_code == 200
        assert resp.json()['items'] == []

    def test_cannot_add_unavailable_product(self, api_client, customer_user, product):
        product.availability = 'unavailable'
        product.save()
        api_client.force_authenticate(user=customer_user.user)
        resp = api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        assert resp.status_code == 400

    def test_customer_cannot_view_another_customers_cart(self, api_client, customer_user, product, django_user_model):
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')

        from marketplace.models import Cart, CustomerProfile
        other_user = django_user_model.objects.create_user(username='other_shopper', password='Password123!')
        other_customer = CustomerProfile.objects.create(user=other_user, address='2 Other St', postcode='BS2 1AA')
        Cart.objects.create(customer=other_customer)

        api_client.force_authenticate(user=other_user)
        resp = api_client.get(f'/api/cart/{customer_user.id}/')
        assert resp.status_code == 403
