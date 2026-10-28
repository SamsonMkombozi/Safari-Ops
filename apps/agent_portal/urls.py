from django.urls import path

from . import views

app_name = 'agent_portal'

urlpatterns = [
    path('', views.home, name='home'),
    path('leads/', views.lead_list, name='lead_list'),
    path('leads/<int:pk>/', views.lead_detail, name='lead_detail'),
    path('commissions/', views.commission_list, name='commission_list'),
]
