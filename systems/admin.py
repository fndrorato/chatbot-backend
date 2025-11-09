from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from systems.models import LogIntegration, HotelRooms, LogApiSystem, SystemPrompt, ContextCategory
from django.utils.html import format_html
from systems.resources import LogIntegrationResource 

@admin.register(LogIntegration)
class LogIntegrationAdmin(ImportExportModelAdmin):
    resource_class = LogIntegrationResource
    list_display = ('client_id', 'contact_id', 'origin', 'to', 'status_http', 'created_at')
    search_fields = (
        'client_id__name', 
        'origin', 
        'to',
        'contact_id', # Adicionando este campo do seu modelo
        'content__icontains',   # Busca por qualquer texto dentro do JSON 'content'
        'response__icontains',  # Busca por qualquer texto dentro do JSON 'response'
    )
    list_filter = ('status_http', 'created_at')
    ordering = ('-created_at',)

@admin.register(HotelRooms)
class HotelRoomsAdmin(admin.ModelAdmin):
    list_display = ('client_id', 'room_code', 'room_type', 'number_of_pax', 'created_at')
    search_fields = ('client_id__name', 'room_code', 'room_type')
    list_filter = ('created_at',)
    ordering = ('-created_at',)

@admin.register(LogApiSystem)
class LogApiSystemAdmin(admin.ModelAdmin):
    list_display = ('client_id', 'origin', 'status_message', 'created_at')
    search_fields = (
        'client_id__name',
        'origin',
        'content__icontains',
        'status_message',
    )
    list_filter = ('created_at',)
    ordering = ('-created_at',)

@admin.register(ContextCategory)
class ContextCategoryAdmin(admin.ModelAdmin):
    list_display = ['client', 'category', 'priority', 'active', 'keywords_preview', 'updated_at']
    list_filter = ['client', 'category', 'active', 'priority']
    search_fields = ['category', 'content', 'keywords']
    ordering = ['-priority', 'category']
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('client', 'category', 'priority', 'active')
        }),
        ('Conteúdo', {
            'fields': ('content',),
            'description': 'Escreva o conteúdo que será enviado ao ChatGPT quando este contexto for relevante.'
        }),
        ('Palavras-chave para RAG', {
            'fields': ('keywords',),
            'description': 'Lista de palavras-chave (uma por linha ou separadas por vírgula). Quanto mais palavras, mais fácil o contexto será encontrado.',
            'classes': ('collapse',)
        }),
        ('Metadados', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    def keywords_preview(self, obj):
        """Mostra preview das keywords"""
        keywords = obj.keywords or []
        if len(keywords) > 5:
            preview = ', '.join(keywords[:5]) + '...'
        else:
            preview = ', '.join(keywords)
        return format_html('<span title="{}">{}</span>', ', '.join(keywords), preview)
    keywords_preview.short_description = 'Keywords'
    
    def save_model(self, request, obj, form, change):
        """Processa keywords antes de salvar"""
        # Se keywords vier como string (textarea), converte para lista
        if isinstance(obj.keywords, str):
            # Remove espaços e quebras de linha, split por vírgula
            obj.keywords = [
                kw.strip().lower() 
                for kw in obj.keywords.replace('\n', ',').split(',') 
                if kw.strip()
            ]
        super().save_model(request, obj, form, change)
    
    actions = ['duplicate_context', 'activate_contexts', 'deactivate_contexts']
    
    def duplicate_context(self, request, queryset):
        """Duplica contextos selecionados"""
        for obj in queryset:
            obj.pk = None
            obj.category = f"{obj.category}_copy"
            obj.save()
        self.message_user(request, f"{queryset.count()} contexto(s) duplicado(s)")
    duplicate_context.short_description = "Duplicar contextos selecionados"
    
    def activate_contexts(self, request, queryset):
        """Ativa contextos selecionados"""
        updated = queryset.update(active=True)
        self.message_user(request, f"{updated} contexto(s) ativado(s)")
    activate_contexts.short_description = "Ativar contextos"
    
    def deactivate_contexts(self, request, queryset):
        """Desativa contextos selecionados"""
        updated = queryset.update(active=False)
        self.message_user(request, f"{updated} contexto(s) desativado(s)")
    deactivate_contexts.short_description = "Desativar contextos"        


@admin.register(SystemPrompt)
class SystemPromptAdmin(admin.ModelAdmin):
    list_display = ['client', 'name', 'version', 'is_active', 'char_count', 'updated_at']
    list_filter = ['client', 'is_active', 'name']
    search_fields = ['name', 'prompt_text']
    ordering = ['-updated_at']
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('client', 'name', 'version', 'is_active')
        }),
        ('Prompt', {
            'fields': ('prompt_text',),
            'description': '''
            <strong>Variáveis disponíveis:</strong><br>
            • {chat_id} - ID do chat<br>
            • {now} - Data/hora atual<br>
            • {language} - Idioma do usuário<br>
            • {context} - Contexto relevante (injetado automaticamente pelo RAG)<br>
            <br>
            <strong>Dica:</strong> Use esses placeholders no texto e eles serão substituídos automaticamente.
            '''
        }),
        ('Metadados', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    def char_count(self, obj):
        """Mostra contagem de caracteres do prompt"""
        count = len(obj.prompt_text)
        # Estima tokens (aproximadamente 4 chars = 1 token)
        token_estimate = count // 4
        color = 'green' if count < 2000 else 'orange' if count < 4000 else 'red'
        return format_html(
            '<span style="color: {}">{} chars (~{} tokens)</span>',
            color, count, token_estimate
        )
    char_count.short_description = 'Tamanho'
    
    def save_model(self, request, obj, form, change):
        """Desativa outros prompts com mesmo nome se este for ativo"""
        if obj.is_active:
            # Desativa outros prompts com mesmo nome e cliente
            SystemPrompt.objects.filter(
                client=obj.client,
                name=obj.name,
                is_active=True
            ).exclude(pk=obj.pk).update(is_active=False)
        super().save_model(request, obj, form, change)


# Customização do Admin Site (opcional, mas fica mais bonito)
admin.site.site_header = "Hotel Le Pelican - Administração"
admin.site.site_title = "Le Pelican Admin"
admin.site.index_title = "Gerenciamento do Sistema"    