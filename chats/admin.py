from django.contrib import admin
from django.db.models import Q
from chats.models import Chat, Message
from chats.resources import MessageResource, ChatResource
from import_export.admin import ImportExportModelAdmin


@admin.register(Chat)
class ChatAdmin(ImportExportModelAdmin):
    resource_class = ChatResource
    list_display = ('id', 'contact_id', 'status', 'created_at')
    search_fields = ('contact_id',)
    list_filter = ('created_at','contact_id', 'status',)

@admin.register(Message)
class MessageAdmin(ImportExportModelAdmin):
    resource_class = MessageResource
    list_display = ('id', 'contact_id', 'timestamp')
    raw_id_fields = ('client', 'origin')

    # Campos de filtro — sem content_input/output
    list_filter = ('timestamp', 'contact_id', 'origin', 'client', 'chat')

    # Campos pesquisáveis — apenas contact_id
    search_fields = ('contact_id',)

    # Adiciona busca customizada no conteúdo
    def get_search_results(self, request, queryset, search_term):
        """
        Permite buscar também dentro de content_input e content_output
        sem precisar indexar diretamente esses campos (evita lentidão).
        """
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        if search_term:
            queryset |= self.model.objects.filter(
                Q(content_input__icontains=search_term) |
                Q(content_output__icontains=search_term)
            )

        return queryset, use_distinct

    # Exibe timestamp no formulário de detalhes (readonly)
    readonly_fields = ('timestamp',)
