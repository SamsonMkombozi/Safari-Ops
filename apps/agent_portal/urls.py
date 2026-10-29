from django.urls import path

from . import views

app_name = 'agent_portal'

urlpatterns = [
    path('', views.home, name='home'),
    path('leads/', views.lead_list, name='lead_list'),
    path('leads/<int:pk>/', views.lead_detail, name='lead_detail'),
    path('book/', views.direct_booking, name='direct_booking'),
    path('request/', views.custom_request, name='custom_request'),
    path('bookings/', views.booking_list, name='booking_list'),
    path('quotations/', views.quotation_list, name='quotation_list'),
    path('commissions/', views.commission_list, name='commission_list'),
]
