import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from clients.models import Client

# Configurar o logger
logger = logging.getLogger(__name__)

class GetClientBasicInfoView(APIView):
    """
    Endpoint para recuperar as informações básicas (information_basic)
    do cliente autenticado via token Bearer.
    """
    authentication_classes = [] # Autenticação manual via header
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Recupera o campo 'information_basic' do cliente autenticado.",
        manual_parameters=[
            openapi.Parameter(
                name='Authorization',
                in_=openapi.IN_HEADER,
                type=openapi.TYPE_STRING,
                description="Bearer {token_do_cliente_ativo}",
                required=True,
                default="Bearer seu_token_aqui"
            )
        ],
        # O GET não usa corpo de requisição, então removemos o request_body.
        responses={
            200: openapi.Response(
                description="Informações básicas recuperadas com sucesso",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "information": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="O conteúdo do campo information."
                        )
                    }
                )
            ),
            403: "Token Bearer inválido ou cliente inativo."
        }
    )
    def get(self, request):
        try:
            # 1. Extração e Validação do Header
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response({"detail": "Authorization header ausente ou inválido (Formato: Bearer token)"}, status=403)

            token = auth_header.split(" ")[1]
            
            # 2. Busca e Validação do Cliente (Importante: substitua 'Client' pelo seu modelo real)
            # Use o seu modelo Client aqui:
            # from sua_app.models import Client 
            try:
                client = Client.objects.get(token=token, active=True)
            except Client.DoesNotExist:
                return Response({"detail": "Token inválido ou cliente inativo."}, status=403)
            
            # 3. Retorno do Campo information_basic
            return Response(
                {"information": client.information_basic}, 
                status=200
            )

        except Exception as e:
            logger.exception("Erro ao buscar informações básicas do cliente")
            return Response({"detail": "Erro interno do servidor"}, status=500)