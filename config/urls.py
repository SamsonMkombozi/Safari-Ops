from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.bookings.public_views import quote_accept, quote_page

urlpatterns = [
    path('django-admin/', admin.site.urls),  # Django's own built-in admin — kept separate from our /dashboard/ panel below
    path('dashboard/', include('apps.dashboard.urls')),
    path('dashboard/manage/', include('apps.dashboard.crud_urls')),
    path('agent/', include('apps.agent_portal.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('api/v1/', include('apps.api.urls')),
    path('q/<str:token>/', quote_page, name='quote_public'),
    path('q/<str:token>/accept/', quote_accept, name='quote_accept'),
    path('', include('apps.dashboard.urls_root')),  # bare '/' redirects into the dashboard
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
