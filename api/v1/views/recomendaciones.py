"""
API de recomendaciones ML, metas y pronósticos.

POST   /api/v1/recomendaciones/ejecutar/               → Análisis con datos REALES (guarda ResultadoML)
POST   /api/v1/recomendaciones/pronostico/             → Análisis HIPOTÉTICO (no guarda nada)
GET    /api/v1/recomendaciones/historial/               → Lista de análisis pasados
GET    /api/v1/recomendaciones/historial/<id>/          → Detalle + planes recomputados
DELETE /api/v1/recomendaciones/historial/<id>/          → Eliminar un resultado

CRUD   /api/v1/recomendaciones/metas-mensuales/        → Metas de ahorro mensual
CRUD   /api/v1/recomendaciones/metas/                  → Metas a largo plazo
"""
import logging
from datetime import date

from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from django.core.exceptions import ObjectDoesNotExist

from core.constants import MESES_ES
from financiero.models import RegistroMensual
from gamificacion.services import verificar_y_otorgar_logros
from recomendaciones.models import MetaLargoPlazo, MetaMensual, PlanSeleccionado, ResultadoML
from api.v1.serializers.recomendaciones import (
    EjecutarMLSerializer,
    MetaLargoPlazoSerializer,
    MetaMensualSerializer,
    PronosticoMLSerializer,
    ResultadoMLDetalleSerializer,
    ResultadoMLSerializer,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _llamar_recommend(user_dict: dict, meta_ahorro: float):
    """Importa y llama a recommend() manejando errores de forma consistente."""
    from src.predict import recommend
    return recommend(user_dict, meta_ahorro)


def _orquestar(ref_dict: dict, actual_dict: dict, meta_ahorro: float, historial=None):
    """Flujo de recomendaciones del spec (mes de referencia ≠ mes actual):

      • Clasificación + SHAP se calculan sobre el MES DE REFERENCIA elegido.
      • El plan counterfactual (opciones) se genera sobre el MES ACTUAL, priorizando
        las categorías que más han crecido en el `historial` (multi-mes).

    Devuelve el dict de recommend(actual) con `clase_actual` y `diagnostico_shap`
    sustituidos por los del mes de referencia. Si ref_dict es actual_dict, el
    resultado es equivalente a recommend() directo (caso de un solo mes).
    """
    from src.predict import classify, recommend, shap_explain
    plan = recommend(actual_dict, meta_ahorro, historial=historial)
    plan['clase_actual'] = classify(ref_dict)
    plan['diagnostico_shap'] = shap_explain(ref_dict, top=3)
    return plan


# ── Análisis ML — datos REALES ────────────────────────────────────────────────

class EjecutarMLView(APIView):
    """
    POST /api/v1/recomendaciones/ejecutar/

    Flujo (mes de referencia ≠ mes actual):
      - El usuario elige un mes del historial como REFERENCIA (registro_id):
        se clasifica con XGBoost y se calcula su SHAP.
      - El plan counterfactual (opciones) se genera sobre el MES ACTUAL
        (el RegistroMensual más reciente del usuario).
    El resultado se persiste en recomendaciones_resultadoml (solo escalares);
    las opciones y el SHAP se recomputan cuando el usuario consulta el historial.

    Selección de la referencia:
      - Sin registro_id → referencia = mes actual (más reciente)
      - Con registro_id → ese mes específico como referencia
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EjecutarMLSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user

        # 1. Verificar que el perfil esté completo
        if not user.perfil_completo:
            return Response(
                {
                    'error': 'Completa tu perfil antes de ejecutar el análisis.',
                    'campos_faltantes': {
                        'edad': user.edad is None,
                        'nivel_educ': user.nivel_educ is None,
                        'miembros_hogar': user.miembros_hogar is None,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Resolver MES DE REFERENCIA (el que se clasifica) y MES ACTUAL (en curso).
        #    El usuario elige el de referencia; el plan se genera sobre el más reciente.
        registro_id = serializer.validated_data.get('registro_id')
        mes_actual = RegistroMensual.objects.filter(
            usuario=user
        ).order_by('-periodo').first()
        if not mes_actual:
            return Response(
                {'error': 'No tienes registros financieros. Crea uno primero.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if registro_id:
            try:
                mes_referencia = RegistroMensual.objects.get(id=registro_id, usuario=user)
            except RegistroMensual.DoesNotExist:
                return Response(
                    {'error': f'Registro #{registro_id} no encontrado.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            mes_referencia = mes_actual  # sin elección → referencia = mes actual

        meta_ahorro = float(serializer.validated_data.get('meta_ahorro', 0.0))

        # 3. Pipeline ML: clasificación + SHAP del mes de referencia; plan del mes actual
        #    (priorizando el gasto que más creció en el historial multi-mes).
        from recomendaciones.trends import historial_user_dicts
        try:
            resultado_raw = _orquestar(
                mes_referencia.to_user_dict(), mes_actual.to_user_dict(), meta_ahorro,
                historial=historial_user_dicts(user),
            )
        except FileNotFoundError as exc:
            return Response(
                {'error': f'Modelo ML no encontrado: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as exc:
            logger.exception('Error inesperado en pipeline ML (ejecutar).')
            return Response(
                {'error': f'Error en el modelo ML: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 4. Guardar/actualizar MetaMensual del MES ACTUAL (el del plan) si se dio meta
        meta_obj = None
        if meta_ahorro > 0:
            meta_obj, _ = MetaMensual.objects.update_or_create(
                usuario=user,
                periodo=date(mes_actual.periodo.year, mes_actual.periodo.month, 1),
                defaults={'monto': meta_ahorro},
            )

        # 5. Persistir escalares: clasificación (mes referencia) + plan (mes actual)
        cls = resultado_raw['clase_actual']
        resultado = ResultadoML.objects.create(
            usuario=user,
            registro=mes_actual,             # mes del plan (ahorro real del mes en curso)
            mes_referencia=mes_referencia,   # mes clasificado
            meta=meta_obj,
            ahorro_actual=resultado_raw['ahorro_actual'],
            meta_validada=resultado_raw['meta'],
            necesita_recortar=resultado_raw['necesita_recortar'],
            clase_predicha=cls['clase'],
            label_predicha=cls['label'],
            prob_ahorra=cls['probabilidad_ahorra'],
            confianza=cls['confianza'],
            shap_top_features=resultado_raw.get('diagnostico_shap', []),
        )

        # 6. Verificar logros desbloqueables
        verificar_y_otorgar_logros(user, contexto='ml')

        # 7. Respuesta: escalares + opciones/SHAP del resultado fresco
        data = ResultadoMLSerializer(resultado).data
        data['opciones']         = resultado_raw.get('opciones', [])
        data['diagnostico_shap'] = resultado_raw.get('diagnostico_shap', [])
        data['mensaje']          = resultado_raw.get('mensaje', '')
        data['ya_cumple']        = resultado_raw.get('ya_cumple', False)

        return Response(data, status=status.HTTP_201_CREATED)


# ── Análisis ML — datos HIPOTÉTICOS (pronóstico) ──────────────────────────────

class PronosticoMLView(APIView):
    """
    POST /api/v1/recomendaciones/pronostico/

    Ejecuta el pipeline ML con datos HIPOTÉTICOS proporcionados por el usuario.
    NO crea ningún RegistroMensual ni ResultadoML en la BD.
    Útil para:
      - Simular el mes actual antes de cerrarlo
      - Hacer análisis what-if (¿qué pasa si reduzco gastos X?)
      - Probar escenarios alternativos de ingresos/gastos

    Los campos de perfil (edad, nivel_educ, miembros_hogar) son opcionales.
    Si no se envían, se usan los valores del usuario autenticado.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PronosticoMLSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        data = serializer.validated_data

        # Resolver campos de perfil: usa los del request o los del usuario
        edad           = data.get('edad') or user.edad
        nivel_educ     = data.get('nivel_educ') or user.nivel_educ
        miembros_hogar = data.get('miembros_hogar') or user.miembros_hogar

        # Validar que tenemos perfil suficiente para el ML
        if not all([edad, nivel_educ, miembros_hogar]):
            faltantes = {
                'edad': edad is None,
                'nivel_educ': nivel_educ is None,
                'miembros_hogar': miembros_hogar is None,
            }
            return Response(
                {
                    'error': (
                        'Faltan datos de perfil para el análisis. '
                        'Completa tu perfil o envíalos en el cuerpo de la solicitud.'
                    ),
                    'campos_faltantes': faltantes,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        meta_ahorro = float(data.get('meta_ahorro', 0.0))

        # Construir user_dict con los datos hipotéticos
        user_dict = {
            'EDAD':                     edad,
            'NIVEL_EDUC':               nivel_educ,
            'MIEMBROS_HOGAR':           miembros_hogar,
            'ING_PLANILLA':             float(data['ing_planilla']),
            'ING_INFORMAL':             float(data['ing_informal']),
            'GASTO_ALIMENTOS':          float(data['gasto_alimentos']),
            'GASTO_VESTIDO':            float(data['gasto_vestido']),
            'GASTO_VIVIENDA_SERVICIOS': float(data['gasto_vivienda_servicios']),
            'GASTO_SALUD':              float(data['gasto_salud']),
            'GASTO_TRANSPORTE':         float(data['gasto_transporte']),
            'GASTO_COMUNICACIONES':     float(data['gasto_comunicaciones']),
            'GASTO_EDUCACION':          float(data['gasto_educacion']),
            'GASTO_OTROS_BIENES':       float(data['gasto_otros_bienes']),
        }

        # Llamar al pipeline ML
        try:
            resultado_raw = _llamar_recommend(user_dict, meta_ahorro)
        except FileNotFoundError as exc:
            return Response(
                {'error': f'Modelo ML no encontrado: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as exc:
            logger.exception('Error inesperado en pipeline ML (pronóstico).')
            return Response(
                {'error': f'Error en el modelo ML: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Calcular totales para contexto
        ing_total   = float(data['ing_planilla']) + float(data['ing_informal'])
        gasto_total = sum(float(data[f]) for f in [
            'gasto_alimentos', 'gasto_vestido', 'gasto_vivienda_servicios',
            'gasto_salud', 'gasto_transporte', 'gasto_comunicaciones',
            'gasto_educacion', 'gasto_otros_bienes',
        ])

        cls = resultado_raw['clase_actual']
        return Response({
            'tipo':    'pronostico',
            'mensaje_tipo': 'Análisis hipotético completado. Este resultado NO fue guardado.',
            # Resultados del ML — clasificación binaria (sin K-Means, sin monto predicho)
            'ahorro_actual':     resultado_raw['ahorro_actual'],
            'meta_validada':     resultado_raw['meta'],
            'necesita_recortar': resultado_raw['necesita_recortar'],
            'ya_cumple':         resultado_raw['ya_cumple'],
            'clase_predicha':    cls['clase'],
            'label_predicha':    cls['label'],
            'prob_ahorra':       cls['probabilidad_ahorra'],
            'confianza':         cls['confianza'],
            'opciones':          resultado_raw.get('opciones', []),
            'diagnostico_shap':  resultado_raw.get('diagnostico_shap', []),
            'mensaje':           resultado_raw.get('mensaje', ''),
            # Datos de entrada para referencia del frontend
            'datos_entrada': {
                'ing_total':    round(ing_total, 2),
                'gasto_total':  round(gasto_total, 2),
                'ahorro_bruto': round(ing_total - gasto_total, 2),
                'tasa_ahorro':  round((ing_total - gasto_total) / ing_total * 100, 1) if ing_total > 0 else 0,
            },
        })


# ── Historial de resultados ML ────────────────────────────────────────────────

class ResultadoMLListView(ListAPIView):
    """
    GET /api/v1/recomendaciones/historial/
    Lista todos los análisis ML del usuario autenticado (paginado).
    Soporta ?mes=2025-05 para filtrar por período del registro.
    """
    serializer_class   = ResultadoMLSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ResultadoML.objects.filter(
            usuario=self.request.user
        ).select_related('registro', 'meta').order_by('-creado_en')

        # Filtro opcional por período del registro asociado
        mes = self.request.query_params.get('mes', '').strip()
        if mes:
            try:
                year, month = mes.split('-')
                qs = qs.filter(
                    registro__periodo__year=int(year),
                    registro__periodo__month=int(month),
                )
            except (ValueError, AttributeError):
                pass  # ignorar filtro malformado

        return qs


class ResultadoMLDetailView(APIView):
    """
    GET    /api/v1/recomendaciones/historial/<id>/  → Detalle con planes recomputados
    DELETE /api/v1/recomendaciones/historial/<id>/  → Eliminar resultado
    """
    permission_classes = [IsAuthenticated]

    def _get_resultado(self, pk, user):
        try:
            return ResultadoML.objects.select_related(
                'registro', 'meta'
            ).get(pk=pk, usuario=user)
        except ResultadoML.DoesNotExist:
            return None

    def get(self, request, pk):
        resultado = self._get_resultado(pk, request.user)
        if not resultado:
            return Response(
                {'error': 'Resultado no encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = ResultadoMLSerializer(resultado).data

        # Recomputar opciones de recorte y SHAP desde el registro original
        try:
            resultado_recomputado = resultado.recomputar()
            data['opciones']         = resultado_recomputado.get('opciones', [])
            data['diagnostico_shap'] = resultado_recomputado.get('diagnostico_shap', [])
            data['mensaje']          = resultado_recomputado.get('mensaje', '')
        except Exception as exc:
            logger.warning('No se pudo recomputar resultado ML #%s: %s', pk, exc)
            data['opciones']         = []
            data['diagnostico_shap'] = []
            data['mensaje']          = ''

        return Response(data)

    def delete(self, request, pk):
        resultado = self._get_resultado(pk, request.user)
        if not resultado:
            return Response(
                {'error': 'Resultado no encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        resultado.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Elegir plan de optimización ───────────────────────────────────────────────

class ElegirPlanView(APIView):
    """
    POST /api/v1/recomendaciones/elegir-plan/

    Guarda el plan de optimización elegido por el usuario.
    Desactiva cualquier plan previo activo (solo un plan activo a la vez).

    Body: { "resultado_id": int, "nombre_plan": "Suave|Equilibrado|Decidido" }
    """
    permission_classes = [IsAuthenticated]

    _PLANES_VALIDOS = ['Suave', 'Equilibrado', 'Decidido']

    def post(self, request):
        resultado_id = request.data.get('resultado_id')
        nombre_plan  = str(request.data.get('nombre_plan', '')).strip()

        if not resultado_id or not nombre_plan:
            return Response(
                {'error': 'Faltan datos: resultado_id y nombre_plan son requeridos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if nombre_plan not in self._PLANES_VALIDOS:
            return Response(
                {'error': f'Plan inválido. Opciones: {self._PLANES_VALIDOS}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resultado = ResultadoML.objects.select_related('registro').get(
                pk=resultado_id, usuario=request.user
            )
        except ResultadoML.DoesNotExist:
            return Response({'error': 'Análisis no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            detalle = resultado.recomputar()
        except Exception as exc:
            logger.exception('Error recomputando para elegir plan.')
            return Response(
                {'error': f'Error al obtener plan: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        plan_data = next(
            (p for p in detalle.get('opciones', []) if p.get('nombre', '').strip() == nombre_plan),
            None,
        )
        if not plan_data:
            return Response(
                {'error': f'Plan {nombre_plan} no encontrado en el análisis.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Solo los valores optimizados por categoría (dict plano {GASTO_X: valor})
        gastos_sugeridos = {
            col: round(float(valor), 2)
            for col, valor in plan_data.get('gastos_optimizados', {}).items()
        }

        # Desactivar plan previo y crear el nuevo
        PlanSeleccionado.objects.filter(usuario=request.user, activo=True).update(activo=False)

        plan = PlanSeleccionado.objects.create(
            usuario=request.user,
            resultado=resultado,
            nombre_plan=nombre_plan,
            ahorro_proyectado=round(float(plan_data.get('ahorro_resultante', 0)), 2),
            meta_ahorro=round(float(resultado.meta_validada), 2),
            gastos_sugeridos=gastos_sugeridos,
            activo=True,
        )

        return Response(
            {
                'id': plan.id,
                'nombre_plan': plan.nombre_plan,
                'mensaje': f'Plan {nombre_plan} guardado. Haz seguimiento en Progreso.',
            },
            status=status.HTTP_201_CREATED,
        )


# ── Meta Mensual — CRUD completo ──────────────────────────────────────────────

class MetaMensualViewSet(ModelViewSet):
    """
    CRUD completo de MetaMensual (meta de ahorro mensual).

    GET    /api/v1/recomendaciones/metas-mensuales/         → lista
    POST   /api/v1/recomendaciones/metas-mensuales/         → crear
    GET    /api/v1/recomendaciones/metas-mensuales/<id>/    → detalle
    PUT    /api/v1/recomendaciones/metas-mensuales/<id>/    → actualizar
    PATCH  /api/v1/recomendaciones/metas-mensuales/<id>/    → actualización parcial
    DELETE /api/v1/recomendaciones/metas-mensuales/<id>/    → eliminar

    Cada usuario solo ve y modifica sus propias metas mensuales.
    """
    serializer_class   = MetaMensualSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return MetaMensual.objects.filter(
            usuario=self.request.user
        ).order_by('-periodo')

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)


# ── Meta Largo Plazo — CRUD completo ─────────────────────────────────────────

class MetaLargoPlazoViewSet(ModelViewSet):
    """
    CRUD completo de MetaLargoPlazo (objetivos a largo plazo).

    GET    /api/v1/recomendaciones/metas/         → lista (solo activas)
    POST   /api/v1/recomendaciones/metas/         → crear
    GET    /api/v1/recomendaciones/metas/<id>/    → detalle
    PUT    /api/v1/recomendaciones/metas/<id>/    → actualizar
    PATCH  /api/v1/recomendaciones/metas/<id>/    → actualización parcial
    DELETE /api/v1/recomendaciones/metas/<id>/    → soft delete (activa=False)

    Cada usuario solo ve y modifica sus propias metas.
    """
    serializer_class   = MetaLargoPlazoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return MetaLargoPlazo.objects.filter(
            usuario=self.request.user, activa=True
        ).order_by('-creado_en')

    def perform_create(self, serializer):
        meta = serializer.save(usuario=self.request.user)
        # Verificar logro de primera meta creada
        total_metas = self.request.user.metas_largo_plazo.filter(activa=True).count()
        if total_metas == 1:
            from gamificacion.services import _otorgar
            _otorgar(self.request.user, 'PRIMERA_META')

    def perform_destroy(self, instance):
        # Soft delete: marca inactiva en lugar de borrar físicamente
        instance.activa = False
        instance.save(update_fields=['activa'])

    def perform_update(self, serializer):
        meta = serializer.save()
        # Verificar logros si la meta se completó
        if meta.completada:
            verificar_y_otorgar_logros(self.request.user, contexto='meta_completada')
