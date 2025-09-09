from django.contrib import admin
from systems.models import LogIntegration, HotelRooms

@admin.register(LogIntegration)
class LogIntegrationAdmin(admin.ModelAdmin):
    list_display = ('client_id', 'origin', 'to', 'status_http', 'created_at')
    search_fields = ('client_id__name', 'origin', 'to')
    list_filter = ('status_http', 'created_at')
    ordering = ('-created_at',)

@admin.register(HotelRooms)
class HotelRoomsAdmin(admin.ModelAdmin):
    list_display = ('client_id', 'room_code', 'room_type', 'number_of_pax', 'created_at')
    search_fields = ('client_id__name', 'room_code', 'room_type')
    list_filter = ('created_at',)
    ordering = ('-created_at',)

