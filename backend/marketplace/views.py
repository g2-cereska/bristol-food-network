import csv
from decimal import Decimal

from django.contrib.auth import login, logout
from django.db.models import F, Q
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    ActivityLog,
    Category,
    CartItem,
    CustomerProfile,
    Order,
    ProducerProfile,
    ProducerSubOrder,
    Product,
)
from .permissions import IsAdminUserOrStaff, IsAuthenticatedAndCustomer, IsAuthenticatedAndProducer
from .serializers import (
    AddCartItemSerializer,
    CartSerializer,
    CategorySerializer,
    CustomerRegisterSerializer,
    LoginSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    ProducerRegisterSerializer,
    ProducerSubOrderSerializer,
    ProductSerializer,
    ReviewSerializer,
    SettlementSerializer,
    UpdateCartItemSerializer,
    UpdateSubOrderStatusSerializer,
)
from .services.ai_client import fetch_json
from .services.admin_reports import build_commission_report, parse_date_range
from .services.settlements import build_weekly_settlement, weekly_settlement_line_items


class HealthView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({'status': 'ok'})


class CsrfTokenView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({'csrfToken': get_token(request)})


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        login(request, serializer.validated_data['user'])
        return Response(serializer.to_representation(serializer.validated_data['user']))


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({'detail': 'Logged out successfully.'})


class ProducerRegisterView(generics.CreateAPIView):
    serializer_class = ProducerRegisterSerializer
    permission_classes = [permissions.AllowAny]


class CustomerRegisterView(generics.CreateAPIView):
    serializer_class = CustomerRegisterSerializer
    permission_classes = [permissions.AllowAny]


class CategoryListView(generics.ListAPIView):
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]


class ProductListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticatedAndProducer()]
        return [permissions.AllowAny()]

    def get(self, request):
        queryset = Product.objects.select_related('producer', 'category').all().order_by('-created_at')

        search = (request.query_params.get('search') or '').strip()
        category = request.query_params.get('category')
        producer = request.query_params.get('producer')
        visible_only = request.query_params.get('visible_only')
        organic_only = request.query_params.get('organic_only')
        surplus_only = request.query_params.get('surplus_only')
        low_stock_only = request.query_params.get('low_stock_only')

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(producer__business_name__icontains=search)
            )
        if category:
            queryset = queryset.filter(category__slug=category)
        if producer:
            queryset = queryset.filter(producer_id=producer)
        if organic_only == 'true':
            queryset = queryset.filter(organic_certified=True)
        if surplus_only == 'true':
            # Mirrors Product.is_surplus_active: on, and either no expiry
            # or an expiry that hasn't passed yet — done at the query
            # level (rather than filtering the Python list, like
            # visible_only does) since both halves translate directly to
            # a WHERE clause.
            queryset = queryset.filter(is_surplus=True).filter(
                Q(surplus_expires_at__isnull=True) | Q(surplus_expires_at__gt=timezone.now())
            )
        if low_stock_only == 'true':
            queryset = queryset.filter(
                low_stock_threshold__isnull=False,
                stock_quantity__lte=F('low_stock_threshold'),
            )

        products = list(queryset)
        if visible_only == 'true':
            products = [product for product in products if product.is_visible]

        return Response(ProductSerializer(products, many=True).data)

    def post(self, request):
        payload = request.data.copy()
        payload['producer'] = request.user.producer_profile.id
        serializer = ProductSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        ActivityLog.objects.create(action='product_created', details=product.name, user=request.user)
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


class ProductDetailView(generics.RetrieveUpdateAPIView):
    queryset = Product.objects.select_related('producer', 'category').all()
    serializer_class = ProductSerializer

    def get_permissions(self):
        if self.request.method in {'PUT', 'PATCH'}:
            return [IsAuthenticatedAndProducer()]
        return [permissions.AllowAny()]

    def update(self, request, *args, **kwargs):
        product = self.get_object()
        if product.producer.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You can only edit your own products.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        payload = request.data.copy()
        payload['producer'] = product.producer.id
        serializer = self.get_serializer(product, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        ActivityLog.objects.create(action='product_updated', details=updated.name, user=request.user)
        return Response(ProductSerializer(updated).data)


class ProductReviewListCreateView(APIView):
    """
    TC-024. GET is open to anyone — reviews are public, browsing-time
    information, same as the rating badge on the catalogue card. POST
    requires a logged-in customer; the actual "did you buy this and was
    it delivered" check happens inside ReviewSerializer.validate(), not
    here, so the one rule lives in one place.
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticatedAndCustomer()]
        return [permissions.AllowAny()]

    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        reviews = product.reviews.select_related('customer__user')
        return Response(ReviewSerializer(reviews, many=True).data)

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        customer = request.user.customer_profile
        serializer = ReviewSerializer(
            data=request.data,
            context={'product': product, 'customer': customer},
        )
        serializer.is_valid(raise_exception=True)
        review = serializer.save()
        ActivityLog.objects.create(
            action='review_created', details=f'{review.rating}\u2605 {product.name}', user=request.user,
        )
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class CartView(APIView):
    """Retrieves a specific customer's cart. GET only; needs customer_id in the URL."""
    permission_classes = [IsAuthenticatedAndCustomer]

    def get(self, request, customer_id):
        customer = get_object_or_404(CustomerProfile, pk=customer_id)
        if request.user.customer_profile != customer and not request.user.is_staff:
            return Response(
                {'detail': 'You can only view your own cart.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(CartSerializer(customer.cart).data)


class AddToCartView(APIView):
    """
    Adds an item to the current user's own cart. POST only, no URL
    parameter — the customer always comes from the authenticated
    session, never from client input. Previously this shared CartView,
    which crashed with a TypeError on a plain browser GET to /cart/add/
    because CartView.get() requires a customer_id this URL never supplies.
    """
    permission_classes = [IsAuthenticatedAndCustomer]

    def post(self, request):
        payload = request.data.copy()
        payload['customer_id'] = request.user.customer_profile.id
        serializer = AddCartItemSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            CartSerializer(request.user.customer_profile.cart).data,
            status=status.HTTP_201_CREATED,
        )


class CartItemDetailView(APIView):
    permission_classes = [IsAuthenticatedAndCustomer]

    def patch(self, request, item_id):
        item = get_object_or_404(CartItem.objects.select_related('cart__customer', 'product'), pk=item_id)
        if item.cart.customer != request.user.customer_profile and not request.user.is_staff:
            return Response(
                {'detail': 'You can only update your own cart items.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = UpdateCartItemSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.update(item, serializer.validated_data)
        return Response(CartSerializer(item.cart).data)

    def delete(self, request, item_id):
        item = get_object_or_404(CartItem.objects.select_related('cart__customer'), pk=item_id)
        if item.cart.customer != request.user.customer_profile and not request.user.is_staff:
            return Response(
                {'detail': 'You can only remove your own cart items.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        cart = item.cart
        item.delete()
        return Response(CartSerializer(cart).data)


class OrderCreateView(generics.CreateAPIView):
    serializer_class = OrderCreateSerializer
    permission_classes = [IsAuthenticatedAndCustomer]

    def create(self, request, *args, **kwargs):
        payload = request.data.copy()
        payload['customer_id'] = request.user.customer_profile.id
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if hasattr(self.request.user, 'customer_profile'):
            return Order.objects.filter(customer=self.request.user.customer_profile).order_by('-created_at')
        if self.request.user.is_staff:
            return Order.objects.all().order_by('-created_at')
        return Order.objects.none()


class ProducerOrderView(generics.ListAPIView):
    serializer_class = ProducerSubOrderSerializer
    permission_classes = [IsAuthenticatedAndProducer]

    def get_queryset(self):
        producer = get_object_or_404(ProducerProfile, pk=self.kwargs['producer_id'])
        if producer != self.request.user.producer_profile and not self.request.user.is_staff:
            return ProducerSubOrder.objects.none()
        return (
            ProducerSubOrder.objects.filter(producer_id=producer.id)
            .select_related('producer', 'order')
            .prefetch_related('items__product')
        )


class UpdateProducerSubOrderStatusView(APIView):
    permission_classes = [IsAuthenticatedAndProducer]

    def patch(self, request, suborder_id):
        suborder = get_object_or_404(ProducerSubOrder, pk=suborder_id)
        if suborder.producer != request.user.producer_profile and not request.user.is_staff:
            return Response(
                {'detail': 'You can only update your own sub-orders.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = UpdateSubOrderStatusSerializer(suborder, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        ActivityLog.objects.create(
            action='suborder_status_updated',
            details=f'Suborder {suborder.id} -> {suborder.status}',
            user=request.user,
        )
        return Response(ProducerSubOrderSerializer(suborder).data)


class SettlementSummaryView(APIView):
    permission_classes = [IsAuthenticatedAndProducer]

    def post(self, request, producer_id):
        producer = get_object_or_404(ProducerProfile, pk=producer_id)
        if producer != request.user.producer_profile and not request.user.is_staff:
            return Response(
                {'detail': 'You can only view your own settlements.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        settlement = build_weekly_settlement(producer)
        return Response(SettlementSerializer(settlement).data)


class SettlementCsvExportView(APIView):
    """
    Downloadable CSV settlement report for a producer (TC-012).

    Lists every delivered sub-order behind the current settlement week,
    with order number, delivery date, customer, items sold, subtotal,
    commission, and payout — suitable for the producer's own accounting
    and tax records — followed by a totals row.
    """
    permission_classes = [IsAuthenticatedAndProducer]

    def get(self, request, producer_id):
        producer = get_object_or_404(ProducerProfile, pk=producer_id)
        if producer != request.user.producer_profile and not request.user.is_staff:
            return Response(
                {'detail': 'You can only export your own settlements.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        week_start, week_end, suborders = weekly_settlement_line_items(producer)

        filename = f'settlement_{producer.id}_{week_start.isoformat()}_to_{week_end.isoformat()}.csv'
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow([f'Bristol Food Network — Settlement report for {producer.business_name}'])
        writer.writerow([f'Period: {week_start.isoformat()} to {week_end.isoformat()}'])
        writer.writerow([])
        writer.writerow([
            'Order Number', 'Delivery Date', 'Customer', 'Items',
            'Subtotal (£)', 'Commission 5% (£)', 'Your Payout 95% (£)', 'Status',
        ])

        total_subtotal = Decimal('0.00')
        total_commission = Decimal('0.00')
        total_payout = Decimal('0.00')

        for suborder in suborders:
            customer_user = suborder.order.customer.user
            customer_name = customer_user.get_full_name() or customer_user.username
            items = '; '.join(
                f'{item.quantity} x {item.product.name}' for item in suborder.items.all()
            )
            commission = suborder.subtotal - suborder.producer_payout

            writer.writerow([
                suborder.order_id,
                suborder.delivery_date.isoformat() if suborder.delivery_date else '',
                customer_name,
                items,
                f'{suborder.subtotal:.2f}',
                f'{commission:.2f}',
                f'{suborder.producer_payout:.2f}',
                suborder.status,
            ])

            total_subtotal += suborder.subtotal
            total_commission += commission
            total_payout += suborder.producer_payout

        writer.writerow([])
        writer.writerow([
            'TOTAL', '', '', '',
            f'{total_subtotal:.2f}', f'{total_commission:.2f}', f'{total_payout:.2f}', '',
        ])

        ActivityLog.objects.create(
            action='settlement_exported',
            details=f'{producer.business_name}: {week_start.isoformat()} to {week_end.isoformat()}',
            user=request.user,
        )
        return response


class AIRecommendView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, customer_id):
        customer = get_object_or_404(CustomerProfile, pk=customer_id)
        is_same_customer = (
            hasattr(request.user, 'customer_profile')
            and request.user.customer_profile == customer
        )
        if not is_same_customer and not request.user.is_staff:
            return Response(
                {'detail': 'You can only access your own recommendations.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        payload = fetch_json(f'/recommend/{customer_id}')
        return Response(payload)


class AIForecastView(APIView):
    permission_classes = [IsAuthenticatedAndProducer]

    def get(self, request, producer_id):
        producer = get_object_or_404(ProducerProfile, pk=producer_id)
        if producer != request.user.producer_profile and not request.user.is_staff:
            return Response(
                {'detail': 'You can only access your own forecasts.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        payload = fetch_json(f'/forecast/{producer_id}')
        return Response(payload)


class AdminDashboardView(APIView):
    permission_classes = [IsAdminUserOrStaff]

    def get(self, request):
        recent = list(
            ActivityLog.objects.order_by('-created_at').values('action', 'details', 'created_at')[:10]
        )

        start_date, end_date = parse_date_range(request.query_params)
        status_filter = request.query_params.get('status') or None
        producer_filter = request.query_params.get('producer') or None
        commission_report = build_commission_report(start_date, end_date, status_filter, producer_filter)

        return Response({
            'producer_count': ProducerProfile.objects.count(),
            'customer_count': CustomerProfile.objects.count(),
            'product_count': Product.objects.count(),
            'order_count': Order.objects.count(),
            'pending_order_count': Order.objects.filter(status='pending').count(),
            'top_products': list(
                Product.objects.order_by('-stock_quantity').values('id', 'name', 'stock_quantity')[:5]
            ),
            'recent_activity': recent,
            'producers': list(
                ProducerProfile.objects.order_by('business_name').values('id', 'business_name')
            ),
            'commission_report': commission_report,
        })


class AdminCommissionCsvExportView(APIView):
    """
    Downloadable CSV commission report for admins (TC-025) — one row per
    order with its producer breakdown flattened into a readable summary,
    followed by a totals row. Respects the same date range / status /
    producer filters as the on-screen report, via the same query params.
    """
    permission_classes = [IsAdminUserOrStaff]

    def get(self, request):
        start_date, end_date = parse_date_range(request.query_params)
        status_filter = request.query_params.get('status') or None
        producer_filter = request.query_params.get('producer') or None
        report = build_commission_report(start_date, end_date, status_filter, producer_filter)

        filename = f'commission_report_{report["start_date"]}_to_{report["end_date"]}.csv'
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(['Bristol Food Network — Network Commission Report'])
        writer.writerow([f'Period: {report["start_date"]} to {report["end_date"]}'])
        if status_filter:
            writer.writerow([f'Status filter: {status_filter}'])
        writer.writerow([])
        writer.writerow([
            'Order Number', 'Date', 'Customer', 'Status', 'Producers',
            'Order Total (£)', 'Commission 5% (£)', 'Producer Payout 95% (£)',
        ])

        for row in report['orders']:
            producers_summary = '; '.join(
                f'{p["producer_name"]} [{p["status"]}: subtotal £{p["subtotal"]}, '
                f'commission £{p["commission"]}, payout £{p["payout"]}]'
                for p in row['producers']
            )
            writer.writerow([
                row['id'], row['created_at'], row['customer_name'], row['status'],
                producers_summary, row['total_amount'], row['commission_amount'],
                row['producer_payout_total'],
            ])

        writer.writerow([])
        writer.writerow([
            'TOTAL', '', '', '', '',
            report['orders_total'], report['commission_total'], report['producer_payout_total'],
        ])

        ActivityLog.objects.create(
            action='commission_report_exported',
            details=f'{report["start_date"]} to {report["end_date"]}',
            user=request.user,
        )
        return response