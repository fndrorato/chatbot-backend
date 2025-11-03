from django.urls import path
from systems.views import (
    ChangeReservationView,
    CheckAvailabilityView,
    CheckAvailabilityAveragePerNightView,
    GetReservationView,
    MakeReservationView,
    CancelReservationView,
    MakeMultiReservationsView,
)

app_name = 'systems'

urlpatterns = [
    path('v1/systems/check-availability/<str:client_type>/', CheckAvailabilityView.as_view(), name='check-availability'),
    path('v1.1/systems/check-availability/<str:client_type>/', CheckAvailabilityAveragePerNightView.as_view(), name='check-availability-average-per-night'),
    path('v1/systems/reservations/multi-reservation/<str:client_type>/', MakeMultiReservationsView.as_view(), name='make-multi-reservations'),
    path('v1/systems/reservations/make/<str:client_type>/', MakeReservationView.as_view(), name='make-reservations'),
    path('v1/systems/reservations/get/<str:client_type>/', GetReservationView.as_view(), name='get-reservations'),
    path('v1/systems/reservations/change/<str:client_type>/', ChangeReservationView.as_view(), name='change-reservations'),
    path('v1/systems/reservations/cancel/<str:client_type>/', CancelReservationView.as_view(), name='cancel-reservations'),
]
    
    
