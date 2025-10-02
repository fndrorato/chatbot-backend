from django.contrib import admin
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
    
    # ADICIONADO: Pesquisa por texto dentro dos campos de conteúdo
    search_fields = (
        'contact_id',
        'content_input',   
        'content_output',
    )
    
    # REMOVIDO: 'content_input' e 'content_output' daqui, pois são campos de texto longo
    list_filter = (
        'timestamp', 
        'contact_id', 
        'origin',
        'content_input',   
        'content_output',
        'client', 
        'chat' 
    )
    raw_id_fields = ('client', 'origin')
