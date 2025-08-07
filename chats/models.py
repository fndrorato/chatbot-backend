from clients.models import Client
from common.models import Origin
from django.db import models


class Chat(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='chats')
    origin = models.ForeignKey(Origin, on_delete=models.CASCADE, related_name='chats', null=True, blank=True)
    contact_id = models.CharField(max_length=255)
    flow = models.BooleanField(default=False, null=True, blank=True, help_text="Indicates if the chat is part of a flow")
    flow_option = models.IntegerField(default=0, null=True, blank=True, help_text="Option selected in the flow, if applicable")
    status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Active'),
            ('inactive', 'Inactive'),
            ('archived', 'Archived')
        ],
        default='active',
        help_text="Status of the chat"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Chat {self.id} for Client {self.client.id}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Chat'
        verbose_name_plural = 'Chats'

class Message(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='messages')
    origin = models.ForeignKey(Origin, on_delete=models.CASCADE, related_name='messages', null=True, blank=True)
    contact_id = models.CharField(max_length=255, help_text="Sender of message, e.g., phone number or username")
    content_input = models.TextField(blank=True, null=True, help_text="Input content for the chat")
    content_output = models.TextField(blank=True, null=True, help_text="Response content from the chat")
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message {self.id} in Chat {self.origin.name} from {self.contact_id}"
    
    class Meta:
        ordering = ['timestamp']
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
