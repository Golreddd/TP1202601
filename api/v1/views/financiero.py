"""
API de registros financieros y dashboard.

GET    /api/v1/financiero/dashboard/         → Resumen del dashboard
GET    /api/v1/financiero/analisis/          → Datos para gráficos
GET    /api/v1/financiero/registros/         → Lista de registros del usuario
POST   /api/v1/financiero/registros/         → Crear nuevo registro mensual
GET    /api/v1/financiero/registros/ultimo/  → Último registro del usuario
GET    /api/v1/financiero/registros/<id>/    → Detalle de un registro
PUT    /api/v1/financiero/registros/<id>/    → Actualizar registro
DELETE /api/v1/financiero/registros/<id>/    → Eliminar registro
"""
import logging
from datetime import date

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from core.constants import MESES_ES_ABREV as MESES_ES
from financiero.models import RegistroMensual
from gamificacion.services import verificar_y_otorgar_logros
from api.v1.serializers.financiero import RegistroMensualSerializer

logger = logging.getLogger(__name__)


class RegistroMensualViewSet(ModelViewSet):
    """
    ViewSet CRUD para RegistroMensual.
    Cada usuario solo ve y modifica sus propios registros.
    """
    serializer_class   = RegistroMensualSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RegistroMensual.objects.filter(
            usuario=self.request.user
        ).order_by('-periodo')

    def perform_create(self, serializer):
        registro = serializer.save(usuario=self.request.user)
        self._post_create(registro)

    def _post_create(self, registro):
        """Acciones después de crear un registro: racha + logros."""
        try:
            self.request.user.racha.actualizar(date.today())
        except (AttributeError, ValueError, ObjectDoesNotExist) as exc:
            logger.warning('No se pudo actualizar racha del usuario %s: %s',
                           self.request.user.id, exc)

        verificar_y_otorgar_logros(self.request.user, contexto='registro')

    @action(detail=False, methods=['get'], url_path='ultimo')
    def ultimo(self, request):
        """GET /api/v1/financiero/registros/ultimo/"""
        registro = self.get_queryset().first()
        if not registro:
            return Response(
                {'error': 'No tienes registros financieros aún.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(self.get_serializer(registro).data)


class DashboardView(APIView):
    """
    GET /api/v1/financiero/dashboard/
    Retorna el resumen financiero para poblar el dashboard principal.
    perfil_completo ahora se accede directo desde usuario (sin JOIN a PerfilFinanciero).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        registros_qs = RegistroMensual.objects.filter(
            usuario=user
        ).order_by('-periodo')[:6]

        if not registros_qs.exists():
            return Response({
                'tiene_datos': False,
                'mensaje': 'Aún no tienes registros financieros. Crea tu primer registro.',
                'perfil_completo': user.perfil_completo,
            })

        registros  = list(registros_qs)
        ultimo     = registros[0]
        historial  = list(reversed(registros))

        # Racha
        racha_dias = 0
        racha_max  = 0
        try:
            racha_dias = user.racha.dias_consecutivos
            racha_max  = user.racha.racha_maxima
        except ObjectDoesNotExist:
            pass

        # Último resultado ML
        ultimo_ml = None
        resultado = user.resultados_ml.select_related('registro').first()
        if resultado:
            ultimo_ml = {
                'cluster_label': resultado.cluster_label,
                'ahorro_actual': resultado.ahorro_actual,
                'confianza':     resultado.confianza,
                'fecha':         resultado.creado_en.strftime('%d/%m/%Y'),
            }

        return Response({
            'tiene_datos':     True,
            'perfil_completo': user.perfil_completo,
            'resumen_actual':  {
                'periodo':      ultimo.periodo.strftime('%B %Y'),
                'periodo_label': f"{MESES_ES[ultimo.periodo.month]} {ultimo.periodo.year}",
                'ing_total':    round(ultimo.ing_total, 2),
                'gasto_total':  round(ultimo.gasto_total, 2),
                'ahorro_bruto': round(ultimo.ahorro_bruto, 2),
                'tasa_ahorro':  round(ultimo.tasa_ahorro, 1),
            },
            'historial_6m': [
                {
                    'periodo':      r.periodo.strftime('%Y-%m'),
                    'label':        f"{MESES_ES[r.periodo.month]} {r.periodo.year}",
                    'ing_total':    round(r.ing_total, 2),
                    'gasto_total':  round(r.gasto_total, 2),
                    'ahorro_bruto': round(r.ahorro_bruto, 2),
                    'tasa_ahorro':  round(r.tasa_ahorro, 1),
                }
                for r in historial
            ],
            'gastos_actuales': ultimo.gastos_por_categoria(),
            'racha':      {'dias': racha_dias, 'maxima': racha_max},
            'ultimo_ml':  ultimo_ml,
        })


class AnalisisView(APIView):
    """
    GET /api/v1/financiero/analisis/?meses=6
    Datos procesados para los gráficos de análisis de gastos.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        meses = min(int(request.query_params.get('meses', 6)), 12)
        registros = list(
            RegistroMensual.objects.filter(usuario=request.user)
            .order_by('-periodo')[:meses]
        )

        if not registros:
            return Response({'tiene_datos': False})

        registros = list(reversed(registros))

        categorias = ['Alimentos', 'Vestido', 'Vivienda/Serv.', 'Salud',
                      'Transporte', 'Comunicaciones', 'Educación', 'Otros']
        campos = ['gasto_alimentos', 'gasto_vestido', 'gasto_vivienda_servicios',
                  'gasto_salud', 'gasto_transporte', 'gasto_comunicaciones',
                  'gasto_educacion', 'gasto_otros_bienes']

        return Response({
            'tiene_datos': True,
            'labels': [f"{MESES_ES[r.periodo.month]} {r.periodo.year}" for r in registros],
            'ingresos':       [round(r.ing_total, 2)    for r in registros],
            'gastos_totales': [round(r.gasto_total, 2)  for r in registros],
            'ahorros':        [round(r.ahorro_bruto, 2) for r in registros],
            'gastos_promedio_categoria': {
                cat: round(
                    sum(float(getattr(r, campo)) for r in registros) / len(registros), 2
                )
                for cat, campo in zip(categorias, campos)
            },
            'gastos_ultimo_mes': {
                cat: round(float(getattr(registros[-1], campo)), 2)
                for cat, campo in zip(categorias, campos)
            },
        })
