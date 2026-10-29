from django.urls import include, path

from . import admin_views, analytics, crud, sales, views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),

    # Operations
    path('bookings/', views.booking_list, name='booking_list'),
    path('bookings/<int:pk>/', views.booking_detail, name='booking_detail'),
    path('bookings/<int:pk>/edit/', views.booking_edit, name='booking_edit'),
    path('bookings/<int:pk>/payment/', views.booking_record_payment, name='booking_record_payment'),
    path('bookings/<int:pk>/status/', views.booking_status, name='booking_status'),
    path('bookings/<int:pk>/assign/', views.booking_assign, name='booking_assign'),
    path('bookings/<int:pk>/assign/<int:assignment_id>/remove/', views.booking_unassign, name='booking_unassign'),
    path('bookings/<int:pk>/reset-tracking/', views.booking_reset_tracking, name='booking_reset_tracking'),
    path('payments/', views.payment_list, name='payment_list'),
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('customer/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('package/<int:pk>/', views.package_detail, name='package_detail'),
    path('package/<int:pk>/reprice/', views.package_reprice, name='package_reprice'),
    path('supplier/<int:pk>/contract/', views.supplier_contract, name='supplier_contract'),

    path('quotations/', sales.quotation_list, name='quotation_list'),
    path('quotations/new/', sales.quotation_new, name='quotation_new'),
    path('quotations/<int:pk>/', sales.quotation_detail, name='quotation_detail'),
    path('quotations/<int:pk>/action/', sales.quotation_action, name='quotation_action'),
    path('leads/', sales.lead_list, name='lead_list'),
    path('leads/new/', sales.lead_form, name='lead_new'),
    path('leads/<int:pk>/edit/', sales.lead_form, name='lead_edit'),
    path('leads/<int:pk>/stage/', sales.lead_stage, name='lead_stage'),
    path('leads/<int:pk>/delete/', sales.lead_delete, name='lead_delete'),
    path('requests/', sales.request_list, name='request_list'),
    path('requests/<int:pk>/', sales.request_detail, name='request_detail'),
    path('requests/<int:pk>/action/', sales.request_action, name='request_action'),
    path('commissions/', sales.commission_list, name='commission_list'),
    path('commissions/<int:pk>/status/', sales.commission_status, name='commission_status'),
    path('commissions/agent-rate/', sales.commission_agent_rate, name='commission_agent_rate'),

    path('messages/', admin_views.message_list, name='message_list'),
    path('messages/<int:pk>/', admin_views.message_detail, name='message_detail'),
    path('messages/<int:pk>/action/', admin_views.message_action, name='message_action'),

    # Communications
    path('email-queue/', admin_views.email_queue, name='email_queue'),
    path('email-queue/action/', admin_views.email_queue_action, name='email_queue_action'),
    path('reminders/', admin_views.reminder_list, name='reminder_list'),
    path('reminders/<int:pk>/action/', admin_views.reminder_action, name='reminder_action'),
    path('emergency-contacts/', admin_views.emergency_contacts, name='emergency_contacts'),

    # Analytics
    path('analytics/sales/', analytics.sales, name='sales'),
    path('analytics/profitability/', analytics.profitability, name='profitability'),
    path('analytics/customer-experience/', analytics.customer_experience, name='customer_experience'),
    path('analytics/agents/', analytics.agent_performance, name='agent_performance'),

    # Settings
    path('settings/', admin_views.settings_view, name='settings'),
    path('users/', admin_views.user_list, name='user_list'),
    path('users/new/', admin_views.user_form, name='user_new'),
    path('users/<int:pk>/edit/', admin_views.user_form, name='user_edit'),
    path('activity-log/', admin_views.activity_log, name='activity_log'),
]
