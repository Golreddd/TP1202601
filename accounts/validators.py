# -*- coding: utf-8 -*-
"""Validadores del Usuario, declarados una sola vez y adjuntos a los campos del
MODELO (no solo en el formulario web): así los hereda automáticamente también la
API REST, ya que DRF copia los `validators` del campo del modelo al construir un
ModelSerializer — mismo patrón que ya usan financiero/models.py y
recomendaciones/models.py para no depender de que cada formulario repita la regla.
"""
import re

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator

# ── Nickname ────────────────────────────────────────────────────────────────────
# Antes solo se validaba el charset (letras, números, espacio, punto, guion, guion
# bajo), lo que dejaba pasar nicknames como "044444444404040404040409494049" (solo
# números) o "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" (un único carácter repetido) — ninguno
# identifica realmente a una persona. Se agregan dos reglas de contenido, además de
# acortar el máximo de 30 a 20 caracteres.
NICKNAME_FORMATO_RE = re.compile(r'^[\w.\- ]{3,20}$', re.UNICODE)
NICKNAME_REPETIDO_RE = re.compile(r'^(.)\1*$', re.UNICODE)


def validar_formato_nickname(nickname: str) -> None:
    nickname = nickname or ''
    if not NICKNAME_FORMATO_RE.fullmatch(nickname):
        raise ValidationError(
            'El nickname debe tener entre 3 y 20 caracteres: letras, números, '
            'espacios, punto, guion o guion bajo.'
        )
    if not any(c.isalpha() for c in nickname):
        raise ValidationError('El nickname debe incluir al menos una letra.')
    if NICKNAME_REPETIDO_RE.fullmatch(nickname):
        raise ValidationError('El nickname no puede ser el mismo carácter repetido.')


# ── Correo electrónico ──────────────────────────────────────────────────────────
# El EmailValidator de Django solo exige el formato local@dominio.tld, así que
# acepta direcciones sintácticamente válidas pero casi siempre un error de tipeo
# ("1@1.com", "asdas.a@a.com"): un dominio de una sola letra o puramente numérico.
# No se resuelve el DNS (sería lento y frágil para un formulario) — solo se filtran
# los casos evidentes.
def validar_dominio_email(email: str) -> None:
    dominio = (email or '').rsplit('@', 1)[-1]
    partes = dominio.split('.')
    if len(partes) < 2:
        raise ValidationError('Revisa tu correo: el dominio no parece válido.')
    segundo_nivel = partes[-2]
    if len(segundo_nivel) < 2 or segundo_nivel.isdigit():
        raise ValidationError('Revisa tu correo: el dominio no parece válido.')


# ── Edad ─────────────────────────────────────────────────────────────────────────
# El campo no tenía NINGÚN validador a nivel de modelo (solo un `min`/`max` en el
# atributo HTML del widget, que no protege nada si se edita el POST a mano o se
# llama directo a la API) — permitía registrar usuarios de 1 o 2 años.
validar_mayor_de_edad = MinValueValidator(
    18, message='Debes ser mayor de edad (18 años o más) para registrarte.'
)

# ── Teléfono ─────────────────────────────────────────────────────────────────────
# Convención de celular en Perú: exactamente 9 dígitos, sin letras ni símbolos.
validar_telefono_peru = RegexValidator(
    regex=r'^\d{9}$',
    message='El teléfono debe tener exactamente 9 dígitos numéricos (ej: 987654321).',
)
