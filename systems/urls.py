from django.urls import path
from systems.views import (
    ChangeReservationView,
    CheckAvailabilityView,
    GetReservationView,
    MakeReservationView,
    CancelReservationView,
    MakeMultiReservationsView,
)

app_name = 'systems'

urlpatterns = [
    path('check-availability/<str:client_type>/', CheckAvailabilityView.as_view(), name='check-availability'),
    path('reservations/multi-reservation/<str:client_type>/', MakeMultiReservationsView.as_view(), name='make-multi-reservations'),
    path('reservations/make/<str:client_type>/', MakeReservationView.as_view(), name='make-reservations'),
    path('reservations/get/<str:client_type>/', GetReservationView.as_view(), name='get-reservations'),
    path('reservations/change/<str:client_type>/', ChangeReservationView.as_view(), name='change-reservations'),
    path('reservations/cancel/<str:client_type>/', CancelReservationView.as_view(), name='cancel-reservations'),
]
    
    
