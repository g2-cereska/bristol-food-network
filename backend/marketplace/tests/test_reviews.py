from datetime import date, timedelta

import pytest


def _future_date(days):
    return (date.today() + timedelta(days=days)).isoformat()


def _deliver_a_product_to(api_client, customer, product):
    """
    Places and fully delivers an order for `product` to `customer`,
    the way `test_producer_orders.py` progresses an order through the
    status lifecycle — reviews can only be written against something
    that's genuinely reached 'delivered', so every test in this file
    needs one of these to exist first.
    """
    api_client.force_authenticate(user=customer.user)
    api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
    api_client.post('/api/orders/create/', {
        'customer_id': customer.id,
        'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
    }, format='json')

    api_client.force_authenticate(user=product.producer.user)
    from marketplace.models import ProducerSubOrder
    suborder = ProducerSubOrder.objects.get(producer=product.producer, order__customer=customer)
    for next_status in ['confirmed', 'ready', 'delivered']:
        api_client.patch(
            f'/api/producer-suborders/{suborder.id}/status/', {'status': next_status}, format='json',
        )


@pytest.mark.django_db
class TestReviews:
    """TC-024: customers rate and review products they've actually had delivered."""

    def test_customer_can_review_a_delivered_product(self, api_client, customer_user, product):
        _deliver_a_product_to(api_client, customer_user, product)

        api_client.force_authenticate(user=customer_user.user)
        resp = api_client.post(f'/api/products/{product.id}/reviews/', {
            'rating': 5, 'title': 'Excellent quality', 'text': 'Very fresh, will order again.',
        }, format='json')

        assert resp.status_code == 201
        data = resp.json()
        assert data['rating'] == 5
        assert data['customer_name'] == customer_user.user.username

    def test_cannot_review_a_product_that_was_never_delivered(self, api_client, customer_user, product):
        """Order placed but still pending — the review should be rejected, not just discouraged."""
        api_client.force_authenticate(user=customer_user.user)
        api_client.post('/api/cart/add/', {'product_id': product.id, 'quantity': 1}, format='json')
        api_client.post('/api/orders/create/', {
            'customer_id': customer_user.id,
            'delivery_dates': [{'producer_id': product.producer.id, 'delivery_date': _future_date(3)}],
        }, format='json')

        resp = api_client.post(f'/api/products/{product.id}/reviews/', {
            'rating': 4, 'title': 'x', 'text': 'x',
        }, format='json')
        assert resp.status_code == 400

    def test_cannot_review_a_product_never_ordered_at_all(self, api_client, customer_user, product):
        api_client.force_authenticate(user=customer_user.user)
        resp = api_client.post(f'/api/products/{product.id}/reviews/', {
            'rating': 3, 'title': 'x', 'text': 'x',
        }, format='json')
        assert resp.status_code == 400

    def test_cannot_review_the_same_product_twice(self, api_client, customer_user, product):
        _deliver_a_product_to(api_client, customer_user, product)
        api_client.force_authenticate(user=customer_user.user)

        first = api_client.post(f'/api/products/{product.id}/reviews/', {
            'rating': 5, 'title': 'Great', 'text': 'Loved it',
        }, format='json')
        assert first.status_code == 201

        second = api_client.post(f'/api/products/{product.id}/reviews/', {
            'rating': 1, 'title': 'Changed my mind', 'text': 'Actually no',
        }, format='json')
        assert second.status_code == 400

    def test_rating_outside_one_to_five_rejected(self, api_client, customer_user, product):
        _deliver_a_product_to(api_client, customer_user, product)
        api_client.force_authenticate(user=customer_user.user)

        too_high = api_client.post(f'/api/products/{product.id}/reviews/', {
            'rating': 6, 'title': 'x', 'text': 'x',
        }, format='json')
        assert too_high.status_code == 400

        too_low = api_client.post(f'/api/products/{product.id}/reviews/', {
            'rating': 0, 'title': 'x', 'text': 'x',
        }, format='json')
        assert too_low.status_code == 400

    def test_average_rating_and_review_count_reflect_delivered_reviews(
        self, api_client, customer_user, product,
    ):
        from marketplace.models import CustomerProfile, Cart
        from django.contrib.auth.models import User

        second_user = User.objects.create_user(username='second_reviewer', password='Password123!')
        second_customer = CustomerProfile.objects.create(
            user=second_user, address='2 Other Street, Bristol', postcode='BS2 0AA',
        )
        Cart.objects.create(customer=second_customer)

        _deliver_a_product_to(api_client, customer_user, product)
        api_client.force_authenticate(user=customer_user.user)
        api_client.post(f'/api/products/{product.id}/reviews/', {
            'rating': 5, 'title': 'x', 'text': 'x',
        }, format='json')

        _deliver_a_product_to(api_client, second_customer, product)
        api_client.force_authenticate(user=second_customer.user)
        api_client.post(f'/api/products/{product.id}/reviews/', {
            'rating': 3, 'title': 'x', 'text': 'x',
        }, format='json')

        resp = api_client.get(f'/api/products/{product.id}/')
        data = resp.json()
        assert data['review_count'] == 2
        assert data['average_rating'] == 4.0

    def test_product_with_no_reviews_has_null_average_not_zero(self, api_client, product):
        """
        A product nobody's reviewed yet should read as "no rating", not
        "a 0-star rating" — those mean very different things on a
        catalogue card.
        """
        resp = api_client.get(f'/api/products/{product.id}/')
        data = resp.json()
        assert data['review_count'] == 0
        assert data['average_rating'] is None

    def test_reviews_are_publicly_readable(self, api_client, customer_user, product):
        """Anyone — including someone not logged in at all — can read a product's reviews."""
        _deliver_a_product_to(api_client, customer_user, product)
        api_client.force_authenticate(user=customer_user.user)
        api_client.post(f'/api/products/{product.id}/reviews/', {
            'rating': 4, 'title': 'Good', 'text': 'Solid product',
        }, format='json')

        api_client.force_authenticate(user=None)
        resp = api_client.get(f'/api/products/{product.id}/reviews/')
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]['title'] == 'Good'