import json
import logging
import requests
import time
from clients.models import Client
from common.utils import parse_int
from datetime import datetime, date
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from systems.models import LogIntegration, HotelRooms
from systems.hotel import reservations


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
                    type=openapi.TYPE_ARRAY,
                    description='Idades das crianças, se houver (ex: [3,5,7])',
                    items=openapi.Items(type=openapi.TYPE_INTEGER),
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
            try:
                from_date = datetime.strptime(data.get('from'), '%Y-%m-%d').date()
                to_date = datetime.strptime(data.get('to'), '%Y-%m-%d').date()
                today = date.today()
                if from_date < today:
                    return Response({'detail': 'From date must be today or in the future'}, status=400)
                if to_date <= from_date:
                    return Response({'detail': 'To date must be after from date'}, status=400)
            except Exception:
                return Response({'detail': 'Invalid date format. Use YYYY-MM-DD'}, status=400)

            if int(data.get('adults', 0)) <= 0:
                return Response({'detail': 'Adults must be greater than 0'}, status=400)
            if int(data.get('children', 0)) < 0:
                print(f'Children: {data.get("children")}')
                return Response({'detail': 'Children must be 0 or greater'}, status=400)
            if int(data.get('rooms', 0)) < 0:
                return Response({'detail': 'Rooms must be greater than 0'}, status=400)
            
            # --- Validação children_age ---
            children_count = int(data.get('children', 0))
            children_age = data.get('children_age', [])

            # Se há crianças, verificar se as idades foram informadas corretamente
            if children_count > 0:
                if not isinstance(children_age, list):
                    return Response({'detail': 'children_age must be a list of ages (e.g. [3,5,7])'}, status=400)
                if len(children_age) != children_count:
                    return Response({'detail': f'children_age must contain exactly {children_count} items'}, status=400)
                for age in children_age:
                    if not isinstance(age, int) or age < 0:
                        return Response({'detail': 'Each child age must be a positive integer'}, status=400)
            else:
                # Se não há crianças, o campo children_age deve estar ausente ou vazio
                if children_age:
                    return Response({'detail': 'children_age should be empty when children = 0'}, status=400)            

            origin = data.get('origin')
            contact_id = request.data.get('contact_id')
            children_ages = data.get('children_age', [])
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

            return Response({"availability": cleaned, "status": "OK"}, status=200)

        except Exception as e:
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
                    type=openapi.TYPE_ARRAY,
                    description='Idades das crianças, se houver (ex: [3,5,7])',
                    items=openapi.Items(type=openapi.TYPE_INTEGER),
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
                
            # --- Validação children_age ---
            children_count = int(data.get('children', 0))
            children_age = data.get('children_age', [])

            # Se há crianças, verificar se as idades foram informadas corretamente
            if children_count > 0:
                if not isinstance(children_age, list):
                    return Response({'detail': 'children_age must be a list of ages (e.g. [3,5,7])'}, status=400)
                if len(children_age) != children_count:
                    return Response({'detail': f'children_age must contain exactly {children_count} items'}, status=400)
                for age in children_age:
                    if not isinstance(age, int) or age < 0:
                        return Response({'detail': 'Each child age must be a positive integer'}, status=400)
            else:
                # Se não há crianças, o campo children_age deve estar ausente ou vazio
                if children_age:
                    return Response({'detail': 'children_age should be empty when children = 0'}, status=400)                 

            payload = data.copy()
            payload["token"] = client.api_token
            url = f"{client.api_address}/app/reservations/makeReservation"

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

            return Response({"message": msg}, status=response.status_code)

        except Exception as e:
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
