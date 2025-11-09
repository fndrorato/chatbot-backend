import json
import logging
import requests
import time
from clients.models import Client
from common.utils import parse_int
from datetime import datetime, date
from django.db.models import Q
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from systems.models import LogIntegration, HotelRooms, ContextCategory, SystemPrompt, LogApiSystem
from systems.hotel import reservations
from systems.utils import log_received_json


logger = logging.getLogger(__name__)

class CheckAvailabilityView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Verifica disponibilidade de hospedagem",
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
            required=['contact_id','from', 'to', 'adults', 'children', 'rooms', 'origin'],
            properties={
                'contact_id': openapi.Schema(type=openapi.TYPE_STRING, description='Contact ID'),
                'from': openapi.Schema(type=openapi.TYPE_STRING, format='date'),
                'to': openapi.Schema(type=openapi.TYPE_STRING, format='date'),
                'adults': openapi.Schema(type=openapi.TYPE_INTEGER),
                'children': openapi.Schema(type=openapi.TYPE_INTEGER),
                'rooms': openapi.Schema(type=openapi.TYPE_INTEGER),
                'origin': openapi.Schema(type=openapi.TYPE_STRING),
                'children_age': openapi.Schema(
                    type=openapi.TYPE_STRING, # Alterado de TYPE_ARRAY para TYPE_STRING
                    description='Idades das crianças, se houver, separadas por vírgula (ex: "3,5,7")',
                ),             
            }
        ),
        responses={
            200: openapi.Response('Disponibilidade formatada'),
            400: openapi.Response('Erro de validação'),
            403: openapi.Response('Token inválido'),
            500: openapi.Response('Erro interno')
        }
    )
    def post(self, request, client_type):
        try:
            # ---------- Auth ----------
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return Response({'detail': 'Authorization header missing or invalid'}, status=403)

            token = auth_header.split(' ')[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({'detail': 'Invalid or inactive client'}, status=403)

            if client_type != 'hotel':
                return Response({'detail': 'Unsupported client type'}, status=400)

            # ---------- Validação do body ----------
            data = request.data
            
            # 1. CRIA O LOG INICIALMENTE COM UM STATUS TEMPORÁRIO
            log_entry = log_received_json(
                client_instance=client, 
                data=data, 
                origin_name='API_Hotel_Validation',
                status_message='Pending Validation'
            )
            
            try:
                from_date = datetime.strptime(data.get('from'), '%Y-%m-%d').date()
                to_date = datetime.strptime(data.get('to'), '%Y-%m-%d').date()
                today = date.today()
                if from_date < today:
                    log_entry.status_message = "ERROR: From date must be today or in the future"
                    log_entry.save()
                    return Response({'detail': 'From date must be today or in the future'}, status=400)
                if to_date <= from_date:
                    log_entry.status_message = "ERROR: To date must be after from date"
                    log_entry.save()
                    return Response({'detail': 'To date must be after from date'}, status=400)
            except Exception:
                log_entry.status_message = "ERROR: Invalid date format. Use YYYY-MM-DD"
                log_entry.save()
                return Response({'detail': 'Invalid date format. Use YYYY-MM-DD'}, status=400)

            if int(data.get('adults', 0)) <= 0:
                log_entry.status_message = "ERROR: Adults must be greater than 0"
                log_entry.save()
                return Response({'detail': 'Adults must be greater than 0'}, status=400)
            if int(data.get('children', 0)) < 0:
                log_entry.status_message = "ERROR: Children must be 0 or greater"
                log_entry.save()
                return Response({'detail': 'Children must be 0 or greater'}, status=400)
            if int(data.get('rooms', 0)) < 0:
                log_entry.status_message = "ERROR: Rooms must be greater than 0"
                log_entry.save()
                return Response({'detail': 'Rooms must be greater than 0'}, status=400)
            
            # --- Validação children_age (Versão Atualizada) ---
            children_count = int(data.get('children', 0))
            children_age_input = data.get('children_age') # Campo original (pode ser string '2,10', lista, ou None)
            children_ages = [] # A lista final de inteiros que você usará no payload

            error_message = None

            if children_count > 0:
                if not children_age_input:
                    error_message = 'children_age is required when children > 0'
                elif isinstance(children_age_input, str):
                    try:
                        # Tenta dividir a string e converter para inteiros
                        age_strings = [a.strip() for a in children_age_input.split(',') if a.strip()]
                        children_ages = [int(age) for age in age_strings]
                    except ValueError:
                        error_message = 'Invalid children_age format. Must be a comma-separated string of integers (e.g., "2,10")'
                elif isinstance(children_age_input, list):
                    # Mantenha o suporte se for passado acidentalmente como lista, mas garanta que são inteiros
                    try:
                        children_ages = [int(age) for age in children_age_input]
                    except ValueError:
                        error_message = 'Each child age in the list must be an integer'
                else:
                    error_message = 'children_age must be a string (e.g., "2,10")'

                # Verifica se a contagem de idades corresponde à contagem de crianças
                if not error_message and len(children_ages) != children_count:
                    error_message = f'children_age must contain exactly {children_count} ages, but found {len(children_ages)}'
                    
                # Verifica se todas as idades são válidas
                if not error_message:
                    for age in children_ages:
                        if age < 0:
                            error_message = 'Each child age must be a positive integer'
                            break
                            
            elif children_count == 0:
                # Se não há crianças, o campo children_age deve estar ausente ou vazio
                if children_age_input and (isinstance(children_age_input, str) and children_age_input.strip() != '' or children_age_input):
                    error_message = 'children_age should be empty when children = 0'

            # Tratamento do erro (se houver)
            if error_message:
                log_entry.status_message = f"ERROR: {error_message}"
                log_entry.save()
                return Response({'detail': error_message}, status=400)

            # Se há crianças, verificar se as idades foram informadas corretamente
            if children_count > 0:
                if not isinstance(children_ages, list):
                    log_entry.status_message = "ERROR: children_age must be a list of ages"
                    log_entry.save()
                    return Response({'detail': 'children_age must be a list of ages (e.g. [3,5,7])'}, status=400)
                if len(children_ages) != children_count:
                    log_entry.status_message = f"ERROR: children_age must contain exactly {children_count} items"
                    log_entry.save()
                    return Response({'detail': f'children_age must contain exactly {children_count} items'}, status=400)
                for age in children_ages:
                    if not isinstance(age, int) or age < 0:
                        log_entry.status_message = "ERROR: Each child age must be a positive integer"
                        log_entry.save()
                        return Response({'detail': 'Each child age must be a positive integer'}, status=400)
            else:
                # Se não há crianças, o campo children_age deve estar ausente ou vazio
                if children_ages:
                    log_entry.status_message = "ERROR: children_age should be empty when children = 0"
                    log_entry.save()
                    return Response({'detail': 'children_age should be empty when children = 0'}, status=400)            

            origin = data.get('origin')
            contact_id = request.data.get('contact_id')

            if not contact_id:
                contact_id = 'unknown'

            payload = {
                'token': client.api_token,
                'from': data.get('from'),
                'to': data.get('to'),
                'adults': int(data.get('adults',0)),
                'children': data.get('children'),
                'rooms': data.get('rooms'),
            }
            
            # Se tiver crianças e idades fornecidas
            if children_ages:
                # transformar lista de inteiros para lista de dicts
                payload['age_children'] = [{'age': age} for age in children_ages]            

            # ---------- Requisição externa ----------
            url = f"{client.api_address}/app/reservations/checkAvailability"
            start_time = time.monotonic()
            try:
                response = requests.post(url, json=payload, timeout=30)
            except requests.Timeout as ex:
                elapsed = round(time.monotonic() - start_time, 3)
                LogIntegration.objects.create(
                    client_id=client, origin=origin, to=url, content=payload, contact_id=contact_id,
                    response={'detail': 'timeout'}, status_http=504, response_time=elapsed
                )
                log_entry.status_message = "ERROR: Upstream timeout"
                log_entry.save()
                return Response({'detail': 'Upstream timeout'}, status=504)
            except requests.RequestException as ex:
                elapsed = round(time.monotonic() - start_time, 3)
                LogIntegration.objects.create(
                    client_id=client, origin=origin, to=url, content=payload, contact_id=contact_id,
                    response={'detail': str(ex)}, status_http=502, response_time=elapsed
                )
                log_entry.status_message = f"ERROR: Upstream error - {str(ex)}"
                log_entry.save()
                return Response({'detail': 'Upstream error', 'error': str(ex)}, status=502)

            elapsed = round(time.monotonic() - start_time, 3)

            # ---------- Parse do JSON ----------
            try:
                response_data = response.json()
            except ValueError:
                LogIntegration.objects.create(
                    client_id=client, origin=origin, to=url, content=payload, contact_id=contact_id,
                    response={'detail': 'invalid json', 'raw': response.text[:500]},
                    status_http=response.status_code, response_time=elapsed
                )
                return Response({'detail': 'Invalid JSON from upstream'}, status=502)

            # Log sempre
            LogIntegration.objects.create(
                client_id=client,
                origin=origin,
                to=url,
                content=payload,
                contact_id=contact_id,
                response=response_data,
                status_http=response.status_code,
                response_time=elapsed
            )

            # ---------- Normalização do payload ----------
            data_list = response_data.get("data") or []
            
            if not isinstance(data_list, list) or not data_list:
                # payload inesperado
                return Response(
                    {"availability": [], "status": "Invalid or empty data payload"},
                    status=200
                )

            availability = data_list[0].get("availability", [])

            # Caso: availability é um dict com status
            if isinstance(availability, dict):
                status_msg = availability.get("status", "")
                if status_msg:
                    # ex.: "There is no availability"
                    return Response(
                        {"availability": [], "status": status_msg},
                        status=200
                    )
                # estrutura inesperada
                return Response(
                    {"availability": [], "status": "Unexpected availability object"},
                    status=200
                )

            # Caso: availability None ou lista vazia
            if not availability:
                return Response(
                    {"availability": [], "status": "No availability returned"},
                    status=200
                )

            # Deve ser lista a partir daqui
            if not isinstance(availability, list):
                return Response(
                    {"availability": [], "status": "Availability is not a list"},
                    status=200
                )

            # ---------- Persistência segura ----------
            for room in availability:
                if not isinstance(room, dict):
                    continue
                room_code = room.get("id_type")
                room_type = room.get("type")
                number_of_pax = None

                # 2. Verifique se a chave 'photos' existe e é uma lista não vazia
                photos = room.get("photos")
                if isinstance(photos, list) and photos:
                    # 3. Acesse o primeiro item da lista 'photos' e pegue o 'number_of_pax'
                    number_of_pax = photos[0].get("number_of_pax")

                if not room_code:
                    continue

                # Busca o quarto. Se ela existir, atualiza. Se não, cria.
                # room_instance, created = HotelRooms.objects.update_or_create(
                #     client_id=client,
                #     room_code=room_code,
                #     defaults={
                #         'room_type': room_type,
                #         'number_of_pax': number_of_pax
                #     }
                # )  
                room_instance, created = HotelRooms.objects.update_or_create(
                    client_id=client,
                    room_code=room_code,
                    defaults={
                        'room_type': room_type
                    }
                )                                

            total_pax = int(data.get('adults', 0)) + int(data.get('children', 0))
            available_rooms = HotelRooms.objects.filter(client_id=client, number_of_pax__gte=total_pax)
            
            filtered_room_codes = {room.room_code for room in available_rooms}
            
            # Calcula a diferença de dias entre as datas de entrada e saída
            number_of_nights = (to_date - from_date).days            
            
            # ---------- Limpeza para resposta ----------
            cleaned = []
            for r in availability:
                if not isinstance(r, dict):
                    continue
                # Filtra a resposta para incluir apenas os quartos que atendem aos critérios de lotação
                if r.get("id_type") in filtered_room_codes:
                    details = r.get("details", [])
                    if not isinstance(details, list):
                        details = []
                    
                    # Itera sobre os detalhes para recalcular o total
                    for detail in details:
                        if isinstance(detail, dict):
                            # Tenta pegar o unit_total, garantindo que é um número
                            try:
                                new_total = float(detail.get("total", 0))
                                # Atualiza o valor no dicionário
                                detail['total'] = new_total
                            except (ValueError, TypeError):
                                # Se a conversão falhar, mantém o valor original ou 0
                                detail['total'] = detail.get("total", 0)

                    cleaned.append({
                        "id_type": r.get("id_type"),
                        "type": r.get("type"),
                        "details": details
                    })
            
            log_entry.status_message = "SUCCESS"
            log_entry.save()
            return Response({"availability": cleaned, "status": "OK"}, status=200)

        except Exception as e:
            log_entry = log_received_json(
                client_instance=client, 
                data=data, 
                origin_name='API_Hotel_Validation',
                status_message='Pending Validation'
            )            
            log_entry.status_message = f"ERROR: {str(e)}"
            log_entry.save()
            logger.exception("Erro ao verificar disponibilidade")
            return Response({"detail": str(e)}, status=500)

class CheckAvailabilityAveragePerNightView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Verifica disponibilidade de hospedagem",
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
            required=['contact_id','from', 'to', 'adults', 'children', 'rooms', 'origin'],
            properties={
                'contact_id': openapi.Schema(type=openapi.TYPE_STRING, description='Contact ID'),
                'from': openapi.Schema(type=openapi.TYPE_STRING, format='date'),
                'to': openapi.Schema(type=openapi.TYPE_STRING, format='date'),
                'adults': openapi.Schema(type=openapi.TYPE_INTEGER),
                'children': openapi.Schema(type=openapi.TYPE_INTEGER),
                'rooms': openapi.Schema(type=openapi.TYPE_INTEGER),
                'origin': openapi.Schema(type=openapi.TYPE_STRING),
                'children_age': openapi.Schema(
                    type=openapi.TYPE_STRING, # Alterado de TYPE_ARRAY para TYPE_STRING
                    description='Idades das crianças, se houver, separadas por vírgula (ex: "3,5,7")',
                ),                 
            }
        ),
        responses={
            200: openapi.Response('Disponibilidade formatada'),
            400: openapi.Response('Erro de validação'),
            403: openapi.Response('Token inválido'),
            500: openapi.Response('Erro interno')
        }
    )
    def post(self, request, client_type):
        try:
            # ---------- Auth ----------
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return Response({'detail': 'Authorization header missing or invalid'}, status=403)

            token = auth_header.split(' ')[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({'detail': 'Invalid or inactive client'}, status=403)

            if client_type != 'hotel':
                return Response({'detail': 'Unsupported client type'}, status=400)

            # ---------- Validação do body ----------
            data = request.data
            # 1. CRIA O LOG INICIALMENTE COM UM STATUS TEMPORÁRIO
            log_entry = log_received_json(
                client_instance=client, 
                data=data, 
                origin_name='API_Hotel_Validation',
                status_message='Pending Validation'
            )            
            try:
                from_date = datetime.strptime(data.get('from'), '%Y-%m-%d').date()
                to_date = datetime.strptime(data.get('to'), '%Y-%m-%d').date()
                today = date.today()
                if from_date < today:
                    log_entry.status_message = "ERROR: From date must be today or in the future"
                    log_entry.save()
                    return Response({'detail': 'From date must be today or in the future'}, status=400)
                if to_date <= from_date:
                    log_entry.status_message = "ERROR: To date must be after from date"
                    log_entry.save()
                    return Response({'detail': 'To date must be after from date'}, status=400)
            except Exception:
                log_entry.status_message = "ERROR: Invalid date format. Use YYYY-MM-DD"
                log_entry.save()
                return Response({'detail': 'Invalid date format. Use YYYY-MM-DD'}, status=400)

            if int(data.get('adults', 0)) <= 0:
                log_entry.status_message = "ERROR: Adults must be greater than 0"
                log_entry.save()
                return Response({'detail': 'Adults must be greater than 0'}, status=400)
            if int(data.get('children', 0)) < 0:
                log_entry.status_message = "ERROR: Children must be 0 or greater"
                log_entry.save()
                return Response({'detail': 'Children must be 0 or greater'}, status=400)
            if int(data.get('rooms', 0)) < 0:
                log_entry.status_message = "ERROR: Rooms must be greater than 0"
                log_entry.save()
                return Response({'detail': 'Rooms must be greater than 0'}, status=400)
            
            # --- Validação children_age (Versão Atualizada) ---
            children_count = int(data.get('children', 0))
            children_age_input = data.get('children_age') # Campo original (pode ser string '2,10', lista, ou None)
            children_ages = [] # A lista final de inteiros que você usará no payload

            error_message = None

            if children_count > 0:
                if not children_age_input:
                    error_message = 'children_age is required when children > 0'
                elif isinstance(children_age_input, str):
                    try:
                        # Tenta dividir a string e converter para inteiros
                        age_strings = [a.strip() for a in children_age_input.split(',') if a.strip()]
                        children_ages = [int(age) for age in age_strings]
                    except ValueError:
                        error_message = 'Invalid children_age format. Must be a comma-separated string of integers (e.g., "2,10")'
                elif isinstance(children_age_input, list):
                    # Mantenha o suporte se for passado acidentalmente como lista, mas garanta que são inteiros
                    try:
                        children_ages = [int(age) for age in children_age_input]
                    except ValueError:
                        error_message = 'Each child age in the list must be an integer'
                else:
                    error_message = 'children_age must be a string (e.g., "2,10")'

                # Verifica se a contagem de idades corresponde à contagem de crianças
                if not error_message and len(children_ages) != children_count:
                    error_message = f'children_age must contain exactly {children_count} ages, but found {len(children_ages)}'
                    
                # Verifica se todas as idades são válidas
                if not error_message:
                    for age in children_ages:
                        if age < 0:
                            error_message = 'Each child age must be a positive integer'
                            break
                            
            elif children_count == 0:
                # Se não há crianças, o campo children_age deve estar ausente ou vazio
                if children_age_input and (isinstance(children_age_input, str) and children_age_input.strip() != '' or children_age_input):
                    error_message = 'children_age should be empty when children = 0'

            # Tratamento do erro (se houver)
            if error_message:
                log_entry.status_message = f"ERROR: {error_message}"
                log_entry.save()
                return Response({'detail': error_message}, status=400)

            # Se há crianças, verificar se as idades foram informadas corretamente
            if children_count > 0:
                if not isinstance(children_ages, list):
                    log_entry.status_message = "ERROR: children_age must be a list of ages"
                    log_entry.save()
                    return Response({'detail': 'children_age must be a list of ages (e.g. [3,5,7])'}, status=400)
                if len(children_ages) != children_count:
                    log_entry.status_message = f"ERROR: children_age must contain exactly {children_count} items"
                    log_entry.save()
                    return Response({'detail': f'children_age must contain exactly {children_count} items'}, status=400)
                for age in children_ages:
                    if not isinstance(age, int) or age < 0:
                        log_entry.status_message = "ERROR: Each child age must be a positive integer"
                        log_entry.save()
                        return Response({'detail': 'Each child age must be a positive integer'}, status=400)
            else:
                # Se não há crianças, o campo children_age deve estar ausente ou vazio
                if children_ages:
                    log_entry.status_message = "ERROR: children_age should be empty when children = 0"
                    log_entry.save()
                    return Response({'detail': 'children_age should be empty when children = 0'}, status=400)            

            origin = data.get('origin')
            contact_id = request.data.get('contact_id')

            if not contact_id:
                contact_id = 'unknown'

            payload = {
                'token': client.api_token,
                'from': data.get('from'),
                'to': data.get('to'),
                'adults': int(data.get('adults',0)),
                'children': data.get('children'),
                'rooms': data.get('rooms'),
            }
            
            # Se tiver crianças e idades fornecidas
            if children_ages:
                # transformar lista de inteiros para lista de dicts
                payload['age_children'] = [{'age': age} for age in children_ages]            

            # ---------- Requisição externa ----------
            url = f"{client.api_address}/app/reservations/checkAvailability"
            start_time = time.monotonic()
            try:
                response = requests.post(url, json=payload, timeout=30)
            except requests.Timeout as ex:
                elapsed = round(time.monotonic() - start_time, 3)
                LogIntegration.objects.create(
                    client_id=client, origin=origin, to=url, content=payload, contact_id=contact_id,
                    response={'detail': 'timeout'}, status_http=504, response_time=elapsed
                )
                return Response({'detail': 'Upstream timeout'}, status=504)
            except requests.RequestException as ex:
                elapsed = round(time.monotonic() - start_time, 3)
                LogIntegration.objects.create(
                    client_id=client, origin=origin, to=url, content=payload, contact_id=contact_id,
                    response={'detail': str(ex)}, status_http=502, response_time=elapsed
                )
                return Response({'detail': 'Upstream error', 'error': str(ex)}, status=502)

            elapsed = round(time.monotonic() - start_time, 3)

            # ---------- Parse do JSON ----------
            try:
                response_data = response.json()
            except ValueError:
                LogIntegration.objects.create(
                    client_id=client, origin=origin, to=url, content=payload, contact_id=contact_id,
                    response={'detail': 'invalid json', 'raw': response.text[:500]},
                    status_http=response.status_code, response_time=elapsed
                )
                return Response({'detail': 'Invalid JSON from upstream'}, status=502)

            # Log sempre
            LogIntegration.objects.create(
                client_id=client,
                origin=origin,
                to=url,
                content=payload,
                contact_id=contact_id,
                response=response_data,
                status_http=response.status_code,
                response_time=elapsed
            )

            # ---------- Normalização do payload ----------
            data_list = response_data.get("data") or []
            
            if not isinstance(data_list, list) or not data_list:
                # payload inesperado
                return Response(
                    {"availability": [], "status": "Invalid or empty data payload"},
                    status=200
                )

            availability = data_list[0].get("availability", [])

            # Caso: availability é um dict com status
            if isinstance(availability, dict):
                status_msg = availability.get("status", "")
                if status_msg:
                    # ex.: "There is no availability"
                    return Response(
                        {"availability": [], "status": status_msg},
                        status=200
                    )
                # estrutura inesperada
                return Response(
                    {"availability": [], "status": "Unexpected availability object"},
                    status=200
                )

            # Caso: availability None ou lista vazia
            if not availability:
                return Response(
                    {"availability": [], "status": "No availability returned"},
                    status=200
                )

            # Deve ser lista a partir daqui
            if not isinstance(availability, list):
                return Response(
                    {"availability": [], "status": "Availability is not a list"},
                    status=200
                )

            # ---- NOVA VERIFICAÇÃO ----
            # Caso: availability veio com itens mas todos com details vazio
            if all(
                isinstance(item, dict) and not item.get("details")
                for item in availability
            ):
                log_entry.status_message = "NO_AVAILABILITY - Error no retorno do detail"
                log_entry.save()
                return Response(
                    {"availability": [], "status": "No availability"},
                    status=200
                )
            # --------------------------                

            # ---------- Persistência segura ----------
            for room in availability:
                if not isinstance(room, dict):
                    continue
                room_code = room.get("id_type")
                room_type = room.get("type")
                number_of_pax = None

                # 2. Verifique se a chave 'photos' existe e é uma lista não vazia
                photos = room.get("photos")
                if isinstance(photos, list) and photos:
                    # 3. Acesse o primeiro item da lista 'photos' e pegue o 'number_of_pax'
                    number_of_pax = photos[0].get("number_of_pax")

                if not room_code:
                    continue
                
                room_instance, created = HotelRooms.objects.update_or_create(
                    client_id=client,
                    room_code=room_code,
                    defaults={
                        'room_type': room_type
                    }
                )                                

            total_pax = int(data.get('adults', 0)) + int(data.get('children', 0))
            available_rooms = HotelRooms.objects.filter(client_id=client, number_of_pax__gte=total_pax)
            
            filtered_room_codes = {room.room_code for room in available_rooms}
            
            # Calcula a diferença de dias entre as datas de entrada e saída
            number_of_nights = (to_date - from_date).days            
            
            # ---------- Limpeza para resposta ----------
            cleaned = []
            for r in availability:
                if not isinstance(r, dict):
                    continue
                # Filtra a resposta para incluir apenas os quartos que atendem aos critérios de lotação
                if r.get("id_type") in filtered_room_codes:
                    details = r.get("details", [])
                    if not isinstance(details, list):
                        details = []
                    
                    # Itera sobre os detalhes para recalcular o total
                    for detail in details:
                        if isinstance(detail, dict):
                            # Tenta pegar o unit_total, garantindo que é um número
                            try:
                                new_total = float(detail.get("total", 0))
                                # Atualiza o valor no dicionário
                                detail['total'] = new_total
                            except (ValueError, TypeError):
                                # Se a conversão falhar, mantém o valor original ou 0
                                detail['total'] = detail.get("total", 0)

                    detail['average_per_night'] = round(detail['total'] / number_of_nights, 0) if number_of_nights > 0 else detail['total']
                    cleaned.append({
                        "id_type": r.get("id_type"),
                        "type": r.get("type"),
                        "details": details
                    })

            log_entry.status_message = "SUCCESS"
            log_entry.save()
            return Response({"availability": cleaned, "status": "OK"}, status=200)

        except Exception as e:
            log_entry = log_received_json(
                client_instance=client, 
                data=data, 
                origin_name='API_Hotel_Validation',
                status_message='Pending Validation'
            )            
            log_entry.status_message = f"ERROR: {str(e)}"
            log_entry.save()
            logger.exception("Erro ao verificar disponibilidade")
            return Response({"detail": str(e)}, status=500)

class MakeReservationView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Efetua uma reserva para clientes do tipo hotel",
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
            required=["from", "to", "adults", "children", "rooms", "id_fee", "id_type", "document_guest", "guest", "phone_guest", "guest_data", "contact_id"],
            properties={
                "from": openapi.Schema(type=openapi.TYPE_STRING, format="date"),
                "to": openapi.Schema(type=openapi.TYPE_STRING, format="date"),
                "adults": openapi.Schema(type=openapi.TYPE_INTEGER),
                "children": openapi.Schema(type=openapi.TYPE_INTEGER),
                'children_age': openapi.Schema(
                    type=openapi.TYPE_STRING, # Alterado de TYPE_ARRAY para TYPE_STRING
                    description='Idades das crianças, se houver, separadas por vírgula (ex: "3,5,7")',
                ),              
                "rooms": openapi.Schema(type=openapi.TYPE_INTEGER),
                "id_fee": openapi.Schema(type=openapi.TYPE_INTEGER),
                "id_type": openapi.Schema(type=openapi.TYPE_INTEGER),
                "document_guest": openapi.Schema(type=openapi.TYPE_STRING),
                "guest": openapi.Schema(type=openapi.TYPE_STRING),
                "phone_guest": openapi.Schema(type=openapi.TYPE_STRING),
                "observation": openapi.Schema(type=openapi.TYPE_STRING),
                "origin": openapi.Schema(type=openapi.TYPE_STRING),
                "guest_data": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "document_guest": openapi.Schema(type=openapi.TYPE_STRING),
                            "guest": openapi.Schema(type=openapi.TYPE_STRING),
                            "guest_pax": openapi.Schema(type=openapi.TYPE_STRING),
                            "phone_guest": openapi.Schema(type=openapi.TYPE_STRING),
                        },
                        required=["document_guest", "guest"]
                    )
                ),
                "contact_id": openapi.Schema(type=openapi.TYPE_STRING, description='Contact ID')
            }
        )
    )
    def post(self, request, client_type):
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response({"detail": "Authorization header missing or invalid"}, status=403)

            token = auth_header.split(" ")[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({"detail": "Invalid or inactive client"}, status=403)

            if client_type != 'hotel':
                return Response({"detail": "Unsupported client type"}, status=400)

            data = request.data
            # 1. CRIA O LOG INICIALMENTE COM UM STATUS TEMPORÁRIO
            log_entry = log_received_json(
                client_instance=client, 
                data=data, 
                origin_name='API_Hotel_Validation',
                status_message='Pending Validation'
            )             
            from_date = datetime.strptime(data.get("from"), "%Y-%m-%d").date()
            to_date = datetime.strptime(data.get("to"), "%Y-%m-%d").date()
            today = date.today()
            
            try:
                adults = parse_int(data, "adults")
                children = parse_int(data, "children")
                rooms = parse_int(data, "rooms")
            except ValueError as ve:
                return Response({"detail": str(ve)}, status=400)            

            if from_date < today:
                return Response({"detail": "From date must be today or in the future"}, status=400)
            if to_date <= from_date:
                return Response({"detail": "To date must be after from date"}, status=400)
            if adults <= 0:
                return Response({"detail": "Adults must be greater than 0"}, status=400)
            if children < 0:
                return Response({"detail": "Children must be 0 or greater"}, status=400)
            if rooms <= 0:
                return Response({"detail": "Rooms must be greater than 0"}, status=400)

            guests = data.get("guest_data", [])
            for g in guests:
                if not g.get("document_guest") or not g.get("guest"):
                    return Response({"detail": "Each guest must have name and document"}, status=400)
                
            # --- Validação children_age (Versão Atualizada) ---
            children_count = int(data.get('children', 0))
            children_age_input = data.get('children_age') # Campo original (pode ser string '2,10', lista, ou None)
            children_ages = [] # A lista final de inteiros que você usará no payload

            error_message = None

            if children_count > 0:
                if not children_age_input:
                    error_message = 'children_age is required when children > 0'
                elif isinstance(children_age_input, str):
                    try:
                        # Tenta dividir a string e converter para inteiros
                        age_strings = [a.strip() for a in children_age_input.split(',') if a.strip()]
                        children_ages = [int(age) for age in age_strings]
                    except ValueError:
                        error_message = 'Invalid children_age format. Must be a comma-separated string of integers (e.g., "2,10")'
                elif isinstance(children_age_input, list):
                    # Mantenha o suporte se for passado acidentalmente como lista, mas garanta que são inteiros
                    try:
                        children_ages = [int(age) for age in children_age_input]
                    except ValueError:
                        error_message = 'Each child age in the list must be an integer'
                else:
                    error_message = 'children_age must be a string (e.g., "2,10")'

                # Verifica se a contagem de idades corresponde à contagem de crianças
                if not error_message and len(children_ages) != children_count:
                    error_message = f'children_age must contain exactly {children_count} ages, but found {len(children_ages)}'
                    
                # Verifica se todas as idades são válidas
                if not error_message:
                    for age in children_ages:
                        if age < 0:
                            error_message = 'Each child age must be a positive integer'
                            break
                            
            elif children_count == 0:
                # Se não há crianças, o campo children_age deve estar ausente ou vazio
                if children_age_input and (isinstance(children_age_input, str) and children_age_input.strip() != '' or children_age_input):
                    error_message = 'children_age should be empty when children = 0'

            # Tratamento do erro (se houver)
            if error_message:
                log_entry.status_message = f"ERROR: {error_message}"
                log_entry.save()
                return Response({'detail': error_message}, status=400)

            # Se há crianças, verificar se as idades foram informadas corretamente
            if children_count > 0:
                if not isinstance(children_ages, list):
                    log_entry.status_message = "ERROR: children_age must be a list of ages"
                    log_entry.save()
                    return Response({'detail': 'children_age must be a list of ages (e.g. [3,5,7])'}, status=400)
                if len(children_ages) != children_count:
                    log_entry.status_message = f"ERROR: children_age must contain exactly {children_count} items"
                    log_entry.save()
                    return Response({'detail': f'children_age must contain exactly {children_count} items'}, status=400)
                for age in children_ages:
                    if not isinstance(age, int) or age < 0:
                        log_entry.status_message = "ERROR: Each child age must be a positive integer"
                        log_entry.save()
                        return Response({'detail': 'Each child age must be a positive integer'}, status=400)
            else:
                # Se não há crianças, o campo children_age deve estar ausente ou vazio
                if children_ages:
                    log_entry.status_message = "ERROR: children_age should be empty when children = 0"
                    log_entry.save()
                    return Response({'detail': 'children_age should be empty when children = 0'}, status=400)                 

            payload = data.copy()
            payload["token"] = client.api_token
            url = f"{client.api_address}/app/reservations/makeReservation"

            start_time = time.monotonic()
            response = requests.post(url, json=payload, timeout=30)
            end_time = time.monotonic()
            elapsed = round(end_time - start_time, 3)

            response_data = response.json()
            
            contact_id = data.get('contact_id')
            if not contact_id:
                contact_id = 'unknown'

            LogIntegration.objects.create(
                client_id=client,
                origin=data.get("origin"),
                contact_id=contact_id,
                to=url,
                content=payload,
                response=response_data,
                status_http=response.status_code,
                response_time=elapsed
            )

            try:
                msg = response_data['data'][0]['response'][0]['msg']
            except (KeyError, IndexError, TypeError):
                msg = "Reserva realizada com sucesso."

            log_entry.status_message = "SUCCESS"
            log_entry.save()
            return Response({"message": msg}, status=response.status_code)

        except Exception as e:
            log_entry = log_received_json(
                client_instance=client, 
                data=data, 
                origin_name='API_Hotel_Validation',
                status_message='Pending Validation'
            )            
            log_entry.status_message = f"ERROR: {str(e)}"
            log_entry.save()            
            logger.exception("Erro ao realizar reserva")
            return Response({"detail": str(e)}, status=500)

def _parse_int(value, field_name):
    """Converte para int aceitando string '10' etc.; lança ValueError com mensagem amigável."""
    try:
        return int(str(value).strip())
    except Exception:
        raise ValueError(f"Field '{field_name}' must be an integer.")

def _parse_date(value, field_name):
    """Converte YYYY-MM-DD para date; lança ValueError se inválido."""
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except Exception:
        raise ValueError(f"Field '{field_name}' must be a date in format YYYY-MM-DD.")

def _mask_card(card: str) -> str:
    """Mascarar cartão para logs: mantém só últimos 4 dígitos."""
    if not card:
        return ""
    digits = re.sub(r"\D", "", card)
    tail = digits[-4:] if len(digits) >= 4 else digits
    return f"**** **** **** {tail}" if tail else "****"


class MakeMultiReservationsView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Efetua múltiplas reservas (um POST por quarto) para clientes do tipo hotel.",
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
            type=openapi.TYPE_ARRAY,
            items=openapi.Items(
                type=openapi.TYPE_OBJECT,
                required=[
                    "full_name", "adults", "childrens", "document", "phone",
                    "payment_method", "check_in", "check_out", "id_type", "id_fee"
                ],
                properties={
                    "full_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "adults": openapi.Schema(type=openapi.TYPE_STRING, description="int ou string numérica"),
                    "childrens": openapi.Schema(type=openapi.TYPE_STRING, description="int ou string numérica"),
                    "document": openapi.Schema(type=openapi.TYPE_STRING),
                    "phone": openapi.Schema(type=openapi.TYPE_STRING),
                    "payment_method": openapi.Schema(type=openapi.TYPE_STRING),
                    "credit_card_data": openapi.Schema(type=openapi.TYPE_STRING, description="será concatenado em observation"),
                    "check_in": openapi.Schema(type=openapi.TYPE_STRING, format="date"),
                    "check_out": openapi.Schema(type=openapi.TYPE_STRING, format="date"),
                    "id_type": openapi.Schema(type=openapi.TYPE_STRING, description="int ou string numérica"),
                    "id_fee": openapi.Schema(type=openapi.TYPE_STRING, description="int ou string numérica"),
                    # campos opcionais extras, se quiser:
                    "origin": openapi.Schema(type=openapi.TYPE_STRING),
                    "contact_id": openapi.Schema(type=openapi.TYPE_STRING, description='Contact ID')
                }
            )
        ),
        responses={
            200: "JSON com resumo e detalhes por reserva"
        }
    )
    def post(self, request, client_type):
        try:
            # --- Auth + client ---
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response({"detail": "Authorization header missing or invalid"}, status=403)
            token = auth_header.split(" ")[1]

            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({"detail": "Invalid or inactive client"}, status=403)

            if client_type != 'hotel':
                return Response({"detail": "Unsupported client type"}, status=400)

            # --- Entrada deve ser uma lista ---
            data = request.data
            if not isinstance(data, list) or len(data) == 0:
                return Response({"detail": "Request body must be a non-empty JSON array."}, status=400)

            url = f"{client.api_address}/app/reservations/makeReservation"
            today = date.today()

            results = []
            success_count = 0
            fail_count = 0

            for idx, item in enumerate(data):
                # Valida campos obrigatórios por item
                missing = [k for k in ["full_name","adults","childrens","document","phone",
                                       "payment_method","check_in","check_out","id_type","id_fee"]
                           if item.get(k) in (None, "")]
                if missing:
                    results.append({
                        "index": idx,
                        "full_name": item.get("full_name"),
                        "status": "error",
                        "message": f"Missing required fields: {', '.join(missing)}"
                    })
                    fail_count += 1
                    continue

                try:
                    # Parse e validações
                    check_in = _parse_date(item["check_in"], "check_in")
                    check_out = _parse_date(item["check_out"], "check_out")
                    if check_in < today:
                        raise ValueError("check_in must be today or in the future.")
                    if check_out <= check_in:
                        raise ValueError("check_out must be after check_in.")

                    adults = _parse_int(item["adults"], "adults")
                    childrens = _parse_int(item["childrens"], "childrens")
                    id_type = _parse_int(item["id_type"], "id_type")
                    id_fee = _parse_int(item["id_fee"], "id_fee")

                    if adults <= 0:
                        raise ValueError("adults must be greater than 0.")
                    if childrens < 0:
                        raise ValueError("childrens must be 0 or greater.")

                    # observation = payment_method | credit_card_data
                    payment_method = str(item.get("payment_method", "")).strip()
                    cc_raw = str(item.get("credit_card_data", "")).strip()
                    observation = f"{payment_method} | {cc_raw}" if payment_method or cc_raw else ""

                    # Monta payload esperado pelo endpoint do cliente
                    # (espelha a sua rota de 1 quarto, mapeando nomes)
                    payload = {
                        "from": check_in.strftime("%Y-%m-%d"),
                        "to": check_out.strftime("%Y-%m-%d"),
                        "adults": adults,
                        "children": childrens,
                        "rooms": 1,  # 1 quarto por item
                        "id_fee": id_fee,
                        "id_type": id_type,
                        "document_guest": item["document"],
                        "guest": item["full_name"],
                        "phone_guest": item["phone"],
                        "observation": observation,
                        "origin": item.get("origin"),
                        "guest_data": [
                            {
                                "document_guest": item["document"],
                                "guest": item["full_name"],
                                "guest_pax": str(adults + childrens),
                                "phone_guest": item["phone"],
                            }
                        ],
                        "token": client.api_token,  # auth do cliente externo
                    }

                    # POST por reserva
                    start_time = time.monotonic()
                    resp = requests.post(url, json=payload, timeout=30)
                    elapsed = round(time.monotonic() - start_time, 3)

                    # response safe json
                    try:
                        response_data = resp.json()
                    except Exception:
                        response_data = {"raw": resp.text}

                    # LogIntegration (mascarando cartão nos logs)
                    masked_obs = f"{payment_method} | {_mask_card(cc_raw)}" if payment_method or cc_raw else ""
                    log_payload = {**payload, "observation": masked_obs}
                    
                    contact_id = request.data.get('contact_id')
                    if not contact_id:
                        contact_id = 'unknown'       
             
                    LogIntegration.objects.create(
                        client_id=client,
                        origin=item.get("origin"),
                        contact_id=contact_id,
                        to=url,
                        content=log_payload,
                        response=response_data,
                        status_http=resp.status_code,
                        response_time=elapsed
                    )

                    # extrai mensagem amigável, se possível
                    try:
                        msg = response_data['data'][0]['response'][0]['msg']
                    except (KeyError, IndexError, TypeError):
                        msg = "Reserva processada."

                    if 200 <= resp.status_code < 300:
                        success_count += 1
                        results.append({
                            "index": idx,
                            "full_name": item["full_name"],
                            "status": "success",
                            "http_status": resp.status_code,
                            "message": msg
                        })
                    else:
                        fail_count += 1
                        results.append({
                            "index": idx,
                            "full_name": item["full_name"],
                            "status": "error",
                            "http_status": resp.status_code,
                            "message": msg,
                            "details": response_data
                        })

                except ValueError as ve:
                    fail_count += 1
                    results.append({
                        "index": idx,
                        "full_name": item.get("full_name"),
                        "status": "error",
                        "message": str(ve)
                    })
                except requests.Timeout:
                    fail_count += 1
                    results.append({
                        "index": idx,
                        "full_name": item.get("full_name"),
                        "status": "error",
                        "message": "Upstream timeout (30s) while creating reservation."
                    })
                except Exception as e:
                    logger.exception("Erro ao processar reserva index=%s", idx)
                    fail_count += 1
                    results.append({
                        "index": idx,
                        "full_name": item.get("full_name"),
                        "status": "error",
                        "message": str(e)
                    })

            summary = {
                "requested": len(data),
                "succeeded": success_count,
                "failed": fail_count,
            }

            # Status HTTP geral: 207 (Multi-Status) se teve mistura, 200 se tudo ok, 400 se tudo falhou
            if success_count and fail_count:
                http_status = 207
            elif success_count and not fail_count:
                http_status = 200
            else:
                http_status = 400

            return Response({
                "summary": summary,
                "results": results
            }, status=http_status)

        except Exception as e:
            logger.exception("Erro em MakeMultiReservationsView")
            return Response({"detail": str(e)}, status=500)

class GetReservationView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Consulta reserva pelo ID para clientes do tipo hotel",
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
            required=["id_reserva"],
            properties={
                "id_reserva": openapi.Schema(type=openapi.TYPE_INTEGER),
                "origin": openapi.Schema(type=openapi.TYPE_STRING),
                "contact_id": openapi.Schema(type=openapi.TYPE_STRING, description='Contact ID')
            }
        )
    )
    def post(self, request, client_type):
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response({"detail": "Authorization header missing or invalid"}, status=403)

            token = auth_header.split(" ")[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({"detail": "Invalid or inactive client"}, status=403)

            if client_type != 'hotel':
                return Response({"detail": "Unsupported client type"}, status=400)

            id_reserva = request.data.get("id_reserva")
            if not id_reserva:
                return Response({"detail": "Missing reservation ID"}, status=400)

            payload = {
                "token": client.api_token,
                "id_reserva": id_reserva
            }

            url = f"{client.api_address}/app/reservations/getReservation"
            start_time = time.monotonic()
            response = requests.post(url, json=payload, timeout=30)
            end_time = time.monotonic()
            elapsed = round(end_time - start_time, 3)

            response_data = response.json()
            
            contact_id = request.data.get('contact_id')
            if not contact_id:
                contact_id = 'unknown'            

            LogIntegration.objects.create(
                client_id=client,
                origin=request.data.get("origin"),
                contact_id=contact_id,
                to=url,
                content=payload,
                response=response_data,
                status_http=response.status_code,
                response_time=elapsed
            )

            reserva = response_data.get("reserva", [])

            for r in reserva:
                id_type = r.get("id_type")
                room = HotelRooms.objects.filter(client_id=client, room_code=id_type).first()
                if room:
                    r["room_type"] = room.room_type

            return Response({"reserva": reserva}, status=response.status_code)

        except Exception as e:
            logger.exception("Erro ao consultar reserva")
            return Response({"detail": str(e)}, status=500)

class ChangeReservationView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Modifica uma reserva existente para clientes do tipo hotel",
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
            required=["from", "to", "adults", "children", "rooms", "id_fee", "id_type", "document_guest", "guest", "phone_guest", "id_reserva"],
            properties={
                "from": openapi.Schema(type=openapi.TYPE_STRING, format="date"),
                "to": openapi.Schema(type=openapi.TYPE_STRING, format="date"),
                "adults": openapi.Schema(type=openapi.TYPE_INTEGER),
                "children": openapi.Schema(type=openapi.TYPE_INTEGER),
                "rooms": openapi.Schema(type=openapi.TYPE_INTEGER),
                "id_fee": openapi.Schema(type=openapi.TYPE_INTEGER),
                "id_type": openapi.Schema(type=openapi.TYPE_INTEGER),
                "document_guest": openapi.Schema(type=openapi.TYPE_STRING),
                "guest": openapi.Schema(type=openapi.TYPE_STRING),
                "phone_guest": openapi.Schema(type=openapi.TYPE_STRING),
                "id_reserva": openapi.Schema(type=openapi.TYPE_INTEGER),
                "observation": openapi.Schema(type=openapi.TYPE_STRING),
                "origin": openapi.Schema(type=openapi.TYPE_STRING),
                "contact_id": openapi.Schema(type=openapi.TYPE_STRING, description='Contact ID'),
                "guest_data": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "document_guest": openapi.Schema(type=openapi.TYPE_STRING),
                            "guest": openapi.Schema(type=openapi.TYPE_STRING),
                            "guest_pax": openapi.Schema(type=openapi.TYPE_STRING),
                            "phone_guest": openapi.Schema(type=openapi.TYPE_STRING),
                        }
                    )
                )
            }
        )
    )
    def post(self, request, client_type):
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response({"detail": "Authorization header missing or invalid"}, status=403)

            token = auth_header.split(" ")[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({"detail": "Invalid or inactive client"}, status=403)

            if client_type != 'hotel':
                return Response({"detail": "Unsupported client type"}, status=400)

            data = request.data
            from_date = datetime.strptime(data.get("from"), "%Y-%m-%d").date()
            to_date = datetime.strptime(data.get("to"), "%Y-%m-%d").date()
            today = date.today()

            if from_date < today:
                return Response({"detail": "From date must be today or in the future"}, status=400)
            if to_date <= from_date:
                return Response({"detail": "To date must be after from date"}, status=400)
            if data.get("adults", 0) <= 0:
                return Response({"detail": "Adults must be greater than 0"}, status=400)
            if data.get("children", 0) < 0:
                return Response({"detail": "Children must be 0 or greater"}, status=400)
            if data.get("rooms", 0) <= 0:
                return Response({"detail": "Rooms must be greater than 0"}, status=400)

            for guest in data.get("guest_data", []):
                if not guest.get("guest") or not guest.get("document_guest"):
                    return Response({"detail": "Guest name and document are required for each guest."}, status=400)

            payload = data.copy()
            payload["token"] = client.api_token
            url = f"{client.api_address}/app/reservations/changeReservation"

            start_time = time.monotonic()
            response = requests.post(url, json=payload, timeout=10)
            end_time = time.monotonic()
            elapsed = round(end_time - start_time, 3)

            response_data = response.json()
            
            contact_id = request.data.get('contact_id')
            if not contact_id:
                contact_id = 'unknown'            

            LogIntegration.objects.create(
                client_id=client,
                origin=data.get("origin"),
                contact_id=contact_id,
                to=url,
                content=payload,
                response=response_data,
                status_http=response.status_code,
                response_time=elapsed
            )

            msg = response_data.get("data", [{}])[0].get("response", [{}])[0].get("msg")
            return Response({"message": msg}, status=response.status_code)

        except Exception as e:
            logger.exception("Erro ao modificar reserva")
            return Response({"detail": str(e)}, status=500)

class CancelReservationView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Cancela uma reserva existente para clientes do tipo hotel",
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
            required=["id_reserva", "reason"],
            properties={
                "id_reserva": openapi.Schema(type=openapi.TYPE_STRING),
                "reason": openapi.Schema(type=openapi.TYPE_STRING),
                "origin": openapi.Schema(type=openapi.TYPE_STRING),
                "contact_id": openapi.Schema(type=openapi.TYPE_STRING, description='Contact ID')
            }
        )
    )
    def post(self, request, client_type):
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response({"detail": "Authorization header missing or invalid"}, status=403)

            token = auth_header.split(" ")[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({"detail": "Invalid or inactive client"}, status=403)

            if client_type != 'hotel':
                return Response({"detail": "Unsupported client type"}, status=400)

            data = request.data
            if not data.get("id_reserva") or not data.get("reason"):
                return Response({"detail": "Missing required fields"}, status=400)

            payload = {
                "token": client.api_token,
                "id_reserva": data.get("id_reserva"),
                "reason": data.get("reason")
            }

            url = f"{client.api_address}/app/reservations/cancelReservation"
            start_time = time.monotonic()
            response = requests.post(url, json=payload, timeout=10)
            end_time = time.monotonic()
            elapsed = round(end_time - start_time, 3)

            response_data = response.json()
            
            contact_id = request.data.get('contact_id')
            if not contact_id:
                contact_id = 'unknown'            

            LogIntegration.objects.create(
                client_id=client,
                origin=data.get("origin"),
                contact_id=contact_id,
                to=url,
                content=payload,
                response=response_data,
                status_http=response.status_code,
                response_time=elapsed
            )

            reserva = response_data.get("reserva", [{}])[0]
            return Response({"reserva": reserva}, status=response.status_code)

        except Exception as e:
            logger.exception("Erro ao cancelar reserva")
            return Response({"detail": str(e)}, status=500)

class LogIntegrationView(APIView):
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Grava log de integração",
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
            required=['content', 'response', 'status_http'],
            properties={
                'origin': openapi.Schema(type=openapi.TYPE_STRING, description='Origin of the log (whatsapp, facebook, instagram)'),
                'contact_id': openapi.Schema(type=openapi.TYPE_STRING, description='Contact ID'),
                'to': openapi.Schema(type=openapi.TYPE_STRING, description='Destination'),
                'content': openapi.Schema(type=openapi.TYPE_STRING, description='Payload enviado'),
                'response': openapi.Schema(type=openapi.TYPE_STRING, description='Resposta recebida'),
                'status_http': openapi.Schema(type=openapi.TYPE_INTEGER, description='Status HTTP')
            }
        ),
        responses={
            201: openapi.Response('Log registrado com sucesso'),
            403: openapi.Response('Token inválido ou cliente inativo'),
            500: openapi.Response('Erro interno')
        }
    )
    def post(self, request):
        try:
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return Response({'detail': 'Authorization header missing or invalid'}, status=403)

            token = auth_header.split(' ')[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({'detail': 'Invalid or inactive client'}, status=403)

            data = request.data
            
            contact_id = request.data.get('contact_id')
            if not contact_id:
                contact_id = 'unknown'
                            
            log = LogIntegration.objects.create(
                client_id=client,
                origin=data.get('origin'),
                contact_id=contact_id,
                to=data.get('to'),
                content=data.get('content'),
                response=data.get('response'),
                status_http=data.get('status_http')
            )

            return Response({'log_id': log.id, 'created_at': log.created_at}, status=201)

        except Exception as e:
            logger.exception("Erro ao gravar log de integração")
            return Response({"detail": str(e)}, status=500)

class GetRelevantContextView(APIView):
    """
    Retorna contexto relevante baseado na mensagem do usuário
    usando busca por palavras-chave (RAG leve)
    """
    authentication_classes = []
    permission_classes = []
    
    @swagger_auto_schema(
        operation_description="Busca contexto relevante para a mensagem",
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
                    description='Máximo de contextos a retornar (padrão: 3)',
                    default=3
                ),
                'categories': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(type=openapi.TYPE_STRING),
                    description='Categorias específicas (opcional)',
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
            # Autenticação
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response({"detail": "Authorization header inválido"}, status=403)
            
            token = auth_header.split(" ")[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({"detail": "Token inválido"}, status=403)
            
            # Parâmetros
            message = request.data.get('message', '').lower()
            max_contexts = request.data.get('max_contexts', 3)
            specific_categories = request.data.get('categories', [])
            
            if not message:
                return Response({"detail": "Campo 'message' é obrigatório"}, status=400)
            
            # Log da mensagem
            logger.info(f"[RAG] Cliente: {client.name} | Mensagem: {message[:100]}")
            
            # Buscar contextos relevantes
            contexts = self._search_relevant_contexts(
                client, 
                message, 
                max_contexts,
                specific_categories
            )
            
            # Log dos contextos encontrados
            logger.info(f"[RAG] Contextos retornados: {[c['category'] for c in contexts]}")
            logger.info(f"[RAG] Scores: {[(c['category'], c.get('score', 0)) for c in contexts]}")
            
            # Formatar resposta
            formatted_context = "\n\n---\n\n".join([c['content'] for c in contexts])
            
            return Response({
                "context": formatted_context,
                "contexts_used": [c['category'] for c in contexts],
                "total_contexts": len(contexts)
            }, status=200)
            
        except Exception as e:
            logger.exception("Erro ao buscar contexto")
            return Response({"detail": str(e)}, status=500)
    
    def _normalize_text(self, text):
        """
        Normaliza texto para busca mais flexível
        Remove espaços extras, acentos opcionalmente
        """
        import unicodedata
        
        # Remove acentos
        text = ''.join(
            c for c in unicodedata.normalize('NFD', text)
            if unicodedata.category(c) != 'Mn'
        )
        
        # Lowercase e remove espaços extras
        text = ' '.join(text.lower().split())
        
        return text
    
    def _search_relevant_contexts(self, client, message, max_contexts, specific_categories):
        """
        Busca contextos relevantes usando palavras-chave
        OTIMIZADO: Busca mais flexível e melhor scoring
        """
        # Normalizar mensagem
        normalized_message = self._normalize_text(message)
        message_words = set(normalized_message.split())
        
        # Buscar todos os contextos ativos do cliente
        query = ContextCategory.objects.filter(client=client, active=True)
        
        # Se categorias específicas foram pedidas
        if specific_categories:
            query = query.filter(category__in=specific_categories)
        
        contexts = query.all()
        
        # Calcular score de relevância para cada contexto
        scored_contexts = []
        for ctx in contexts:
            score = 0
            keywords = ctx.keywords or []
            matched_keywords = []
            
            # Pontuação por palavra-chave encontrada
            for keyword in keywords:
                normalized_keyword = self._normalize_text(keyword)
                
                # Match exato na mensagem completa
                if normalized_keyword in normalized_message:
                    score += 3
                    matched_keywords.append(keyword)
                
                # Match de palavra individual
                elif normalized_keyword in message_words:
                    score += 2
                    matched_keywords.append(keyword)
                
                # Match parcial (substring)
                elif any(normalized_keyword in word for word in message_words):
                    score += 1
                    matched_keywords.append(keyword)
            
            # Adiciona prioridade do contexto (peso maior)
            # Multiplica por 2 para dar mais peso à prioridade
            score += (ctx.priority * 2)
            
            if score > 0 or ctx.priority >= 10:  # Sempre inclui contextos de prioridade máxima
                scored_contexts.append({
                    'category': ctx.category,
                    'content': ctx.content,
                    'score': score,
                    'priority': ctx.priority,
                    'matched_keywords': matched_keywords[:3]  # Primeiras 3 keywords
                })
        
        # Ordenar por score (e desempate por prioridade)
        scored_contexts.sort(key=lambda x: (x['score'], x['priority']), reverse=True)
        
        # Log dos scores para debug
        for ctx in scored_contexts[:5]:  # Top 5
            logger.debug(
                f"[RAG] {ctx['category']}: score={ctx['score']}, "
                f"priority={ctx['priority']}, keywords={ctx['matched_keywords']}"
            )
        
        # Se não encontrou nenhum com keywords, retorna os mais importantes (por priority)
        if not scored_contexts:
            logger.warning("[RAG] Nenhuma keyword encontrada! Usando fallback por prioridade")
            fallback = contexts.order_by('-priority')[:max_contexts]
            return [
                {
                    'category': c.category, 
                    'content': c.content,
                    'score': 0,
                    'priority': c.priority
                } 
                for c in fallback
            ]
        
        return scored_contexts[:max_contexts]


class GetSystemPromptView(APIView):
    """
    Retorna o prompt base do sistema
    """
    authentication_classes = []
    permission_classes = []
    
    @swagger_auto_schema(
        operation_description="Retorna o prompt base ativo do cliente",
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
                'prompt_name': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Nome do prompt (opcional, retorna o principal se vazio)',
                    default='main'
                )
            }
        ),
        responses={
            200: "Prompt retornado",
            403: "Token inválido",
            404: "Prompt não encontrado"
        }
    )
    def post(self, request):
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response({"detail": "Authorization header inválido"}, status=403)
            
            token = auth_header.split(" ")[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({"detail": "Token inválido"}, status=403)
            
            prompt_name = request.data.get('prompt_name', 'main')
            
            # Log
            logger.info(f"[Prompt] Cliente: {client.name} | Buscando: {prompt_name}")
            
            # Buscar prompt ativo
            prompt = SystemPrompt.objects.filter(
                client=client,
                name=prompt_name,
                is_active=True
            ).order_by('-updated_at').first()
            
            if not prompt:
                logger.warning(f"[Prompt] Prompt '{prompt_name}' não encontrado para {client.name}")
                return Response({"detail": "Prompt não encontrado"}, status=404)
            
            logger.info(f"[Prompt] Retornando: {prompt.name} v{prompt.version}")
            
            return Response({
                "prompt": prompt.prompt_text,
                "version": prompt.version,
                "name": prompt.name
            }, status=200)
            
        except Exception as e:
            logger.exception("Erro ao buscar prompt")
            return Response({"detail": str(e)}, status=500)


class ManageContextView(APIView):
    """
    CRUD para gerenciar contextos
    """
    authentication_classes = []
    permission_classes = []
    
    @swagger_auto_schema(
        operation_description="Cria ou atualiza um contexto",
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
                'category': openapi.Schema(type=openapi.TYPE_STRING),
                'content': openapi.Schema(type=openapi.TYPE_STRING),
                'keywords': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(type=openapi.TYPE_STRING)
                ),
                'priority': openapi.Schema(type=openapi.TYPE_INTEGER, default=0)
            },
            required=['category', 'content']
        )
    )
    def post(self, request):
        """Cria ou atualiza contexto"""
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response({"detail": "Authorization header inválido"}, status=403)
            
            token = auth_header.split(" ")[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({"detail": "Token inválido"}, status=403)
            
            category = request.data.get('category')
            content = request.data.get('content')
            keywords = request.data.get('keywords', [])
            priority = request.data.get('priority', 0)
            
            if not category or not content:
                return Response({"detail": "category e content são obrigatórios"}, status=400)
            
            # Update or Create
            context, created = ContextCategory.objects.update_or_create(
                client=client,
                category=category,
                defaults={
                    'content': content,
                    'keywords': keywords,
                    'priority': priority,
                    'active': True
                }
            )
            
            return Response({
                "message": "Contexto criado" if created else "Contexto atualizado",
                "category": context.category,
                "id": context.id
            }, status=201 if created else 200)
            
        except Exception as e:
            logger.exception("Erro ao gerenciar contexto")
            return Response({"detail": str(e)}, status=500)
    
    @swagger_auto_schema(
        operation_description="Lista todos os contextos do cliente",
        manual_parameters=[
            openapi.Parameter(
                name='Authorization',
                in_=openapi.IN_HEADER,
                type=openapi.TYPE_STRING,
                description="Bearer {token}",
                required=True
            )
        ]
    )
    def get(self, request):
        """Lista contextos"""
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return Response({"detail": "Authorization header inválido"}, status=403)
            
            token = auth_header.split(" ")[1]
            client = Client.objects.filter(token=token, active=True).first()
            if not client:
                return Response({"detail": "Token inválido"}, status=403)
            
            contexts = ContextCategory.objects.filter(client=client, active=True)
            
            return Response({
                "contexts": [
                    {
                        "id": c.id,
                        "category": c.category,
                        "content": c.content,
                        "keywords": c.keywords,
                        "priority": c.priority
                    } for c in contexts
                ]
            }, status=200)
            
        except Exception as e:
            logger.exception("Erro ao listar contextos")
            return Response({"detail": str(e)}, status=500)
