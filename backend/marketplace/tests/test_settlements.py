from datetime import date
from decimal import Decimal

import pytest

from marketplace.models import Order, ProducerSubOrder
from marketplace.services.settlements import build_weekly_settlement


@pytest.mark.django_db
class TestSettlements:
    """TC-012: weekly settlement only counts delivered sub-orders, correct 95/5 split."""

    def test_settlement_only_counts_delivered_suborders(self, producer_user, producer2_user, customer_user):
        order = Order.objects.create(
            customer=customer_user, delivery_address='x', delivery_date=date.today(),
            total_amount=Decimal('20.00'),
        )
        ProducerSubOrder.objects.create(
            order=order, producer=producer_user, status='delivered',
            subtotal=Decimal('10.00'), producer_payout=Decimal('9.50'),
        )
        # A different producer on the same order, still pending — proves
        # the filter is per-sub-order, not "does this order have any
        # delivered items at all".
        ProducerSubOrder.objects.create(
            order=order, producer=producer2_user, status='pending',
            subtotal=Decimal('100.00'), producer_payout=Decimal('95.00'),
        )

        settlement = build_weekly_settlement(producer_user)

        assert settlement.orders_total == Decimal('10.00')
        assert settlement.payout_total == Decimal('9.50')
        assert settlement.commission_total == Decimal('0.50')

    def test_settlement_csv_export_matches_summary(self, api_client, producer_user, customer_user):
        order = Order.objects.create(
            customer=customer_user, delivery_address='x', delivery_date=date.today(),
            total_amount=Decimal('20.00'),
        )
        ProducerSubOrder.objects.create(
            order=order, producer=producer_user, status='delivered',
            subtotal=Decimal('20.00'), producer_payout=Decimal('19.00'),
        )

        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.get(f'/api/settlements/{producer_user.id}/export/')
        assert resp.status_code == 200
        assert resp['Content-Type'] == 'text/csv'
        body = resp.content.decode()
        assert '19.00' in body
        assert '1.00' in body  # commission = 20.00 - 19.00

    def test_producer_cannot_export_another_producers_settlement(self, api_client, producer_user, producer2_user):
        api_client.force_authenticate(user=producer2_user.user)
        resp = api_client.get(f'/api/settlements/{producer_user.id}/export/')
        assert resp.status_code == 403