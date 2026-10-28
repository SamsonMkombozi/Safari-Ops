from rest_framework import serializers

from .models import ContactMessage, CustomSafariRequest, EmailTemplate, TeamMember


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamMember
        fields = ['id', 'name', 'role', 'member_type', 'bio', 'photo', 'linkedin_url']


class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = '__all__'
        read_only_fields = ['is_read', 'created_at']


class CustomSafariRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomSafariRequest
        fields = '__all__'
        read_only_fields = ['status', 'customer', 'created_at']


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = '__all__'
