from django.urls import path

from .frontend_views import (
    admin_dashboard_page,
    cart_page,
    catalogue_page,
    login_page,
    orders_page,
    producer_page,
)

urlpatterns = [
    path('login/', login_page, name='login_page'),
    path('', catalogue_page, name='catalogue_page'),
    path('cart/', cart_page, name='cart_page'),
    path('orders/', orders_page, name='orders_page'),
    path('producer/', producer_page, name='producer_page'),
    path('admin-dash/', admin_dashboard_page, name='admin_dashboard_page'),
]
