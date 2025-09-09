from clients.models import Client
from django.db import models


class LogIntegration(models.Model):
    client_id = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='log_integrations')
    contact_id = models.CharField(max_length=255, null=True, blank=True, default=None)
    origin = models.CharField(max_length=255, help_text="Origin of the log integration", null=True, blank=True)
    to = models.CharField(max_length=255, help_text="Destination of the log integration", null=True, blank=True)
    content = models.JSONField(help_text="Content of the log integration")
    response = models.JSONField(help_text="Response from the log integration")
    status_http = models.IntegerField()
    response_time = models.FloatField(help_text="Response time in milliseconds", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class HotelRooms(models.Model):
    client_id = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='hotel_rooms')
    room_code = models.CharField(max_length=100, help_text="Code of the hotel room")
    room_type = models.CharField(max_length=100, help_text="Type of the hotel room")
    number_of_pax = models.IntegerField(help_text="Number of pax allowed in the room", default=None, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.room_code} - {self.room_type} ({self.client_id})"