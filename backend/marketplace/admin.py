from django.contrib import admin
from .models import (
    ActivityLog,
    Cart,
    CartItem,
    Category,
    CustomerProfile,
    ForecastLog,
    InventoryLog,
    Order,
    OrderItem,
    Payment,
    ProducerProfile,
    ProducerSubOrder,
    Product,
    RecommendationLog,
    Settlement,
    UserInteraction,
)

admin.site.register(ProducerProfile)
admin.site.register(CustomerProfile)
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(InventoryLog)
admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Order)
admin.site.register(ProducerSubOrder)
admin.site.register(OrderItem)
admin.site.register(Payment)
admin.site.register(Settlement)
admin.site.register(UserInteraction)
admin.site.register(RecommendationLog)
admin.site.register(ForecastLog)
admin.site.register(ActivityLog)