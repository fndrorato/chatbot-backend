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

class LogApiSystem(models.Model):
    client_id = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='log_received_jsons')
    origin = models.CharField(max_length=255, help_text="Origin of the received JSON", null=True, blank=True)
    content = models.JSONField(help_text="Content of the received JSON")

    status_message = models.CharField(
        max_length=500, 
        help_text="Status or specific error message of the processing attempt", 
        null=True, 
        blank=True
    )
    
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

class ContextCategory(models.Model):
    """Categorias de contexto para RAG"""
    CATEGORY_CHOICES = [
        ('quartos', 'Informações sobre Quartos'),
        ('horarios', 'Horários e Check-in/out'),
        ('pagamento', 'Formas de Pagamento'),
        ('servicos', 'Serviços e Amenidades'),
        ('contato', 'Telefones e Contato'),
        ('politicas', 'Políticas do Hotel'),
        ('fluxo_reserva', 'Instruções de Reserva'),
    ]
    
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='contexts')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    content = models.TextField(help_text="Conteúdo estruturado em texto")
    keywords = models.JSONField(
        default=list,
        help_text="Lista de palavras-chave para busca rápida"
    )
    priority = models.IntegerField(default=0, help_text="Maior = mais importante")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'context_categories'
        ordering = ['-priority', 'category']
        unique_together = ['client', 'category']
    
    def __str__(self):
        return f"{self.client.name} - {self.category}"


class SystemPrompt(models.Model):
    """Armazena prompts base do sistema"""
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='prompts')
    name = models.CharField(max_length=100, help_text="Nome identificador do prompt")
    prompt_text = models.TextField(help_text="Texto do prompt")
    is_active = models.BooleanField(default=True)
    version = models.CharField(max_length=20, default="1.0")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'system_prompts'
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.client.name} - {self.name} v{self.version}"
