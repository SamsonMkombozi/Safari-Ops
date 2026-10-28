from django.contrib import admin

from .models import APIKey, ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'object_type', 'object_id', 'ip_address')
    list_filter = ('action', 'object_type')
    search_fields = ('description', 'object_id', 'actor__username')
    date_hierarchy = 'created_at'
    readonly_fields = [f.name for f in ActivityLog._meta.fields]

    def has_add_permission(self, request):
        return False  # written only by log_activity() — never hand-created


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ('name', 'key_preview', 'is_active', 'can_read', 'can_write', 'last_used_at')
    readonly_fields = ('key', 'last_used_at', 'created_at', 'updated_at')

    @admin.display(description='Key')
    def key_preview(self, obj):
        return f'{obj.key[:8]}…{obj.key[-4:]}'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
