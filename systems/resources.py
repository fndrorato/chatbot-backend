from import_export import resources
from systems.models import LogIntegration

class LogIntegrationResource(resources.ModelResource):
    class Meta:
        model = LogIntegration
        # Defina todos os campos que você quer exportar
        fields = (
            'id', 'client_id', 'contact_id', 'origin', 'to', 
            'content', 'response', 'status_http', 
            'response_time', 'created_at', 'updated_at'
        )
        # Campos que podem ser usados para buscar/filtrar ao importar (não essencial para exportação)
        export_order = fields 
