from import_export import resources
from chats.models import Chat, Message

class MessageResource(resources.ModelResource):
    class Meta:
        model = Message
        fields = (
            'id', 
            'client', 
            'origin', 
            'chat', 
            'contact_id', 
            'content_input', 
            'content_output', 
            'timestamp'
        )
        # Garante que a ordem das colunas na exportação siga a ordem definida acima
        export_order = fields

class ChatResource(resources.ModelResource):
    class Meta:
        model = Chat

        fields = (
            'id', 
            'client', 
            'origin', 
            'contact_id', 
            'flow', 
            'flow_option', 
            'room_availability', 
            'rooms', 
            'status', 
            'language', 
            'created_at', 
            'updated_at'
        )
        # Garante que as colunas sejam exportadas na ordem acima
        export_order = fields
