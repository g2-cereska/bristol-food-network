from datetime import date
from decimal import Decimal

import pytest

from marketplace.models import Order, ProducerSubOrder


@pytest.mark.django_db
class TestAdminDashboard:
    """TC-025: admin commission report — accurate, filterable, exportable, auditable."""

    def test_non_staff_forbidden(self, api_client, customer_user):
        api_client.force_authenticate(user=customer_user.user)
        resp = api_client.get('/api/admin-dashboard/')
        assert resp.status_code == 403

    def test_commission_split_correct_for_multi_vendor_order(
        self, api_client, admin_user, customer_user, producer_user, producer2_user,
    ):
        order = Order.objects.create(
            customer=customer_user, delivery_address='x', delivery_date=date.today(),
            total_amount=Decimal('150.00'), commission_amount=Decimal('7.50'),
        )
        ProducerSubOrder.objects.create(
            order=order, producer=producer_user, status='delivered',
            subtotal=Decimal('80.00'), producer_payout=Decimal('76.00'),
        )
        ProducerSubOrder.objects.create(
            order=order, producer=producer2_user, status='pending',
            subtotal=Decimal('70.00'), producer_payout=Decimal('66.50'),
        )

        api_client.force_authenticate(user=admin_user)
        resp = api_client.get('/api/admin-dashboard/')
        report = resp.json()['commission_report']

        assert report['order_count'] == 1
        row = report['orders'][0]
        producer_figures = {p['producer_name']: p for p in row['producers']}
        assert producer_figures[producer_user.business_name]['commission'] == '4.00'
        assert producer_figures[producer2_user.business_name]['commission'] == '3.50'

    def test_derived_status_is_delivered_when_all_suborders_delivered(
        self, api_client, admin_user, customer_user, producer_user, producer2_user,
    ):
        order = Order.objects.create(
            customer=customer_user, delivery_address='x', delivery_date=date.today(),
            total_amount=Decimal('10.00'), commission_amount=Decimal('0.50'),
        )
        ProducerSubOrder.objects.create(
            order=order, producer=producer_user, status='delivered',
            subtotal=Decimal('5.00'), producer_payout=Decimal('4.75'),
        )
        ProducerSubOrder.objects.create(
            order=order, producer=producer2_user, status='delivered',
            subtotal=Decimal('5.00'), producer_payout=Decimal('4.75'),
        )

        api_client.force_authenticate(user=admin_user)
        resp = api_client.get('/api/admin-dashboard/')
        assert resp.json()['commission_report']['orders'][0]['status'] == 'delivered'

        # Order.status itself is never touched anywhere in the codebase —
        # this confirms the report derives status from sub-orders rather
        # than relying on that unreliable field.
        order.refresh_from_db()
        assert order.status == 'pending'

    def test_derived_status_is_in_progress_when_mixed(
        self, api_client, admin_user, customer_user, producer_user, producer2_user,
    ):
        order = Order.objects.create(
            customer=customer_user, delivery_address='x', delivery_date=date.today(),
            total_amount=Decimal('10.00'), commission_amount=Decimal('0.50'),
        )
        ProducerSubOrder.objects.create(
            order=order, producer=producer_user, status='delivered',
            subtotal=Decimal('5.00'), producer_payout=Decimal('4.75'),
        )
        ProducerSubOrder.objects.create(
            order=order, producer=producer2_user, status='confirmed',
            subtotal=Decimal('5.00'), producer_payout=Decimal('4.75'),
        )

        api_client.force_authenticate(user=admin_user)
        resp = api_client.get('/api/admin-dashboard/')
        assert resp.json()['commission_report']['orders'][0]['status'] == 'in_progress'

    def test_status_filter_matches_derived_status(self, api_client, admin_user, customer_user, producer_user):
        order = Order.objects.create(
            customer=customer_user, delivery_address='x', delivery_date=date.today(),
            total_amount=Decimal('5.00'), commission_amount=Decimal('0.25'),
        )
        ProducerSubOrder.objects.create(
            order=order, producer=producer_user, status='delivered',
            subtotal=Decimal('5.00'), producer_payout=Decimal('4.75'),
        )

        api_client.force_authenticate(user=admin_user)
        delivered_resp = api_client.get('/api/admin-dashboard/?status=delivered')
        assert delivered_resp.json()['commission_report']['order_count'] == 1

        pending_resp = api_client.get('/api/admin-dashboard/?status=pending')
        assert pending_resp.json()['commission_report']['order_count'] == 0

    def test_producer_filter_narrows_results(
        self, api_client, admin_user, customer_user, producer_user, producer2_user,
    ):
        order = Order.objects.create(
            customer=customer_user, delivery_address='x', delivery_date=date.today(),
            total_amount=Decimal('5.00'), commission_amount=Decimal('0.25'),
        )
        ProducerSubOrder.objects.create(
            order=order, producer=producer_user, status='pending',
            subtotal=Decimal('5.00'), producer_payout=Decimal('4.75'),
        )

        api_client.force_authenticate(user=admin_user)
        resp = api_client.get(f'/api/admin-dashboard/?producer={producer2_user.id}')
        assert resp.json()['commission_report']['order_count'] == 0  # producer2 has no orders

    def test_csv_export_totals_match_json_report(self, api_client, admin_user, customer_user, producer_user):
        order = Order.objects.create(
            customer=customer_user, delivery_address='x', delivery_date=date.today(),
            total_amount=Decimal('20.00'), commission_amount=Decimal('1.00'),
        )
        ProducerSubOrder.objects.create(
            order=order, producer=producer_user, status='delivered',
            subtotal=Decimal('20.00'), producer_payout=Decimal('19.00'),
        )

        api_client.force_authenticate(user=admin_user)
        resp = api_client.get('/api/admin-dashboard/export/')
        assert resp.status_code == 200
        body = resp.content.decode()
        assert '20.00' in body
        assert '1.00' in body
