from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/', include('marketplace.urls')),
    path('market/', include('marketplace.frontend_urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
