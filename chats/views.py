import logging
from chats.models import Chat, Message
from common.models import Origin
from clients.models import Client
from datetime import timedelta
from django.utils import timezone
from django.utils.timezone import now
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from chats.functions import get_chat_finished
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
            required=['contact_id', 'origin'],
            properties={
                'contact_id': openapi.Schema(type=openapi.TYPE_STRING, description='Contact ID'),
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
            
            contact_id = request.data.get('contact_id')
            # flow = request.data.get('flow', False)
            # flow_option = request.data.get('flow_option', 0)
            origin_name = request.data.get('origin')

            if not all([contact_id]):
                return Response({'detail': 'Missing required fields'}, status=400)

            # Verificando se existe algum chat ativo para o contact_id nas últimas 24 horas
            time_threshold = timezone.now() - timedelta(hours=24)
            existing_chat = Chat.objects.filter(
                contact_id=contact_id,
                status='active',
                created_at__gte=time_threshold
            ).first()

            if existing_chat:
                print('chat existente nas últimas 24 horas.')
                # Filtra mensagens do contato nas últimas 24h
                messages_24h = Message.objects.filter(
                    contact_id=contact_id,
                    timestamp__gte=time_threshold
                ).order_by('timestamp')
                
                if not messages_24h.exists():
                    print('Não existem mensagens nas últimas 24 horas.')
                    return Response({
                        "chat_exists": True, 
                        "chat_id": existing_chat.id,
                        "flow": existing_chat.flow,
                        "flow_option": existing_chat.flow_option,
                    }, status=200)                       
                
                print('existem mensagens nas ultimas 24 horas, verificando se o chat foi finalizado...')
                chat_log = ""
                for msg in messages_24h:
                    if msg.content_input:
                        chat_log += f"Input: {msg.content_input.strip()}\n"
                    if msg.content_output:
                        chat_log += f"Output: {msg.content_output.strip()}\n"

                chat_log += "\nEssa conversa foi encerrada? Você deve apenas responder com True ou False." 
                chat_finished = get_chat_finished(chat_log)
                
                if isinstance(chat_finished, str) and "false" in chat_finished.lower():
                    return Response({
                        "chat_exists": True, 
                        "chat_id": existing_chat.id,
                        "flow": existing_chat.flow,
                        "flow_option": existing_chat.flow_option,
                    }, status=200)               

            origin = Origin.objects.filter(name__iexact=origin_name).first()
            if not origin:
                return Response({'detail': f"Origin '{origin_name}' not found"}, status=404)

            chat = Chat.objects.create(
                client=client,
                origin=origin,
                contact_id=contact_id,
                status='active'
            )

            return Response({
                "chat_exists": False,
                "chat_created": chat.created_at,
                "chat_id": chat.id
            }, status=201)

        except Exception as e:
            logger.exception(f"Error processing chat creation: {str(e)}")
            return Response({"detail": f"Internal server error: {str(e)}"}, status=500)

class ChatUpdateFlowView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Atualiza os campos 'flow' e 'flow_option' de um chat existente",
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
                'chat_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID do chat a ser atualizado'),
                'flow': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Indica se faz parte de um fluxo'),
                'flow_option': openapi.Schema(type=openapi.TYPE_INTEGER, description='Opção selecionada no fluxo'),
            }
        ),
        responses={
            200: openapi.Response('Chat atualizado com sucesso', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'chat_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'flow': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    'flow_option': openapi.Schema(type=openapi.TYPE_INTEGER),
                }
            )),
            403: openapi.Response('Unauthorized'),
            404: openapi.Response('Chat não encontrado'),
            400: openapi.Response('Dados inválidos'),
            500: openapi.Response('Erro interno'),
        }
    )
    def put(self, request):
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

            chat_id = request.data.get('chat_id')
            if not chat_id:
                return Response({'detail': 'Missing chat_id'}, status=400)

            chat = Chat.objects.filter(id=chat_id, client=client).first()
            if not chat:
                return Response({'detail': 'Chat not found'}, status=404)

            # Atualiza os campos se forem fornecidos
            flow = request.data.get('flow')
            flow_option = request.data.get('flow_option')

            if flow is not None:
                chat.flow = flow

            if flow_option is not None:
                chat.flow_option = flow_option

            chat.save()

            return Response({
                'chat_id': chat.id,
                'flow': chat.flow,
                'flow_option': chat.flow_option,
            }, status=200)

        except Exception as e:
            logger.exception(f"Erro ao atualizar chat: {str(e)}")
            return Response({'detail': f'Erro interno: {str(e)}'}, status=500)

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
                'chat_id': openapi.Schema(type=openapi.TYPE_STRING, description='ID do chat'),
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
            
            if 'chat_id' not in data or 'contact_id' not in data:
                return Response({'detail': 'chat_id and contact_id are required'}, status=400)
            
            origin = None
            if 'origin' in data:
                origin = Origin.objects.filter(name__iexact=data.get('origin')).first()

            chat = Chat.objects.filter(id=data['chat_id'], client=client).first()
            message = Message.objects.create(
                client=client,
                origin=origin,
                chat=chat,
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

            chat = Chat.objects.filter(id=chat_id, client=client).first()
            if not chat:
                return Response({'detail': 'Chat not found for this client'}, status=404)

            chat.status = 'archived'
            chat.save()

            return Response(status=204)

        except Exception as e:
            logger.exception("Erro ao arquivar chat")
            return Response({"detail": str(e)}, status=500)

class ChatLogView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Retorna o histórico completo (Input/Output) do chat no formato de texto",
        manual_parameters=[
            openapi.Parameter(
                name='Authorization',
                in_=openapi.IN_HEADER,
                type=openapi.TYPE_STRING,
                description="Bearer {client_token}",
                required=True,
                default="Bearer seu_token_aqui"
            ),
            openapi.Parameter(
                name='chat_id',
                in_=openapi.IN_PATH,
                type=openapi.TYPE_INTEGER,
                description="ID do chat",
                required=True
            ),
        ],
        responses={
            200: openapi.Response('OK', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'chat_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'contact_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'messages_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'chat_log': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            403: openapi.Response('Unauthorized'),
            404: openapi.Response('Chat not found'),
            500: openapi.Response('Internal server error'),
        }
    )
    def get(self, request, chat_id: int):
        try:
            # Auth (mesmo padrão das outras views)
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return Response({'detail': 'Authorization header missing or invalid'}, status=403)

            token = auth_header.split(' ')[1]
            client = Client.objects.filter(token=token).first()
            if not client:
                return Response({'detail': 'Invalid token'}, status=403)
            if client.active is False:
                return Response({'detail': 'Client is inactive'}, status=403)

            # Busca o chat do próprio cliente
            chat = Chat.objects.filter(id=chat_id, client=client).first()
            if not chat:
                return Response({'detail': 'Chat not found'}, status=404)

            # Busca TODAS as mensagens que pertencem ao mesmo contexto do chat
            messages = Message.objects.filter(
                client=chat.client,
                origin=chat.origin,
                contact_id=chat.contact_id,
            ).order_by('timestamp')

            # Monta o chat_log
            chat_log_parts = []
            for msg in messages:
                if msg.content_input:
                    chat_log_parts.append(f"Input: {msg.content_input.strip()}")
                if msg.content_output:
                    chat_log_parts.append(f"Output: {msg.content_output.strip()}")

            chat_log = "\n".join(chat_log_parts)

            return Response({
                "chat_id": chat.id,
                "contact_id": chat.contact_id,
                "messages_count": messages.count(),
                "chat_log": chat_log
            }, status=200)

        except Exception as e:
            logger.exception(f"Error generating chat log: {str(e)}")
            return Response({"detail": f"Internal server error: {str(e)}"}, status=500)
