from decimal import Decimal
from django.contrib.auth.models import User
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ProducerProfile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='producer_profile')
    business_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    business_address = models.TextField(blank=True)
    postcode = models.CharField(max_length=20, blank=True)
    lead_time_hours = models.PositiveIntegerField(default=48)
    organic_only = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=True)

    def __str__(self):
        return self.business_name


class CustomerProfile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile')
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    postcode = models.CharField(max_length=20, blank=True)
    organisation_name = models.CharField(max_length=255, blank=True)
    segment = models.CharField(max_length=50, default='household')

    def __str__(self):
        return self.user.username


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    AVAILABILITY_CHOICES = [
        ('in_season', 'In Season'),
        ('available', 'Available'),
        ('out_of_season', 'Out of Season'),
        ('unavailable', 'Unavailable'),
    ]
    producer = models.ForeignKey(ProducerProfile, on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    unit = models.CharField(max_length=50, default='unit')
    stock_quantity = models.PositiveIntegerField(default=0)
    availability = models.CharField(max_length=20, choices=AVAILABILITY_CHOICES, default='available')
    harvest_date = models.DateField(null=True, blank=True)
    farm_origin = models.CharField(max_length=255, blank=True)
    organic_certified = models.BooleanField(default=False)
    allergen_info = models.CharField(max_length=255, blank=True)
    best_before = models.DateField(null=True, blank=True)
    grade = models.CharField(max_length=4, default='A')
    discount_percent = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='products/', null=True, blank=True)

    class Meta:
        ordering = ['name']

    @property
    def current_price(self):
        if self.discount_percent <= 0:
            return self.price
        return (self.price * Decimal(100 - self.discount_percent) / Decimal(100)).quantize(Decimal('0.01'))

    @property
    def is_visible(self):
        return self.availability in {'in_season', 'available'} and self.stock_quantity > 0

    def __str__(self):
        return self.name


class InventoryLog(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='inventory_logs')
    previous_stock = models.PositiveIntegerField()
    new_stock = models.PositiveIntegerField()
    note = models.CharField(max_length=255, blank=True)


class Cart(TimeStampedModel):
    customer = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE, related_name='cart')

    @property
    def total(self):
        return sum(
            (item.line_total for item in self.items.select_related('product').all()),
            Decimal('0.00')
        )


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('cart', 'product')

    @property
    def line_total(self):
        return self.product.current_price * self.quantity


class Order(TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('ready', 'Ready'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    delivery_address = models.TextField()
    delivery_date = models.DateField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    food_miles_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    payment_status = models.CharField(max_length=20, default='pending')

    def __str__(self):
        return f'Order #{self.pk}'


class ProducerSubOrder(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='suborders')
    producer = models.ForeignKey(ProducerProfile, on_delete=models.CASCADE, related_name='suborders')
    status = models.CharField(max_length=20, choices=Order.STATUS_CHOICES, default='pending')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    producer_payout = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    delivery_date = models.DateField(null=True, blank=True)
    delivery_notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('order', 'producer')


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    suborder = models.ForeignKey(ProducerSubOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    item_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))


class Payment(TimeStampedModel):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    provider = models.CharField(max_length=40, default='sandbox')
    transaction_reference = models.CharField(max_length=120, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, default='succeeded')
    failure_reason = models.CharField(max_length=255, blank=True)


class Settlement(TimeStampedModel):
    producer = models.ForeignKey(ProducerProfile, on_delete=models.CASCADE, related_name='settlements')
    week_start = models.DateField()
    week_end = models.DateField()
    orders_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    commission_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    payout_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=40, default='processed')


class UserInteraction(TimeStampedModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='interactions')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='interactions')
    interaction_type = models.CharField(max_length=40)
    metadata = models.JSONField(default=dict, blank=True)


class RecommendationLog(TimeStampedModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='recommendation_logs')
    model_version = models.CharField(max_length=100)
    response_payload = models.JSONField(default=dict)


class ForecastLog(TimeStampedModel):
    producer = models.ForeignKey(ProducerProfile, on_delete=models.CASCADE, related_name='forecast_logs')
    model_version = models.CharField(max_length=100)
    response_payload = models.JSONField(default=dict)


class ActivityLog(TimeStampedModel):
    action = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.action