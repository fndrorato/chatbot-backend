from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from systems.models import LogIntegration, HotelRooms
from systems.resources import LogIntegrationResource 

@admin.register(LogIntegration)
class LogIntegrationAdmin(ImportExportModelAdmin):
    resource_class = LogIntegrationResource
    list_display = ('client_id', 'origin', 'to', 'status_http', 'created_at')
    search_fields = (
        'client_id__name', 
        'origin', 
        'to',
        'contact_id', # Adicionando este campo do seu modelo
        'content__icontains',   # Busca por qualquer texto dentro do JSON 'content'
        'response__icontains',  # Busca por qualquer texto dentro do JSON 'response'
    )
    list_filter = ('status_http', 'created_at')
    ordering = ('-created_at',)

@admin.register(HotelRooms)
class HotelRoomsAdmin(admin.ModelAdmin):
    list_display = ('client_id', 'room_code', 'room_type', 'number_of_pax', 'created_at')
    search_fields = ('client_id__name', 'room_code', 'room_type')
    list_filter = ('created_at',)
    ordering = ('-created_at',)

