from rest_framework import serializers

from recomendaciones.models import MetaLargoPlazo, MetaMensual, ResultadoML


# ── Meta Mensual ──────────────────────────────────────────────────────────────

class MetaMensualSerializer(serializers.ModelSerializer):
    """CRUD completo de MetaMensual — GET/POST/PUT/DELETE /api/v1/recomendaciones/metas-mensuales/"""

    class Meta:
        model  = MetaMensual
        fields = ['id', 'periodo', 'monto']
        read_only_fields = ['id']

    def validate_monto(self, value):
        if value < 0:
            raise serializers.ValidationError('La meta no puede ser negativa.')
        return value

    def validate_periodo(self, value):
        from datetime import date
        return date(value.year, value.month, 1)


# ── Meta Largo Plazo ──────────────────────────────────────────────────────────

class MetaLargoPlazoSerializer(serializers.ModelSerializer):
    """CRUD completo de MetaLargoPlazo — GET/POST/PUT/DELETE /api/v1/recomendaciones/metas/"""
    porcentaje = serializers.FloatField(read_only=True)
    faltante   = serializers.FloatField(read_only=True)
    completada = serializers.BooleanField(read_only=True)

    class Meta:
        model  = MetaLargoPlazo
        fields = [
            'id', 'nombre', 'icono',
            'monto_objetivo', 'monto_actual', 'porcentaje', 'faltante', 'completada',
            'fecha_limite', 'activa', 'creado_en',
        ]
        read_only_fields = ['id', 'creado_en']

    def validate_monto_objetivo(self, value):
        if value <= 0:
            raise serializers.ValidationError('El monto objetivo debe ser mayor a S/ 0.')
        return value

    def validate_monto_actual(self, value):
        if value < 0:
            raise serializers.ValidationError('El monto ahorrado no puede ser negativo.')
        return value


# ── Resultado ML ──────────────────────────────────────────────────────────────

class ResultadoMLSerializer(serializers.ModelSerializer):
    """
    Serializer base de ResultadoML — solo escalares almacenados en BD.
    Usado en la lista del historial (GET /api/v1/recomendaciones/historial/).
    """
    alcanza_meta     = serializers.BooleanField(read_only=True)
    periodo_registro = serializers.SerializerMethodField()

    class Meta:
        model  = ResultadoML
        fields = [
            'id',
            'ahorro_actual', 'meta_validada', 'necesita_recortar', 'alcanza_meta',
            'clase_predicha', 'label_predicha', 'prob_ahorra', 'confianza',
            'shap_top_features', 'escenario', 'categoria_objetivo',
            'periodo_registro', 'creado_en',
        ]
        read_only_fields = [
            'id', 'ahorro_actual', 'meta_validada', 'necesita_recortar', 'alcanza_meta',
            'clase_predicha', 'label_predicha', 'prob_ahorra', 'confianza',
            'shap_top_features', 'escenario', 'categoria_objetivo',
            'periodo_registro', 'creado_en',
        ]

    def get_periodo_registro(self, obj):
        if obj.registro:
            return obj.registro.periodo.strftime('%Y-%m')
        return None


class ResultadoMLDetalleSerializer(ResultadoMLSerializer):
    """
    Serializer extendido — incluye opciones (recortes) y SHAP recomputados.
    Usado en GET /api/v1/recomendaciones/historial/<id>/
    Los campos opciones/diagnostico_shap/mensaje se inyectan desde la view.
    """
    opciones         = serializers.ListField(default=list, read_only=True)
    diagnostico_shap = serializers.ListField(default=list, read_only=True)
    mensaje          = serializers.CharField(default='', read_only=True)

    class Meta(ResultadoMLSerializer.Meta):
        fields = ResultadoMLSerializer.Meta.fields + ['opciones', 'diagnostico_shap', 'mensaje']


# ── Input para /ejecutar/ ─────────────────────────────────────────────────────

class EjecutarMLSerializer(serializers.Serializer):
    """
    Input para POST /api/v1/recomendaciones/ejecutar/
    Analiza datos de un RegistroMensual EXISTENTE (datos reales del usuario).
    El resultado se guarda en la BD como ResultadoML.

    Modos:
      - Sin registro_id → usa el registro más reciente del usuario
      - Con registro_id → usa ese registro específico
    """
    registro_id = serializers.IntegerField(
        required=False,
        help_text='ID del RegistroMensual usado como MES DE REFERENCIA (se clasifica). '
                  'El plan se genera sobre el mes actual (más reciente). '
                  'Omitir para usar el mes actual también como referencia.',
    )
    meta_ahorro = serializers.FloatField(
        default=0.0,
        min_value=0,
        help_text='Meta de ahorro mensual en S/. (Opción B: meta libre). '
                  'Se ignora si se envía `alternativa` (Opción A).',
    )
    alternativa = serializers.ChoiceField(
        choices=['escalamiento', 'ideal_20', 'meta_largo_plazo', 'suave_10'],
        required=False, allow_null=True, allow_blank=True,
        help_text='Opción A (spec §4): alternativa elegida del menú de metas. El monto '
                  'se resuelve SIEMPRE en el servidor (nunca se confía en un monto del '
                  'cliente para estas alternativas). Solo aplica si el ahorro real del '
                  'mes analizado ya es ≥0; si no, se ignora.',
    )


# ── Input para /pronostico/ ───────────────────────────────────────────────────

class PronosticoMLSerializer(serializers.Serializer):
    """
    Input para POST /api/v1/recomendaciones/pronostico/
    El usuario provee datos financieros HIPOTÉTICOS para simular el análisis.
    NO crea ningún RegistroMensual ni ResultadoML en la BD.

    Permite al usuario:
      - Simular escenarios: ¿qué pasa si reduzco mis gastos?
      - Proyectar el mes actual antes de cerrarlo
      - Comparar escenarios alternativos

    Los campos de perfil (edad, nivel_educ, miembros_hogar) son opcionales:
    si no se envían, se usan los valores del usuario autenticado.
    Pueden enviarse para simular perfiles distintos (what-if de perfil).
    """
    # Perfil (opcional — usa los valores del usuario si no se envían)
    edad           = serializers.IntegerField(required=False, min_value=15, max_value=80,
                                              help_text='Edad. Si se omite, usa la del perfil del usuario.')
    nivel_educ     = serializers.IntegerField(required=False, min_value=1, max_value=6,
                                              help_text='Nivel educativo 1-6. Si se omite, usa el del perfil.')
    miembros_hogar = serializers.IntegerField(required=False, min_value=1, max_value=20,
                                              help_text='Miembros del hogar. Si se omite, usa el del perfil.')

    # Ingresos
    ing_planilla = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, default=0,
        help_text='Ingreso formal (planilla) en S/.',
    )
    ing_informal = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, default=0,
        help_text='Ingreso informal en S/.',
    )

    # Gastos (8 categorías exactas de GASTO_COLS en predict.py)
    gasto_alimentos          = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=0)
    gasto_vestido            = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=0)
    gasto_vivienda_servicios = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=0)
    gasto_salud              = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=0)
    gasto_transporte         = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=0)
    gasto_comunicaciones     = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=0)
    gasto_educacion          = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=0)
    gasto_otros_bienes       = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=0)

    # Meta
    meta_ahorro = serializers.FloatField(
        default=0.0, min_value=0,
        help_text='Meta de ahorro mensual en S/.',
    )

    def validate(self, attrs):
        ing_total = float(attrs.get('ing_planilla', 0)) + float(attrs.get('ing_informal', 0))
        if ing_total <= 0:
            raise serializers.ValidationError(
                {'ing_planilla': 'El ingreso total (planilla + informal) debe ser mayor a S/ 0.'}
            )
        return attrs
