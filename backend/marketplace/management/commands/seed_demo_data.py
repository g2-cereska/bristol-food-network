from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from marketplace.models import Cart, Category, CustomerProfile, ProducerProfile, Product

DEMO_PASSWORD = 'Password123!'


class Command(BaseCommand):
    help = 'Populates the database with demo users, categories, and products for the marketplace.'

    def handle(self, *args, **options):
        self.stdout.write('Seeding demo data...')

        categories = self._seed_categories()
        producer_jane = self._seed_producer(
            username='producer_jane',
            business_name='Bristol Valley Farm',
            postcode='BS1 4DJ',
        )
        producer_dairy = self._seed_producer(
            username='producer_dairy',
            business_name='Hillside Dairy',
            postcode='BS9 1AB',
        )
        self._seed_customer(
            username='customer_robert',
            address='45 Park Street, Bristol',
            postcode='BS1 5JG',
        )
        self._seed_admin(username='admin_1')

        self._seed_products(producer_jane, categories)
        self._seed_dairy_products(producer_dairy, categories)

        self.stdout.write(self.style.SUCCESS('Demo data seeded successfully.'))

    def _seed_categories(self):
        names = ['Vegetables', 'Fruit', 'Dairy', 'Bakery', 'Meat']
        categories = {}
        for name in names:
            category, _ = Category.objects.get_or_create(
                name=name,
                defaults={'slug': name.lower()},
            )
            categories[name] = category
        return categories

    def _seed_producer(self, username, business_name, postcode):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': f'{username}@example.com'},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        producer, _ = ProducerProfile.objects.get_or_create(
            user=user,
            defaults={'business_name': business_name, 'postcode': postcode},
        )
        return producer

    def _seed_customer(self, username, address, postcode):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': f'{username}@example.com'},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        customer, _ = CustomerProfile.objects.get_or_create(
            user=user,
            defaults={'address': address, 'postcode': postcode},
        )
        Cart.objects.get_or_create(customer=customer)
        return customer

    def _seed_admin(self, username):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': f'{username}@example.com', 'is_staff': True},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        return user

    def _seed_products(self, producer, categories):
        today = date.today()
        products = [
            ('Organic Carrots', categories['Vegetables'], '2.50', 40, True),
            ('Heritage Tomatoes', categories['Vegetables'], '3.20', 25, True),
            ('Bramley Apples', categories['Fruit'], '2.80', 30, False),
            ('Surplus Courgettes', categories['Vegetables'], '1.50', 15, True),
        ]
        for name, category, price, stock, organic in products:
            Product.objects.get_or_create(
                producer=producer,
                name=name,
                defaults={
                    'category': category,
                    'description': f'Fresh {name.lower()} from {producer.business_name}.',
                    'price': price,
                    'unit': 'kg',
                    'stock_quantity': stock,
                    'availability': 'available',
                    'harvest_date': today - timedelta(days=2),
                    'farm_origin': producer.business_name,
                    'organic_certified': organic,
                    'allergen_info': 'No common allergens declared.',
                },
            )

    def _seed_dairy_products(self, producer, categories):
        products = [
            ('Whole Milk 1L', categories['Dairy'], '1.40', 50),
            ('Farmhouse Cheddar', categories['Dairy'], '5.60', 20),
        ]
        for name, category, price, stock in products:
            Product.objects.get_or_create(
                producer=producer,
                name=name,
                defaults={
                    'category': category,
                    'description': f'{name} from {producer.business_name}.',
                    'price': price,
                    'unit': 'unit',
                    'stock_quantity': stock,
                    'availability': 'available',
                    'farm_origin': producer.business_name,
                    'organic_certified': False,
                    'allergen_info': 'Contains dairy.',
                },
            )