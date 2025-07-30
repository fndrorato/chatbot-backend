from django.urls import path
from systems.views import (
    ChangeReservationView,
    CheckAvailabilityView,
    GetReservationView,
    MakeReservationView,
    
)

app_name = 'systems'

urlpatterns = [
    path('check-availability/<str:client_type>/', CheckAvailabilityView.as_view(), name='check-availability'),
    path('reservations/make/<str:client_type>/', MakeReservationView.as_view(), name='make-reservations'),
    path('reservations/get/<str:client_type>/', GetReservationView.as_view(), name='get-reservations'),
    path('reservations/change/<str:client_type>/', ChangeReservationView.as_view(), name='change-reservations'),
]
    
    
