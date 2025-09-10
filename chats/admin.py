from django.contrib import admin
from chats.models import Chat, Message


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ('id', 'contact_id', 'status', 'created_at')
    search_fields = ('contact_id',)
    list_filter = ('created_at','contact_id', 'status',)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'contact_id', 'timestamp')
    search_fields = ('contact_id',)
    list_filter = ('timestamp', 'contact_id', 'origin', 'content_input', 'content_output',)
    raw_id_fields = ('client', 'origin')
