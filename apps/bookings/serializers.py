from rest_framework import serializers

from .models import Booking, BookingReminder, Payment, Quotation


class QuotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quotation
        fields = '__all__'
        read_only_fields = ['quote_ref', 'public_token', 'view_count', 'first_viewed_at', 'last_viewed_at', 'created_by']


class QuotationPublicSerializer(serializers.ModelSerializer):
    """What the client sees at their token-gated view link — no internal cost_breakdown/admin_notes, no numeric id exposed."""
    class Meta:
        model = Quotation
        fields = ['quote_ref', 'client_name', 'package_name', 'duration_days', 'start_date',
                  'destinations', 'accommodation_level', 'adults', 'children', 'infants',
                  'line_items', 'subtotal', 'service_charge', 'vat', 'grand_total', 'per_person',
                  'deposit_amount', 'balance_due', 'currency', 'status', 'valid_until', 'notes']


class BookingSerializer(serializers.ModelSerializer):
    balance_due = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Booking
        fields = '__all__'
        # amount_paid/payment_status are derived from the payment ledger — write them via record_payment.
        read_only_fields = ['booking_ref', 'tracking_password_hash', 'created_by', 'amount_paid', 'payment_status']


class BookingTrackingSerializer(serializers.ModelSerializer):
    """What a guest sees after proving ownership (ref + tracking password) — financial summary and itinerary, never the internal payment_notes or another booking's data."""
    balance_due = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Booking
        fields = ['booking_ref', 'full_name', 'email', 'phone', 'package_name', 'accommodation_level',
                   'travel_date', 'travelers', 'adults', 'children', 'special_request', 'payment_status',
                   'total_amount', 'deposit_amount', 'amount_paid', 'balance_due', 'created_at']


class BookingReminderSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingReminder
        fields = '__all__'


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ['recorded_by', 'kind']
        extra_kwargs = {'received_at': {'required': False}}
