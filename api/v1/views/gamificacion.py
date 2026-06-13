"""
API de gamificación (rachas y logros).

Endpoints:
  GET /api/v1/gamificacion/racha/    → Racha actual del usuario
  GET /api/v1/gamificacion/logros/   → Todos los logros con estado del usuario
"""
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from gamificacion.models import Logro, LogroUsuario


class RachaView(APIView):
    """GET /api/v1/gamificacion/racha/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            racha = request.user.racha
            return Response({
                'dias_consecutivos': racha.dias_consecutivos,
                'racha_maxima': racha.racha_maxima,
                'ultimo_registro': racha.ultimo_registro,
            })
        except Exception:
            return Response({'dias_consecutivos': 0, 'racha_maxima': 0, 'ultimo_registro': None})


class LogrosView(APIView):
    """
    GET /api/v1/gamificacion/logros/
    Retorna todos los logros definidos y cuáles tiene el usuario.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        todos = Logro.objects.all()
        obtenidos_ids = set(
            LogroUsuario.objects
            .filter(usuario=request.user)
            .values_list('logro_id', flat=True)
        )

        data = [
            {
                'id': logro.id,
                'codigo': logro.codigo,
                'nombre': logro.nombre,
                'descripcion': logro.descripcion,
                'icono': logro.icono,
                'puntos': logro.puntos,
                'desbloqueado': logro.id in obtenidos_ids,
            }
            for logro in todos
        ]

        total_puntos = sum(
            l['puntos'] for l in data if l['desbloqueado']
        )

        return Response({
            'logros': data,
            'desbloqueados': len(obtenidos_ids),
            'total': todos.count(),
            'puntos_totales': total_puntos,
        })
