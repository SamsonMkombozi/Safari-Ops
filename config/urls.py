from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('django-admin/', admin.site.urls),  # Django's own built-in admin — kept separate from our /dashboard/ panel below
    path('dashboard/', include('apps.dashboard.urls')),
    path('agent/', include('apps.agent_portal.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('api/v1/', include('apps.api.urls')),
    path('', include('apps.dashboard.urls_root')),  # bare '/' redirects into the dashboard
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
