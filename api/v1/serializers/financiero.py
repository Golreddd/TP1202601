from datetime import date

from rest_framework import serializers

from core.constants import MESES_ES
from financiero.models import RegistroMensual


class RegistroMensualSerializer(serializers.ModelSerializer):
    # Campos calculados (read-only)
    ing_total = serializers.FloatField(read_only=True)
    gasto_total = serializers.FloatField(read_only=True)
    ahorro_bruto = serializers.FloatField(read_only=True)
    tasa_ahorro = serializers.FloatField(read_only=True)
    gastos_por_categoria = serializers.DictField(read_only=True)
    periodo_display = serializers.SerializerMethodField()

    class Meta:
        model = RegistroMensual
        fields = [
            'id', 'periodo', 'periodo_display',
            # Ingresos
            'ing_planilla', 'ing_informal', 'ing_total',
            # Gastos (exactamente los 8 de GASTO_COLS en predict.py)
            'gasto_alimentos', 'gasto_vestido', 'gasto_vivienda_servicios',
            'gasto_salud', 'gasto_transporte', 'gasto_comunicaciones',
            'gasto_educacion', 'gasto_otros_bienes',
            # Totales calculados
            'gasto_total', 'ahorro_bruto', 'tasa_ahorro', 'gastos_por_categoria',
            # Timestamps
            'creado_en', 'actualizado_en',
        ]
        read_only_fields = ['id', 'creado_en', 'actualizado_en']

    def get_periodo_display(self, obj):
        return f"{MESES_ES[obj.periodo.month]} {obj.periodo.year}"

    def validate(self, attrs):
        ing_p = float(attrs.get('ing_planilla', 0))
        ing_i = float(attrs.get('ing_informal', 0))
        if ing_p + ing_i <= 0:
            raise serializers.ValidationError(
                'El ingreso total debe ser mayor a S/ 0.'
            )
        # Ningún gasto puede ser negativo
        gastos = [
            'gasto_alimentos', 'gasto_vestido', 'gasto_vivienda_servicios',
            'gasto_salud', 'gasto_transporte', 'gasto_comunicaciones',
            'gasto_educacion', 'gasto_otros_bienes',
        ]
        for campo in gastos:
            if float(attrs.get(campo, 0)) < 0:
                raise serializers.ValidationError(
                    {campo: 'El gasto no puede ser negativo.'}
                )
        return attrs

    def validate_periodo(self, value):
        # Siempre normalizar al primer día del mes
        return date(value.year, value.month, 1)


class DashboardSerializer(serializers.Serializer):
    """Serializer de salida para GET /api/v1/financiero/dashboard/"""
    tiene_datos = serializers.BooleanField()
    mensaje = serializers.CharField(required=False, allow_blank=True)
    resumen_actual = serializers.DictField(required=False)
    historial_6m = RegistroMensualSerializer(many=True, required=False)
    racha = serializers.DictField(required=False)
    perfil_completo = serializers.BooleanField(required=False)
