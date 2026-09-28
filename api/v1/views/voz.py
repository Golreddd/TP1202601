"""
API del asistente de voz.

POST /api/v1/voz/interpretar/  → interpreta una frase (registrar/consultar/mixta/
                                  simulación); si el registro queda completo,
                                  incluye la previsualización del impacto en el
                                  plan; si es una pregunta, incluye la respuesta.
POST /api/v1/voz/confirmar/    → aplica los ítems confirmados por el usuario.
POST /api/v1/voz/deshacer/     → revierte un registro reciente (token de deshacer).

Consumida por el propio dashboard (SessionAuth + CSRF, static/js/voz.js) y
testeable con JWT/Postman como el resto de la API v1.
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.serializers.voz import (
    ConfirmarVozSerializer,
    DeshacerVozSerializer,
    InterpretarVozSerializer,
)
from financiero import voz_servicios
from financiero.voz import interpretar

logger = logging.getLogger(__name__)


class InterpretarVozView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = InterpretarVozSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        resultado = interpretar(datos['texto'], contexto_previo=datos.get('contexto_previo', ''))

        if resultado['intencion'] == 'moneda_no_soportada':
            return Response(resultado, status=status.HTTP_200_OK)

        if resultado['items'] and resultado['faltante'] is None:
            try:
                resultado['previsualizacion'] = voz_servicios.previsualizar(request.user, resultado['items'])
            except Exception:
                logger.exception('Error al previsualizar registro de voz.')
                return Response(
                    {'error': 'No se pudo calcular el impacto en tu plan. Intenta de nuevo.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        if resultado.get('consulta') is not None:
            try:
                resultado['respuesta'] = voz_servicios.responder(request.user, resultado['consulta'])
            except Exception:
                logger.exception('Error al responder consulta de voz.')
                return Response(
                    {'error': 'No se pudo calcular la respuesta. Intenta de nuevo.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(resultado, status=status.HTTP_200_OK)


class ConfirmarVozView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ConfirmarVozSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data['items']

        try:
            resultado = voz_servicios.aplicar(request.user, items)
        except Exception:
            logger.exception('Error al aplicar registro de voz.')
            return Response(
                {'error': 'No se pudo guardar el registro. Intenta de nuevo.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(resultado, status=status.HTTP_201_CREATED)


class DeshacerVozView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DeshacerVozSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        resultado = voz_servicios.deshacer(request.user, serializer.validated_data['token'])
        if not resultado['ok']:
            return Response(resultado, status=status.HTTP_400_BAD_REQUEST)
        return Response(resultado, status=status.HTTP_200_OK)
