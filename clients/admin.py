from clients.models import Client
from django.contrib import admin
from django.utils.html import format_html


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'business_name', 'email', 'phone', 'active', 'created_by', 'created_at', 'logo_preview'
    )
    readonly_fields = ('token', 'created_at', 'updated_at', 'logo_preview')
    list_filter = ('active', 'created_by', 'country', 'state')
    search_fields = ('name', 'business_name', 'email', 'phone')
    autocomplete_fields = ('country', 'state', 'city', 'created_by')

    def logo_preview(self, obj):
        if obj.logo:
            return format_html('<img src="{}" style="height: 50px;" />', obj.logo.url)
        return ""
    logo_preview.short_description = "Logo"