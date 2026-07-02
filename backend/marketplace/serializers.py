from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import (
    ActivityLog,
    Cart,
    CartItem,
    Category,
    CustomerProfile,
    InventoryLog,
    Order,
    OrderItem,
    Payment,
    ProducerProfile,
    ProducerSubOrder,
    Product,
    Settlement,
)
from .services.food_miles import postcode_distance_miles

COMMISSION_RATE = Decimal('0.05')
DEFAULT_ALLERGEN_TEXT = 'No common allergens declared.'
MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class BaseRegistrationSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('Username already exists.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Email already exists.')
        return value

    def validate_password(self, value):
        has_digit = any(ch.isdigit() for ch in value)
        has_letter = any(ch.isalpha() for ch in value)
        if not (has_digit and has_letter) or value.lower() == value:
            raise serializers.ValidationError(
                'Password must contain letters and numbers, and must not be all lowercase.'
            )
        return value


class ProducerRegisterSerializer(BaseRegistrationSerializer):
    business_name = serializers.CharField()
    contact_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    business_address = serializers.CharField(required=False, allow_blank=True)
    postcode = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
        )
        producer = ProducerProfile.objects.create(
            user=user,
            business_name=validated_data['business_name'],
            contact_name=validated_data.get('contact_name', ''),
            phone=validated_data.get('phone', ''),
            business_address=validated_data.get('business_address', ''),
            postcode=validated_data.get('postcode', '').upper().strip(),
        )
        ActivityLog.objects.create(action='producer_registered', details=producer.business_name, user=user)
        return producer

    def to_representation(self, instance):
        return {
            'id': instance.id,
            'business_name': instance.business_name,
            'user': UserSerializer(instance.user).data,
            'role': 'producer',
        }


class CustomerRegisterSerializer(BaseRegistrationSerializer):
    phone = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField()
    postcode = serializers.CharField()
    organisation_name = serializers.CharField(required=False, allow_blank=True)
    segment = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
        )
        customer = CustomerProfile.objects.create(
            user=user,
            phone=validated_data.get('phone', ''),
            address=validated_data['address'],
            postcode=validated_data['postcode'].upper().strip(),
            organisation_name=validated_data.get('organisation_name', ''),
            segment=validated_data.get('segment') or 'household',
        )
        Cart.objects.create(customer=customer)
        ActivityLog.objects.create(action='customer_registered', details=customer.user.username, user=user)
        return customer

    def to_representation(self, instance):
        return {
            'id': instance.id,
            'user': UserSerializer(instance.user).data,
            'role': 'customer',
        }


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs['username'], password=attrs['password'])
        if user is None:
            raise serializers.ValidationError('Invalid username or password.')
        attrs['user'] = user
        return attrs

    def to_representation(self, user):
        if hasattr(user, 'producer_profile'):
            role = 'producer'
        elif hasattr(user, 'customer_profile'):
            role = 'customer'
        elif user.is_staff:
            role = 'admin'
        else:
            role = 'unknown'
        return {
            'user': UserSerializer(user).data,
            'role': role,
        }


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


class ProducerDeliveryDateSerializer(serializers.Serializer):
    producer_id = serializers.IntegerField()
    delivery_date = serializers.DateField()


class ProductSerializer(serializers.ModelSerializer):
    current_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    is_visible = serializers.BooleanField(read_only=True)
    is_in_season_now = serializers.BooleanField(read_only=True)
    season_label = serializers.SerializerMethodField()
    producer_name = serializers.CharField(source='producer.business_name', read_only=True)
    producer_lead_time_hours = serializers.IntegerField(source='producer.lead_time_hours', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Product
        fields = [
        'id', 'producer', 'producer_name', 'producer_lead_time_hours', 'category', 'category_name', 'name',
        'description', 'price', 'current_price', 'unit', 'stock_quantity',
        'availability', 'harvest_date', 'farm_origin', 'organic_certified',
        'allergen_info', 'best_before', 'grade', 'discount_percent', 'is_visible', 'image',
        'season_start_month', 'season_end_month', 'season_label', 'is_in_season_now',
        ]

    def validate_allergen_info(self, value):
        return value.strip() if value.strip() else DEFAULT_ALLERGEN_TEXT

    def validate(self, attrs):
        start = attrs.get('season_start_month', getattr(self.instance, 'season_start_month', None))
        end = attrs.get('season_end_month', getattr(self.instance, 'season_end_month', None))
        if (start is None) != (end is None):
            raise serializers.ValidationError(
                'Set both a season start and end month, or leave both blank for year-round availability.'
            )
        return attrs

    def get_season_label(self, obj):
        if obj.season_start_month and obj.season_end_month:
            return f'{MONTH_NAMES[obj.season_start_month]} \u2013 {MONTH_NAMES[obj.season_end_month]}'
        return None


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'quantity', 'line_total']


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'items', 'total']


class AddCartItemSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate(self, attrs):
        try:
            product = Product.objects.get(pk=attrs['product_id'])
        except Product.DoesNotExist:
            raise serializers.ValidationError('Product not found.')
        if not product.is_visible:
            raise serializers.ValidationError('This product is not currently available.')

        existing_item = CartItem.objects.filter(
            cart__customer_id=attrs['customer_id'],
            product=product,
        ).first()
        already_in_cart = existing_item.quantity if existing_item else 0

        if already_in_cart + attrs['quantity'] > product.stock_quantity:
            available = max(product.stock_quantity - already_in_cart, 0)
            raise serializers.ValidationError(
                f'Only {available} {product.unit} of {product.name} left to add '
                f'(you already have {already_in_cart} in your basket).'
            )

        attrs['product'] = product
        return attrs

    def save(self):
        cart, _ = Cart.objects.get_or_create(customer_id=self.validated_data['customer_id'])
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=self.validated_data['product'],
            defaults={'quantity': self.validated_data['quantity']},
        )
        if not created:
            item.quantity += self.validated_data['quantity']
            item.save()
        return item

class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)

    def update(self, instance, validated_data):
        instance.quantity = validated_data['quantity']
        instance.save()
        return instance


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'unit_price', 'item_total']


class ProducerSubOrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    producer_name = serializers.CharField(source='producer.business_name', read_only=True)
    customer_name = serializers.CharField(source='order.customer.user.username', read_only=True)
    customer_phone = serializers.CharField(source='order.customer.phone', read_only=True)
    delivery_address = serializers.CharField(source='order.delivery_address', read_only=True)
    order_created_at = serializers.DateTimeField(source='order.created_at', read_only=True)

    class Meta:
        model = ProducerSubOrder
        fields = [
            'id', 'order', 'producer', 'producer_name', 'status', 'subtotal',
            'producer_payout', 'delivery_date', 'delivery_notes', 'items',
            'customer_name', 'customer_phone', 'delivery_address', 'order_created_at',
        ]


class OrderSerializer(serializers.ModelSerializer):
    suborders = ProducerSubOrderSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'customer', 'status', 'delivery_address', 'delivery_date',
            'total_amount', 'commission_amount', 'food_miles_total',
            'payment_status', 'suborders', 'created_at',
        ]


class OrderCreateSerializer(serializers.Serializer):
    """
    Builds an Order from the customer's current cart.

    The cart may contain products from several producers — this serializer
    splits the order into one ProducerSubOrder per producer, applies the
    5% network commission, calculates food miles per producer, and
    records a sandbox payment. Each producer gets their own delivery date,
    validated against that producer's individual lead_time_hours, since
    different producers may need different amounts of notice. Everything
    happens inside one atomic transaction so a failure partway through
    never leaves a half-created order in the database.
    """
    customer_id = serializers.IntegerField()
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    delivery_dates = ProducerDeliveryDateSerializer(many=True)
    payment_method = serializers.CharField(required=False, default='sandbox')

    def validate(self, attrs):
        try:
            customer = CustomerProfile.objects.select_related('cart').get(pk=attrs['customer_id'])
        except CustomerProfile.DoesNotExist:
            raise serializers.ValidationError('Customer not found.')

        cart = getattr(customer, 'cart', None)
        if not cart or not cart.items.exists():
            raise serializers.ValidationError('Cart is empty.')

        cart_items = list(cart.items.select_related('product__producer'))
        producer_ids_in_cart = {item.product.producer_id for item in cart_items}

        date_by_producer = {
            entry['producer_id']: entry['delivery_date']
            for entry in attrs['delivery_dates']
        }

        missing_ids = producer_ids_in_cart - set(date_by_producer.keys())
        if missing_ids:
            missing_names = ProducerProfile.objects.filter(id__in=missing_ids).values_list(
                'business_name', flat=True
            )
            raise serializers.ValidationError(
                f"A delivery date is required for: {', '.join(missing_names)}."
            )

        today = timezone.localdate()
        producers = ProducerProfile.objects.filter(id__in=date_by_producer.keys())
        for producer in producers:
            chosen_date = date_by_producer[producer.id]
            lead_days = (producer.lead_time_hours + 23) // 24
            min_date = today + timedelta(days=lead_days)
            if chosen_date < min_date:
                raise serializers.ValidationError(
                    f"{producer.business_name} needs at least {producer.lead_time_hours} hours' "
                    f"notice \u2014 earliest available delivery date is {min_date.isoformat()}."
                )

        attrs['customer'] = customer
        attrs['cart'] = cart
        attrs['date_by_producer'] = date_by_producer
        if not attrs.get('delivery_address'):
            attrs['delivery_address'] = customer.address
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        customer = validated_data['customer']
        cart = validated_data['cart']
        date_by_producer = validated_data['date_by_producer']
        cart_items = list(cart.items.select_related('product__producer'))

        order = Order.objects.create(
            customer=customer,
            delivery_address=validated_data['delivery_address'],
            delivery_date=max(date_by_producer.values()),
            payment_status='pending',
        )

        suborders_by_producer = {}
        order_total = Decimal('0.00')
        food_miles_total = Decimal('0.00')

        for cart_item in cart_items:
            product = cart_item.product
            producer = product.producer

            if product.stock_quantity < cart_item.quantity:
                raise serializers.ValidationError(
                    f'Not enough stock for {product.name}.'
                )

            suborder = suborders_by_producer.get(producer.id)
            if suborder is None:
                suborder = ProducerSubOrder.objects.create(
                    order=order,
                    producer=producer,
                    delivery_date=date_by_producer[producer.id],
                )
                suborders_by_producer[producer.id] = suborder
                distance = Decimal(str(postcode_distance_miles(producer.postcode, customer.postcode)))
                food_miles_total += distance

            line_total = product.current_price * cart_item.quantity
            OrderItem.objects.create(
                order=order,
                suborder=suborder,
                product=product,
                quantity=cart_item.quantity,
                unit_price=product.current_price,
                item_total=line_total,
            )

            suborder.subtotal += line_total
            suborder.save(update_fields=['subtotal'])
            order_total += line_total

            previous_stock = product.stock_quantity
            product.stock_quantity -= cart_item.quantity
            product.save(update_fields=['stock_quantity'])
            InventoryLog.objects.create(
                product=product,
                previous_stock=previous_stock,
                new_stock=product.stock_quantity,
                note=f'Order #{order.id} checkout',
            )

        commission = (order_total * COMMISSION_RATE).quantize(Decimal('0.01'))
        for suborder in suborders_by_producer.values():
            suborder.producer_payout = (suborder.subtotal * (1 - COMMISSION_RATE)).quantize(Decimal('0.01'))
            suborder.save(update_fields=['producer_payout'])

        order.total_amount = order_total
        order.commission_amount = commission
        order.food_miles_total = food_miles_total
        order.payment_status = 'succeeded'
        order.save(update_fields=['total_amount', 'commission_amount', 'food_miles_total', 'payment_status'])

        Payment.objects.create(
            order=order,
            provider=validated_data.get('payment_method', 'sandbox'),
            transaction_reference=str(uuid4()),
            amount=order_total,
            status='succeeded',
        )

        cart.items.all().delete()
        ActivityLog.objects.create(action='order_created', details=f'Order #{order.id}', user=customer.user)
        return order


class UpdateSubOrderStatusSerializer(serializers.Serializer):
    """
    Enforces the status progression: pending -> confirmed -> ready -> delivered.
    A producer cannot skip a step (e.g. jump straight from pending to ready).
    """
    STATUS_ORDER = ['pending', 'confirmed', 'ready', 'delivered']

    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES)

    def validate_status(self, value):
        current = self.instance.status
        if current == 'cancelled':
            raise serializers.ValidationError('Cannot change status of a cancelled order.')
        if value == 'cancelled':
            return value
        current_index = self.STATUS_ORDER.index(current) if current in self.STATUS_ORDER else -1
        new_index = self.STATUS_ORDER.index(value) if value in self.STATUS_ORDER else -1
        if new_index != current_index + 1:
            raise serializers.ValidationError(
                f'Cannot move from "{current}" to "{value}". Status must progress one step at a time.'
            )
        return value

    def save(self):
        self.instance.status = self.validated_data['status']
        self.instance.save(update_fields=['status'])
        return self.instance


class SettlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settlement
        fields = [
            'id', 'producer', 'week_start', 'week_end',
            'orders_total', 'commission_total', 'payout_total', 'status',
        ]