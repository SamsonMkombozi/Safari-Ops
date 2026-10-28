from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'role', 'is_staff_role_display', 'is_active', 'last_login')
    list_filter = ('role', 'is_active', 'is_staff')
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('Safari Zangu role', {'fields': ('role', 'phone', 'bio', 'avatar')}),
        ('Lockout', {'fields': ('failed_login_attempts', 'locked_until')}),
    )

    @admin.display(description='Staff role?', boolean=True)
    def is_staff_role_display(self, obj):
        return obj.is_staff_role
