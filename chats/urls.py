from django.urls import path
from chats.views import (
    ChatCreateOrExistsView,
    ChatDeleteView,
    ChatUpdateFlowView,
    MessageCreateView,
    ChatLogView,
)

app_name = 'chats'

urlpatterns = [
    path('chat/log/<int:chat_id>/', ChatLogView.as_view(), name='chat-log'),
    path('chat/update/', ChatUpdateFlowView.as_view(), name='chat-update-flow'),
    path('validate/', ChatCreateOrExistsView.as_view(), name='chat-create-or-exists'),
    path('messages/<str:client_type>/', MessageCreateView.as_view(), name='message-create'),
    path('delete/chat/<str:client_type>/', ChatDeleteView.as_view(), name='chat-delete'),
]
