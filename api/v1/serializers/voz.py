"""
Serializers del asistente de voz: solo validan la forma del payload de entrada
(la interpretación real vive en financiero.voz / financiero.voz_servicios).
"""
from decimal import Decimal

from rest_framework import serializers

from financiero.voz_vocabulario import CAMPOS_INGRESO, CATEGORIAS_GASTO

_CAMPOS_VALIDOS = list(CATEGORIAS_GASTO) + list(CAMPOS_INGRESO)


class InterpretarVozSerializer(serializers.Serializer):
    texto = serializers.CharField(allow_blank=False, max_length=500)
    contexto_previo = serializers.CharField(required=False, allow_blank=True, default='', max_length=1000)


class ItemVozSerializer(serializers.Serializer):
    """Un ítem tal como lo devolvió /voz/interpretar/ — se revalida aquí antes
    de aplicarlo, nunca se confía ciegamente en lo que mande el cliente."""
    tipo = serializers.ChoiceField(choices=['gasto', 'ingreso'])
    campo = serializers.ChoiceField(choices=_CAMPOS_VALIDOS)
    etiqueta = serializers.CharField(max_length=60)
    monto = serializers.DecimalField(
        max_digits=10, decimal_places=2,
        min_value=Decimal('0.01'), max_value=Decimal('1000000'),
    )

    def validate(self, data):
        if data['tipo'] == 'gasto' and data['campo'] not in CATEGORIAS_GASTO:
            raise serializers.ValidationError('Categoría de gasto inválida.')
        if data['tipo'] == 'ingreso' and data['campo'] not in CAMPOS_INGRESO:
            raise serializers.ValidationError('Tipo de ingreso inválido.')
        return data


class ConfirmarVozSerializer(serializers.Serializer):
    items = ItemVozSerializer(many=True, allow_empty=False)


class DeshacerVozSerializer(serializers.Serializer):
    token = serializers.CharField(allow_blank=False, max_length=2000)
