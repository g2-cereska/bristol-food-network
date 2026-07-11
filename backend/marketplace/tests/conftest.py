"""
Shared fixtures for the marketplace test suite.

These mirror the shape of the demo data (seed_demo_data.py) without
depending on it, so the suite works against a clean test database that
pytest-django creates and tears down automatically.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from marketplace.models import Cart, Category, CustomerProfile, ProducerProfile, Product

DEMO_PASSWORD = 'Password123!'


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def category(db):
    return Category.objects.create(name='Vegetables', slug='vegetables')


@pytest.fixture
def dairy_category(db):
    return Category.objects.create(name='Dairy', slug='dairy')


@pytest.fixture
def producer_user(db):
    """A producer with a 48-hour lead time, matching Bristol Valley Farm's seed data."""
    user = User.objects.create_user(
        username='test_producer', email='producer@example.com', password=DEMO_PASSWORD
    )
    return ProducerProfile.objects.create(
        user=user, business_name='Test Orchard', postcode='BS1 4DJ', lead_time_hours=48,
    )


@pytest.fixture
def producer2_user(db):
    """A second, unrelated producer with a shorter 24-hour lead time."""
    user = User.objects.create_user(
        username='test_producer2', email='producer2@example.com', password=DEMO_PASSWORD
    )
    return ProducerProfile.objects.create(
        user=user, business_name='Test Dairy', postcode='BS9 1AB', lead_time_hours=24,
    )


@pytest.fixture
def customer_user(db):
    user = User.objects.create_user(
        username='test_customer', email='customer@example.com', password=DEMO_PASSWORD
    )
    customer = CustomerProfile.objects.create(
        user=user, address='45 Park Street, Bristol', postcode='BS1 5JG',
    )
    Cart.objects.create(customer=customer)
    return customer


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        username='test_admin', email='admin@example.com', password=DEMO_PASSWORD
    )
    user.is_staff = True
    user.is_superuser = True
    user.save()
    return user


@pytest.fixture
def product(db, producer_user, category):
    """An in-stock, organic-certified, allergen-free product."""
    return Product.objects.create(
        producer=producer_user, category=category, name='Test Carrots',
        price=Decimal('2.50'), unit='kg', stock_quantity=20, availability='available',
        organic_certified=True, allergen_info='No common allergens declared.',
    )


@pytest.fixture
def dairy_product(db, producer2_user, dairy_category):
    """An in-stock, non-organic product with a real allergen, from a different producer."""
    return Product.objects.create(
        producer=producer2_user, category=dairy_category, name='Test Milk',
        price=Decimal('1.40'), unit='unit', stock_quantity=30, availability='available',
        organic_certified=False, allergen_info='Contains dairy.',
    )
