from django.contrib.auth import login, logout
from django.db.models import Q
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
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
    SettlementSerializer,
    UpdateCartItemSerializer,
    UpdateSubOrderStatusSerializer,
)
from .services.ai_client import fetch_json
from .services.settlements import build_weekly_settlement


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


class CartView(APIView):
    permission_classes = [IsAuthenticatedAndCustomer]

    def get(self, request, customer_id):
        customer = get_object_or_404(CustomerProfile, pk=customer_id)
        if request.user.customer_profile != customer and not request.user.is_staff:
            return Response(
                {'detail': 'You can only view your own cart.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(CartSerializer(customer.cart).data)

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


class AIRecommendView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, customer_id):
        customer = get_object_or_404(CustomerProfile, pk=customer_id)
        if (
            hasattr(request.user, 'customer_profile')
            and request.user.customer_profile != customer
            and not request.user.is_staff
        ):
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
        })