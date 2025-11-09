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
    
    client = models.ForeignKey(
        Client, 
        on_delete=models.CASCADE, 
        related_name='contexts',
        verbose_name='Cliente'
    )
    category = models.CharField(
        max_length=50, 
        choices=CATEGORY_CHOICES,
        verbose_name='Categoria'
    )
    content = models.TextField(
        help_text="Conteúdo que será enviado ao ChatGPT quando este contexto for relevante",
        verbose_name='Conteúdo'
    )
    keywords = models.JSONField(
        default=list,
        help_text="Palavras-chave para busca (ex: ['quarto', 'cama', 'reserva'])",
        verbose_name='Palavras-chave',
        blank=True
    )
    priority = models.IntegerField(
        default=0, 
        help_text="Maior = mais importante. Contextos com prioridade maior aparecem primeiro.",
        verbose_name='Prioridade'
    )
    active = models.BooleanField(
        default=True,
        verbose_name='Ativo'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado em'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado em'
    )
    
    class Meta:
        db_table = 'context_categories'
        ordering = ['-priority', 'category']
        unique_together = ['client', 'category']
        verbose_name = 'Contexto RAG'
        verbose_name_plural = 'Contextos RAG'
    
    def __str__(self):
        return f"{self.get_category_display()} (Prioridade: {self.priority})"


class SystemPrompt(models.Model):
    """Armazena prompts base do sistema"""
    client = models.ForeignKey(
        Client, 
        on_delete=models.CASCADE, 
        related_name='prompts',
        verbose_name='Cliente'
    )
    name = models.CharField(
        max_length=100, 
        help_text="Nome identificador (ex: 'main', 'concierge', 'support')",
        verbose_name='Nome'
    )
    prompt_text = models.TextField(
        help_text="Use {chat_id}, {now}, {language} e {context} como placeholders",
        verbose_name='Texto do Prompt'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Ativo',
        help_text='Apenas um prompt com o mesmo nome pode estar ativo por vez'
    )
    version = models.CharField(
        max_length=20, 
        default="1.0",
        verbose_name='Versão'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado em'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado em'
    )
    
    class Meta:
        db_table = 'system_prompts'
        ordering = ['-updated_at']
        verbose_name = 'Prompt do Sistema'
        verbose_name_plural = 'Prompts do Sistema'
    
    def __str__(self):
        status = '✓' if self.is_active else '✗'
        return f"{status} {self.name} v{self.version}"
