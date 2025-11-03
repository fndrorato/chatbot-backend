from django.urls import path
from clients.views import GetClientBasicInfoView, GetRelevantContextView


app_name = 'clients'

urlpatterns = [
    path('info/', GetClientBasicInfoView.as_view(), name='get-client-info'),
    # Buscar contexto relevante (usar no n8n)
    path('context/relevant/', GetRelevantContextView.as_view(), name='get-relevant-context'),
    
    
]