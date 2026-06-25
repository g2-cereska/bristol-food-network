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
    """
    week_start, week_end = _current_week_bounds()

    suborders = ProducerSubOrder.objects.filter(
        producer=producer,
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