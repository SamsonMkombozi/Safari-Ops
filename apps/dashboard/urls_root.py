from django.urls import path
from django.views.generic import RedirectView

app_name = 'root'

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='dashboard:home', permanent=False), name='index'),
]
