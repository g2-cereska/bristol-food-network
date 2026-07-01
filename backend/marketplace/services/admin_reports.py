from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from ..models import Order

DEFAULT_REPORT_WINDOW_DAYS = 30


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def parse_date_range(query_params):
    """
    Resolve the start/end date for the commission report from query
    params (?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD), defaulting to
    the last 30 days (inclusive of today) when not supplied or
    unparsable. If start is after end, the two are swapped rather than
    returning an empty range.
    """
    today = timezone.localdate()
    default_start = today - timedelta(days=DEFAULT_REPORT_WINDOW_DAYS - 1)

    start_date = _parse_date(query_params.get('start_date')) or default_start
    end_date = _parse_date(query_params.get('end_date')) or today

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    return start_date, end_date


def _derive_overall_status(suborder_statuses):
    """
    Order.status is set once at creation and is never updated anywhere
    else in the codebase — only each ProducerSubOrder.status actually
    progresses as individual producers fulfil their portion of an
    order. Order.status is therefore not a reliable signal of an
    order's real fulfilment state, so this derives a meaningful overall
    status from the sub-orders instead:

      - 'cancelled'    every sub-order was cancelled
      - 'delivered'    every (non-cancelled) sub-order has been delivered
      - 'pending'      no sub-order has moved past pending
      - 'in_progress'  a mix — some sub-orders further along than others
    """
    statuses = set(suborder_statuses)
    if not statuses:
        return 'pending'
    if statuses == {'cancelled'}:
        return 'cancelled'
    active = statuses - {'cancelled'}
    if active == {'delivered'}:
        return 'delivered'
    if active == {'pending'}:
        return 'pending'
    return 'in_progress'


def filtered_orders(start_date, end_date, producer_id=None):
    """
    Orders placed within [start_date, end_date] (inclusive), optionally
    narrowed to a specific producer's involvement (via their
    sub-orders). Status filtering is intentionally NOT done here — see
    build_commission_report, which filters on each order's *derived*
    overall status instead of the unreliable Order.status field.
    """
    queryset = Order.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    )
    if producer_id:
        queryset = queryset.filter(suborders__producer_id=producer_id).distinct()

    return (
        queryset
        .select_related('customer', 'customer__user')
        .prefetch_related('suborders__producer')
        .order_by('-created_at')
    )


def build_commission_report(start_date, end_date, status=None, producer_id=None):
    """
    Build the admin commission report (TC-025): a per-order commission
    breakdown plus running totals for the given filters.

    Commission is read from Order.commission_amount / total_amount,
    which are fixed at the 5%/95% split when the order is created (see
    OrderCreateSerializer) — this report therefore reflects commission
    *earned* at the point of sale, independent of delivery status. This
    is a deliberate contrast with the producer settlement report
    (services/settlements.py), which only pays a producer out once
    their sub-order is actually delivered: the network's commission
    ledger and an individual producer's payout ledger are tracking two
    different things and are allowed to disagree on timing.

    The per-order 'status' returned here is the *derived* overall
    status (see _derive_overall_status), not the raw Order.status
    field, and the optional status filter is applied against that
    derived value.
    """
    orders = list(filtered_orders(start_date, end_date, producer_id))

    orders_total = Decimal('0.00')
    commission_total = Decimal('0.00')
    order_rows = []

    for order in orders:
        suborders = list(order.suborders.all())
        overall_status = _derive_overall_status(sub.status for sub in suborders)

        if status and overall_status != status:
            continue

        orders_total += order.total_amount
        commission_total += order.commission_amount

        customer_user = order.customer.user
        customer_name = customer_user.get_full_name() or customer_user.username

        producer_breakdown = [
            {
                'producer_id': sub.producer_id,
                'producer_name': sub.producer.business_name,
                'subtotal': str(sub.subtotal),
                'commission': str(sub.subtotal - sub.producer_payout),
                'payout': str(sub.producer_payout),
                'status': sub.status,
            }
            for sub in suborders
        ]

        order_rows.append({
            'id': order.id,
            'created_at': order.created_at.date().isoformat(),
            'customer_name': customer_name,
            'status': overall_status,
            'total_amount': str(order.total_amount),
            'commission_amount': str(order.commission_amount),
            'producer_payout_total': str(order.total_amount - order.commission_amount),
            'producers': producer_breakdown,
        })

    payout_total = orders_total - commission_total

    return {
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'order_count': len(order_rows),
        'orders_total': str(orders_total),
        'commission_total': str(commission_total),
        'producer_payout_total': str(payout_total),
        'orders': order_rows,
    }