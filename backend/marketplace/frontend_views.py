from django.shortcuts import render


def login_page(request):
    return render(request, 'marketplace/login.html')


def catalogue_page(request):
    return render(request, 'marketplace/catalogue.html')


def cart_page(request):
    return render(request, 'marketplace/cart.html')


def orders_page(request):
    return render(request, 'marketplace/orders.html')


def producer_page(request):
    return render(request, 'marketplace/producer.html')


def admin_dashboard_page(request):
    return render(request, 'marketplace/admin_dash.html')
