import uuid
from common.models import Country, State, City
from django.contrib.auth import get_user_model
from django.db import models


User = get_user_model()

class Client(models.Model):
    name = models.CharField(max_length=255)
    business_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    contact = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    active = models.BooleanField(default=True)
    token = models.CharField(max_length=128, blank=True, editable=False)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, blank=True, null=True)
    state = models.ForeignKey(State, on_delete=models.CASCADE, blank=True, null=True)
    city = models.ForeignKey(City, on_delete=models.CASCADE, blank=True, null=True)
    api_token = models.CharField(max_length=128, unique=True, blank=True, editable=True)
    api_address = models.CharField(max_length=255, blank=True)
    observation = models.TextField(blank=True)
    installation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    monthly_fee = models.DecimalField(max_digits=10, decimal_places=2)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='clients_created', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
