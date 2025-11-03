import json
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

class ProcessAndSaveContextView(APIView):
    """
    Processa um texto bruto usando OpenAI e salva estruturado no banco
    """
    authentication_classes = []
    permission_classes = []
    
    @swagger_auto_schema(
        operation_description="Processa texto bruto e transforma em contexto estruturado",
        manual_parameters=[
            openapi.Parameter(
                name='Authorization',
                in_=openapi.IN_HEADER,
                type=openapi.TYPE_STRING,
                description="Bearer {token}",
                required=True
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'raw_text': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Texto bruto com todas as informações do hotel'
                )
            },
            required=['raw_text']
        ),
        responses={
            200: "Contexto processado e salvo com sucesso",
            400: "Dados inválidos",
            403: "Token inválido"
        }
    )
    def post(self, request):
        try:
            # 1. Validar Token
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response({"detail": "Authorization header inválido"}, status=403)
            
            token = auth_header.split(" ")[1]
            
            try:
                client = Client.objects.get(token=token, active=True)
            except Client.DoesNotExist:
                return Response({"detail": "Token inválido"}, status=403)
            
            # 2. Obter texto bruto
            raw_text = request.data.get('raw_text', '')
            if not raw_text:
                return Response({"detail": "Campo 'raw_text' é obrigatório"}, status=400)
            
            # 3. Processar com OpenAI
            structured_context = self.process_with_openai(raw_text)
            
            # 4. Salvar no banco
            client.information_basic = json.dumps(structured_context, ensure_ascii=False)
            client.save()
            
            return Response({
                "message": "Contexto processado e salvo com sucesso",
                "structured_context": structured_context
            }, status=200)
            
        except Exception as e:
            logger.exception("Erro ao processar contexto")
            return Response({"detail": str(e)}, status=500)
    
    def process_with_openai(self, raw_text: str) -> dict:
        """
        Usa OpenAI para estruturar o texto em categorias
        """
        prompt = f"""
Você é um especialista em organizar informações de hotéis.

Analise o texto abaixo e organize-o em categorias estruturadas.
Extraia TODAS as informações relevantes e organize de forma clara e concisa.

TEXTO ORIGINAL:
{raw_text}

IMPORTANTE:
- Mantenha TODAS as informações importantes
- Organize por categorias lógicas
- Seja conciso mas completo
- Inclua todos os detalhes numéricos (preços, horários, IDs)
- Mantenha o idioma original quando necessário

Retorne APENAS um JSON válido no seguinte formato:
{{
    "quartos": {{
        "descricao": "descrição dos tipos de quartos",
        "tipos": [
            {{"nome": "Individual", "configuracoes": ["1 cama casal", "2 camas solteiro"], "id_types": ["58", "64"]}},
            {{"nome": "Triplo", "configuracoes": ["3 camas solteiro", "1 casal + 1 solteiro"], "id_types": ["62", "63"]}}
        ]
    }},
    "horarios": {{
        "check_in": "horário e regras",
        "check_out": "horário e regras",
        "cafe_manha": "horário"
    }},
    "pagamento": {{
        "formas_aceitas": ["lista de formas"],
        "momento": "quando pagar",
        "nao_aceita": ["lista do que não aceita"],
        "observacoes": "detalhes importantes"
    }},
    "servicos": {{
        "amenidades": ["lista"],
        "eventos": ["lista"],
        "pool_day": "regras e preço"
    }},
    "contato": {{
        "telefones": ["lista"],
        "restricoes_comunicacao": "regras"
    }},
    "politicas": {{
        "gerais": ["lista de políticas"],
        "restricoes": ["lista de restrições"]
    }},
    "instrucoes_atendimento": {{
        "cumprimento_inicial": "texto",
        "fluxo_reserva": ["passos"],
        "pontos_criticos": ["lista de cuidados"]
    }}
}}
"""
        
        try:
            response = client_openai.chat.completions.create(
                model="gpt-4o-mini",  # ou gpt-4o para melhor qualidade
                messages=[
                    {"role": "system", "content": "Você é um especialista em estruturar informações de hotéis. Retorne apenas JSON válido."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Baixa para mais consistência
                response_format={"type": "json_object"}  # Força resposta JSON
            )
            
            structured_data = json.loads(response.choices[0].message.content)
            return structured_data
            
        except Exception as e:
            logger.error(f"Erro ao processar com OpenAI: {e}")
            raise

class GetRelevantContextView(APIView):
    """
    Retorna contexto relevante baseado na mensagem do usuário
    """
    authentication_classes = []
    permission_classes = []
    
    @swagger_auto_schema(
        operation_description="Recupera contexto relevante baseado na mensagem",
        manual_parameters=[
            openapi.Parameter(
                name='Authorization',
                in_=openapi.IN_HEADER,
                type=openapi.TYPE_STRING,
                description="Bearer {token}",
                required=True
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'message': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Mensagem do usuário'
                ),
                'max_contexts': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='Número máximo de contextos (padrão: 3)',
                    default=3
                )
            },
            required=['message']
        ),
        responses={
            200: "Contexto relevante retornado",
            403: "Token inválido"
        }
    )
    def post(self, request):
        try:
            # 1. Validar Token
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response({"detail": "Authorization header inválido"}, status=403)
            
            token = auth_header.split(" ")[1]
            
            try:
                client = Client.objects.get(token=token, active=True)
            except Client.DoesNotExist:
                return Response({"detail": "Token inválido"}, status=403)
            
            # 2. Obter parâmetros
            message = request.data.get('message', '')
            max_contexts = request.data.get('max_contexts', 3)
            
            if not message:
                return Response({"detail": "Campo 'message' é obrigatório"}, status=400)
            
            # 3. Carregar contexto estruturado
            try:
                structured_data = json.loads(client.information_basic)
            except:
                # Fallback se não estiver em JSON
                return Response({
                    "context": client.information_basic,
                    "method": "raw_text"
                }, status=200)
            
            # 4. Buscar contextos relevantes
            relevant_contexts = self.get_relevant_contexts(
                message, 
                structured_data, 
                max_contexts
            )
            
            return Response({
                "context": relevant_contexts,
                "method": "structured_search",
                "num_contexts": len(relevant_contexts)
            }, status=200)
            
        except Exception as e:
            logger.exception("Erro ao buscar contexto")
            return Response({"detail": str(e)}, status=500)
    
    def get_relevant_contexts(self, message: str, structured_data: dict, max_contexts: int) -> str:
        """
        Busca contextos relevantes usando busca por palavras-chave
        """
        message_lower = message.lower()
        
        # Mapeamento de palavras-chave para categorias
        keyword_map = {
            'quartos': ['quarto', 'cama', 'individual', 'triplo', 'quadruplo', 'loft', 'acomodação', 'dormir'],
            'horarios': ['horário', 'check-in', 'check-out', 'entrada', 'saída', 'café', 'manhã'],
            'pagamento': ['pagamento', 'pagar', 'dólar', 'guarani', 'cartão', 'custo', 'preço', 'valor'],
            'servicos': ['serviço', 'piscina', 'pool', 'wifi', 'estacionamento', 'academia', 'casamento', 'evento'],
            'contato': ['telefone', 'contato', 'ligar', 'falar', 'número', 'whatsapp'],
            'politicas': ['política', 'regra', 'transporte', 'taxi', 'permitido', 'proibido']
        }
        
        # Calcular scores
        scores = {}
        for category, keywords in keyword_map.items():
            score = sum(1 for keyword in keywords if keyword in message_lower)
            if score > 0 and category in structured_data:
                scores[category] = score
        
        # Se não encontrou nada, retorna quartos (mais comum)
        if not scores:
            scores = {'quartos': 1, 'horarios': 1, 'instrucoes_atendimento': 1}
        
        # Pegar top categorias
        top_categories = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max_contexts]
        
        # Formatar contextos
        contexts = []
        for category, _ in top_categories:
            if category in structured_data:
                context_text = self.format_category(category, structured_data[category])
                contexts.append(context_text)
        
        return "\n\n---\n\n".join(contexts)
    
    def format_category(self, category: str, data: dict) -> str:
        """
        Formata uma categoria para texto legível
        """
        if category == 'quartos':
            text = "TIPOS DE QUARTOS:\n"
            for tipo in data.get('tipos', []):
                text += f"\n{tipo['nome']}:\n"
                for config in tipo['configuracoes']:
                    text += f"  - {config}\n"
            return text
        
        elif category == 'horarios':
            return f"""HORÁRIOS:
Check-in: {data.get('check_in', '')}
Check-out: {data.get('check_out', '')}
Café da manhã: {data.get('cafe_manha', '')}"""
        
        elif category == 'pagamento':
            return f"""PAGAMENTO:
Formas aceitas: {', '.join(data.get('formas_aceitas', []))}
Momento: {data.get('momento', '')}
NÃO aceita: {', '.join(data.get('nao_aceita', []))}
{data.get('observacoes', '')}"""
        
        elif category == 'servicos':
            return f"""SERVIÇOS E AMENIDADES:
Amenidades: {', '.join(data.get('amenidades', []))}
Eventos: {', '.join(data.get('eventos', []))}
Pool Day: {data.get('pool_day', '')}"""
        
        elif category == 'contato':
            phones = '\n'.join(data.get('telefones', []))
            return f"""CONTATO:
Telefones:
{phones}

{data.get('restricoes_comunicacao', '')}"""
        
        elif category == 'politicas':
            policies = '\n'.join([f"- {p}" for p in data.get('gerais', [])])
            return f"""POLÍTICAS:
{policies}"""
        
        elif category == 'instrucoes_atendimento':
            return f"""INSTRUÇÕES DE ATENDIMENTO:
Cumprimento: {data.get('cumprimento_inicial', '')}

Fluxo de reserva:
{chr(10).join([f"{i+1}. {step}" for i, step in enumerate(data.get('fluxo_reserva', []))])}"""
        
        return json.dumps(data, ensure_ascii=False, indent=2)

