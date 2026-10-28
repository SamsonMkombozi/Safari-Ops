from rest_framework import serializers

from .models import AgentTarget, Commission, Customer, Lead


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'
        read_only_fields = ['first_seen_at']


class LeadSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)

    class Meta:
        model = Lead
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        # An agent can only ever create/claim leads under their own name —
        # mirrors OwnershipScope in the legacy app, enforced here rather
        # than trusted from client input.
        request = self.context.get('request')
        if request and request.user.role == 'agent':
            attrs['agent'] = request.user
        return attrs


class CommissionSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)

    class Meta:
        model = Commission
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'approved_by', 'approved_at', 'paid_at']


class AgentTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentTarget
        fields = '__all__'
