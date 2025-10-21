from django.urls import path
from clients.views import GetClientBasicInfoView

urlpatterns = [
    path('info/', GetClientBasicInfoView.as_view(), name='get-client-info'),
]