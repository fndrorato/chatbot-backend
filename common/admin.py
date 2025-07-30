from common.models import Country, State, City, Origin
from django.contrib import admin


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'updated_at')
    search_fields = ('name',)
    ordering = ('name',)

@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ('name', 'country', 'created_at', 'updated_at')
    search_fields = ('name',)
    list_filter = ('country',)
    ordering = ('name',)

@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name', 'state', 'created_at', 'updated_at')
    search_fields = ('name',)
    list_filter = ('state',)
    ordering = ('name',)

@admin.register(Origin)
class OriginAdmin(admin.ModelAdmin):
    list_display = ('name',  'created_at', 'updated_at')
    search_fields = ('name',)
    ordering = ('name',)