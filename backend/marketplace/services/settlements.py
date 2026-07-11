from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from ..models import ProducerSubOrder, Settlement


def _current_week_bounds():
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)  # Sunday
    return week_start, week_end


def build_weekly_settlement(producer):
    """
    Calculate this producer's settlement for the current week.

    Sums every sub-order delivered to this producer within the week,
    applies the 95/5 payout split, and stores the result as a
    Settlement record for accounting history.

    Only sub-orders with status='delivered' are included — a settlement
    must reflect completed business, not orders that are still pending,
    in progress, or were cancelled. Filtering happens on
    ProducerSubOrder.status rather than Order.status because in a
    multi-vendor order, each producer's sub-order progresses through
    Pending -> Confirmed -> Ready -> Delivered independently of the
    other producers on the same order.
    """
    week_start, week_end = _current_week_bounds()

    suborders = ProducerSubOrder.objects.filter(
        producer=producer,
        status='delivered',
        created_at__date__gte=week_start,
        created_at__date__lte=week_end,
    )

    orders_total = suborders.aggregate(total=Sum('subtotal'))['total'] or Decimal('0.00')
    payout_total = suborders.aggregate(total=Sum('producer_payout'))['total'] or Decimal('0.00')
    commission_total = orders_total - payout_total

    settlement = Settlement.objects.create(
        producer=producer,
        week_start=week_start,
        week_end=week_end,
        orders_total=orders_total,
        commission_total=commission_total,
        payout_total=payout_total,
        status='processed',
    )
    return settlement


def weekly_settlement_line_items(producer, week_start=None, week_end=None):
    """
    Return the individual delivered sub-orders that make up a producer's
    settlement for the given week (defaults to the current week), with
    related order/customer/product data pre-fetched for reporting.

    Used to build the downloadable settlement report (TC-012) — the
    aggregate Settlement record has the totals, but the report needs to
    show the order-by-order breakdown behind those totals.
    """
    if week_start is None or week_end is None:
        week_start, week_end = _current_week_bounds()

    suborders = (
        ProducerSubOrder.objects.filter(
            producer=producer,
            status='delivered',
            created_at__date__gte=week_start,
            created_at__date__lte=week_end,
        )
        .select_related('order', 'order__customer', 'order__customer__user')
        .prefetch_related('items__product')
        .order_by('created_at')
    )
    return week_start, week_end, suborders
