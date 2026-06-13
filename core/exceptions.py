"""
Handler global de excepciones para DRF.
Normaliza todas las respuestas de error al formato:
  {"error": "mensaje", "detalle": {...}}
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        data = response.data

        # Formato unificado
        if isinstance(data, dict):
            error_msg = data.get('detail', str(data))
        elif isinstance(data, list):
            error_msg = data[0] if data else 'Error desconocido'
        else:
            error_msg = str(data)

        response.data = {
            'error': str(error_msg),
            'detalle': data if isinstance(data, dict) and 'detail' not in data else None,
            'status': response.status_code,
        }

    return response
