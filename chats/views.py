import logging
from chats.models import Chat, Message
from common.models import Origin
from clients.models import Client
from django.utils.timezone import now
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


logger = logging.getLogger(__name__)

class ChatCreateOrExistsView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Cria um novo chat ou verifica se já existe",
        manual_parameters=[
            openapi.Parameter(
                name='Authorization',
                in_=openapi.IN_HEADER,
                type=openapi.TYPE_STRING,
                description="Bearer {client_token}",
                required=True,
                default="Bearer seu_token_aqui"
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['_id', 'contact_id', 'origin'],
            properties={
                '_id': openapi.Schema(type=openapi.TYPE_STRING, description='Chat ID'),
                'contact_id': openapi.Schema(type=openapi.TYPE_STRING, description='Contact ID'),
                'flow': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Is part of flow'),
                'flow_option': openapi.Schema(type=openapi.TYPE_INTEGER, description='Selected flow option'),
                'origin': openapi.Schema(type=openapi.TYPE_STRING, description='Origin name (e.g. whatsapp)')
            }
        ),
        responses={
            200: openapi.Response('Chat exists', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'chat_exists': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                }
            )),
            201: openapi.Response('Chat created', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'chat_exists': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    'chat_created': openapi.Schema(type=openapi.FORMAT_DATETIME)
                }
            )),
            403: openapi.Response('Unauthorized'),
            400: openapi.Response('Missing required fields'),
            404: openapi.Response('Origin not found'),
            500: openapi.Response('Internal server error'),
        }
    )
    def post(self, request):
        try:
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return Response({'detail': 'Authorization header missing or invalid'}, status=403)

            token = auth_header.split(' ')[1]
            client = Client.objects.filter(token=token).first()
            if not client:
                return Response({'detail': 'Invalid token'}, status=403)

            if client.active is False:
                return Response({'detail': 'Client is inactive'}, status=403)
            
            chat_id = request.data.get('_id')
            contact_id = request.data.get('contact_id')
            flow = request.data.get('flow', False)
            flow_option = request.data.get('flow_option', 0)
            origin_name = request.data.get('origin')

            if not all([chat_id, contact_id]):
                return Response({'detail': 'Missing required fields'}, status=400)

            existing_chat = Chat.objects.filter(chat_id=chat_id, status='active').first()
            if existing_chat:
                return Response({"chat_exists": True}, status=200)

            origin = Origin.objects.filter(name__iexact=origin_name).first()
            if not origin:
                return Response({'detail': f"Origin '{origin_name}' not found"}, status=404)

            chat = Chat.objects.create(
                client=client,
                origin=origin,
                chat_id=chat_id,
                contact_id=contact_id,
                flow=flow,
                flow_option=flow_option,
                status='active'
            )

            return Response({
                "chat_exists": False,
                "chat_created": chat.created_at
            }, status=201)

        except Exception as e:
            logger.exception(f"Error processing chat creation: {str(e)}")
            return Response({"detail": f"Internal server error: {str(e)}"}, status=500)

class MessageCreateView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Registra mensagem trocada entre usuário e IA",
        manual_parameters=[
            openapi.Parameter(
                name='Authorization',
                in_=openapi.IN_HEADER,
                type=openapi.TYPE_STRING,
                description="Bearer {client_token}",
                required=True,
                default="Bearer seu_token_aqui"
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['contact_id'],
            properties={
                'origin': openapi.Schema(type=openapi.TYPE_STRING, description='Origem da mensagem (e.g., whatsapp)'),
                'contact_id': openapi.Schema(type=openapi.TYPE_STRING, description='ID do contato'),
                'content_input': openapi.Schema(type=openapi.TYPE_STRING, description='Mensagem recebida do usuário'),
                'content_output': openapi.Schema(type=openapi.TYPE_STRING, description='Resposta da IA')
            }
        ),
        responses={
            201: openapi.Response('Mensagem registrada com sucesso'),
            403: openapi.Response('Token inválido ou cliente inativo'),
            500: openapi.Response('Erro interno')
        }
    )
    def post(self, request, client_type):
        try:
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return Response({'detail': 'Authorization header missing or invalid'}, status=403)

            token = auth_header.split(' ')[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({'detail': 'Invalid or inactive client'}, status=403)

            data = request.data
            origin = None
            if 'origin' in data:
                origin = Origin.objects.filter(name__iexact=data.get('origin')).first()

            message = Message.objects.create(
                client=client,
                origin=origin,
                contact_id=data['contact_id'],
                content_input=data.get('content_input'),
                content_output=data.get('content_output')
            )

            return Response({
                'message_id': message.id,
                'timestamp': message.timestamp
            }, status=201)

        except Exception as e:
            logger.exception("Erro ao registrar mensagem")
            return Response({"detail": str(e)}, status=500)

class ChatDeleteView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Arquiva (deleta logicamente) um chat por chat_id",
        manual_parameters=[
            openapi.Parameter(
                name='Authorization',
                in_=openapi.IN_HEADER,
                type=openapi.TYPE_STRING,
                description="Bearer {client_token}",
                required=True,
                default="Bearer seu_token_aqui"
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['chat_id'],
            properties={
                'chat_id': openapi.Schema(type=openapi.TYPE_STRING, description='Identificador do chat a ser arquivado'),
            }
        ),
        responses={
            204: openapi.Response('Chat deletado com sucesso'),
            403: openapi.Response('Token inválido ou cliente inativo'),
            404: openapi.Response('Chat não encontrado'),
            500: openapi.Response('Erro interno')
        }
    )
    def delete(self, request, client_type):
        try:
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return Response({'detail': 'Authorization header missing or invalid'}, status=403)

            token = auth_header.split(' ')[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({'detail': 'Invalid or inactive client'}, status=403)

            chat_id = request.data.get('chat_id')
            if not chat_id:
                return Response({'detail': 'chat_id is required'}, status=400)

            chat = Chat.objects.filter(chat_id=chat_id, client=client).first()
            if not chat:
                return Response({'detail': 'Chat not found for this client'}, status=404)

            chat.status = 'archived'
            chat.save()

            return Response(status=204)

        except Exception as e:
            logger.exception("Erro ao arquivar chat")
            return Response({"detail": str(e)}, status=500)
