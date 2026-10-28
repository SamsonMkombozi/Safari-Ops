from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('packages/', views.package_list, name='package_list'),
    path('packages/<int:pk>/', views.package_detail, name='package_detail'),
    path('bookings/', views.booking_list, name='booking_list'),
    path('bookings/<int:pk>/', views.booking_detail, name='booking_detail'),
    path('quotations/', views.quotation_list, name='quotation_list'),
    path('leads/', views.lead_list, name='lead_list'),
    path('commissions/', views.commission_list, name='commission_list'),
]
