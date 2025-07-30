from django.urls import path
from chats.views import (
    ChatCreateOrExistsView,
    ChatDeleteView,
    MessageCreateView,
)

app_name = 'chats'

urlpatterns = [
    path('validate/', ChatCreateOrExistsView.as_view(), name='chat-create-or-exists'),
    path('messages/<str:client_type>/', MessageCreateView.as_view(), name='message-create'),
    path('delete/chat/<str:client_type>/', ChatDeleteView.as_view(), name='chat-delete'),
]
