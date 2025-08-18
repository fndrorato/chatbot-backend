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
            required=['from', 'to', 'adults', 'children', 'rooms', 'origin'],
            properties={
                'from': openapi.Schema(type=openapi.TYPE_STRING, format='date'),
                'to': openapi.Schema(type=openapi.TYPE_STRING, format='date'),
                'adults': openapi.Schema(type=openapi.TYPE_INTEGER),
                'children': openapi.Schema(type=openapi.TYPE_INTEGER),
                'rooms': openapi.Schema(type=openapi.TYPE_INTEGER),
                'origin': openapi.Schema(type=openapi.TYPE_STRING),
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
                return Response({'detail': 'Children must be 0 or greater'}, status=400)
            if int(data.get('rooms', 0)) <= 0:
                return Response({'detail': 'Rooms must be greater than 0'}, status=400)

            origin = data.get('origin')

            payload = {
                'token': client.api_token,
                'from': data.get('from'),
                'to': data.get('to'),
                'adults': data.get('adults'),
                'children': data.get('children'),
                'rooms': data.get('rooms'),
            }

            # ---------- Requisição externa ----------
            url = f"{client.api_address}/app/reservations/checkAvailability"
            start_time = time.monotonic()
            try:
                response = requests.post(url, json=payload, timeout=30)
            except requests.Timeout as ex:
                elapsed = round(time.monotonic() - start_time, 3)
                LogIntegration.objects.create(
                    client_id=client, origin=origin, to=url, content=payload,
                    response={'detail': 'timeout'}, status_http=504, response_time=elapsed
                )
                return Response({'detail': 'Upstream timeout'}, status=504)
            except requests.RequestException as ex:
                elapsed = round(time.monotonic() - start_time, 3)
                LogIntegration.objects.create(
                    client_id=client, origin=origin, to=url, content=payload,
                    response={'detail': str(ex)}, status_http=502, response_time=elapsed
                )
                return Response({'detail': 'Upstream error', 'error': str(ex)}, status=502)

            elapsed = round(time.monotonic() - start_time, 3)

            # ---------- Parse do JSON ----------
            try:
                response_data = response.json()
            except ValueError:
                LogIntegration.objects.create(
                    client_id=client, origin=origin, to=url, content=payload,
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
                if not room_code:
                    continue
                # evita duplicata
                if not HotelRooms.objects.filter(client_id=client, room_code=room_code).exists():
                    HotelRooms.objects.create(
                        client_id=client,
                        room_code=room_code,
                        room_type=room_type
                    )

            # ---------- Limpeza para resposta ----------
            cleaned = []
            for r in availability:
                if not isinstance(r, dict):
                    continue
                details = r.get("details", [])
                if not isinstance(details, list):
                    details = []
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
            required=["from", "to", "adults", "children", "rooms", "id_fee", "id_type", "document_guest", "guest", "phone_guest", "guest_data"],
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

            payload = data.copy()
            payload["token"] = client.api_token
            url = f"{client.api_address}/app/reservations/makeReservation"

            start_time = time.monotonic()
            response = requests.post(url, json=payload, timeout=30)
            end_time = time.monotonic()
            elapsed = round(end_time - start_time, 3)

            response_data = response.json()

            LogIntegration.objects.create(
                client_id=client,
                origin=data.get("origin"),
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

            LogIntegration.objects.create(
                client_id=client,
                origin=request.data.get("origin"),
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

            LogIntegration.objects.create(
                client_id=client,
                origin=data.get("origin"),
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

            LogIntegration.objects.create(
                client_id=client,
                origin=data.get("origin"),
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
            log = LogIntegration.objects.create(
                client_id=client,
                origin=data.get('origin'),
                to=data.get('to'),
                content=data.get('content'),
                response=data.get('response'),
                status_http=data.get('status_http')
            )

            return Response({'log_id': log.id, 'created_at': log.created_at}, status=201)

        except Exception as e:
            logger.exception("Erro ao gravar log de integração")
            return Response({"detail": str(e)}, status=500)
