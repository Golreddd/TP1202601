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
            'ahorro_actual', 'meta_validada', 'gap', 'alcanza_meta',
            'cluster_id', 'cluster_label', 'confianza',
            'periodo_registro', 'creado_en',
        ]
        read_only_fields = [
            'id', 'ahorro_actual', 'meta_validada', 'gap', 'alcanza_meta',
            'cluster_id', 'cluster_label', 'confianza',
            'periodo_registro', 'creado_en',
        ]

    def get_periodo_registro(self, obj):
        if obj.registro:
            return obj.registro.periodo.strftime('%Y-%m')
        return None


class ResultadoMLDetalleSerializer(ResultadoMLSerializer):
    """
    Serializer extendido — incluye planes y SHAP recomputados.
    Usado en GET /api/v1/recomendaciones/historial/<id>/
    Los campos planes/shap_top5/validacion_meta se inyectan desde la view.
    """
    planes          = serializers.ListField(default=list, read_only=True)
    shap_top5       = serializers.ListField(default=list, read_only=True)
    validacion_meta = serializers.DictField(default=dict, read_only=True)

    class Meta(ResultadoMLSerializer.Meta):
        fields = ResultadoMLSerializer.Meta.fields + ['planes', 'shap_top5', 'validacion_meta']


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
        help_text='ID del RegistroMensual a analizar. Omitir para usar el más reciente.',
    )
    meta_ahorro = serializers.FloatField(
        default=0.0,
        min_value=0,
        help_text='Meta de ahorro mensual en S/.',
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
