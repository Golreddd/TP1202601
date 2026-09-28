# -*- coding: utf-8 -*-
"""
Servicios del asistente de voz: conectan la interpretación pura de
financiero/voz.py con la base de datos (registro del mes, plan activo,
racha, logros y respuestas a preguntas).

Nunca se guarda el audio ni el texto dictado — solo el resultado (montos en
RegistroMensual) y un contador `Usuario.registros_voz`. El "deshacer" no
depende de una tabla propia: usa un token firmado (django.core.signing) con
los deltas aplicados, válido 10 minutos.
"""
from datetime import date
from decimal import Decimal

from django.core import signing
from django.db import transaction

from financiero.models import RegistroMensual
from financiero.voz_vocabulario import CAMPOS_INGRESO, CATEGORIAS_GASTO

_SALT = 'voz-deshacer'
_MAX_AGE_DESHACER = 600  # 10 minutos
_TODOS_LOS_CAMPOS = list(CAMPOS_INGRESO) + list(CATEGORIAS_GASTO)


def mes_actual() -> date:
    hoy = date.today()
    return date(hoy.year, hoy.month, 1)


def _mes_anterior(periodo: date) -> date:
    if periodo.month == 1:
        return date(periodo.year - 1, 12, 1)
    return date(periodo.year, periodo.month - 1, 1)


def _etiqueta_categoria(campo: str) -> str:
    if campo in CATEGORIAS_GASTO:
        return CATEGORIAS_GASTO[campo]['label']
    return CAMPOS_INGRESO.get(campo, {}).get('label', campo)


# ────────────────────────────────────────────────────────────────────────────
# Previsualización (antes de guardar)
# ────────────────────────────────────────────────────────────────────────────

def _registro_con_deltas(registro, usuario, periodo, items):
    """Instancia SIN guardar de RegistroMensual con los `items` ya sumados —
    para previsualizar el impacto en el plan sin tocar la base de datos."""
    valores = {
        campo: (getattr(registro, campo) if registro else Decimal('0'))
        for campo in _TODOS_LOS_CAMPOS
    }
    for it in items:
        valores[it['campo']] = valores[it['campo']] + Decimal(str(it['monto']))
    return RegistroMensual(usuario=usuario, periodo=periodo, **valores)


def previsualizar(usuario, items: list[dict]) -> dict:
    """Arma el "antes/después" de cada ítem y el impacto en el plan activo,
    sin guardar nada. `items` = lista de {tipo, campo, etiqueta, monto} ya
    validados (financiero.voz.interpretar)."""
    from recomendaciones.analitica import presupuesto_por_categoria
    from recomendaciones.models import PlanSeleccionado

    periodo = mes_actual()
    registro = RegistroMensual.objects.filter(usuario=usuario, periodo=periodo).first()
    plan_activo = PlanSeleccionado.objects.filter(usuario=usuario, activo=True).first()

    filas = []
    saldo_extra = Decimal('0')
    for it in items:
        campo = it['campo']
        antes = float(getattr(registro, campo)) if registro else 0.0
        monto = float(it['monto'])
        filas.append({
            'tipo': it['tipo'], 'campo': campo, 'etiqueta': it['etiqueta'],
            'monto': round(monto, 2), 'antes': round(antes, 2),
            'despues': round(antes + monto, 2),
        })
        saldo_extra += Decimal(str(monto)) if it['tipo'] == 'ingreso' else -Decimal(str(monto))

    impacto_plan = []
    excede_plan = False
    compensar_con = []
    if plan_activo:
        registro_simulado = _registro_con_deltas(registro, usuario, periodo, items)
        impacto_plan = presupuesto_por_categoria(plan_activo, registro_simulado)
        claves_tocadas = {
            CATEGORIAS_GASTO[it['campo']]['clave_ml']
            for it in items if it['tipo'] == 'gasto'
        }
        for fila in impacto_plan:
            fila['tocada'] = fila['clave_ml'] in claves_tocadas
        excede_plan = any(f['excedido'] and f['tocada'] for f in impacto_plan)
        if excede_plan:
            compensar_con = [f for f in impacto_plan if not f['excedido'] and f['disponible'] > 0]

    saldo_antes = float(registro.ahorro_bruto) if registro else 0.0
    return {
        'items': filas,
        'tiene_registro_previo': registro is not None,
        'tiene_plan': plan_activo is not None,
        'impacto_plan': impacto_plan,
        'excede_plan': excede_plan,
        'compensar_con': compensar_con,
        'saldo_mes_antes': round(saldo_antes, 2),
        'saldo_mes_despues': round(saldo_antes + float(saldo_extra), 2),
    }


# ────────────────────────────────────────────────────────────────────────────
# Aplicar (guardar)
# ────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def aplicar(usuario, items: list[dict]) -> dict:
    """Suma `items` al RegistroMensual del mes actual (lo crea si no existe),
    actualiza racha/logros y devuelve un token para poder deshacerlo."""
    from gamificacion.models import Racha
    from gamificacion.services import verificar_y_otorgar_logros
    from recomendaciones.models import PlanSeleccionado

    periodo = mes_actual()
    registro, creado = RegistroMensual.objects.get_or_create(usuario=usuario, periodo=periodo)

    deltas: dict[str, Decimal] = {}
    for it in items:
        campo = it['campo']
        delta = Decimal(str(it['monto']))
        setattr(registro, campo, getattr(registro, campo) + delta)
        deltas[campo] = deltas.get(campo, Decimal('0')) + delta
    registro.save()

    racha, _ = Racha.objects.get_or_create(usuario=usuario)
    racha.actualizar(date.today())

    usuario.registros_voz = (usuario.registros_voz or 0) + 1
    usuario.save(update_fields=['registros_voz'])

    logros_nuevos = verificar_y_otorgar_logros(usuario, contexto='registro')
    logros_nuevos += verificar_y_otorgar_logros(usuario, contexto='voz')

    token = signing.dumps({
        'usuario_id': usuario.id,
        'registro_id': registro.id,
        'creado_registro': creado,
        'deltas': {k: str(v) for k, v in deltas.items()},
    }, salt=_SALT)

    return {
        'registro_id': registro.id,
        'periodo': periodo.strftime('%Y-%m'),
        'items': [
            {'etiqueta': it['etiqueta'], 'monto': round(float(it['monto']), 2)}
            for it in items
        ],
        'logros_nuevos': logros_nuevos,
        'token_deshacer': token,
        'tiene_plan': PlanSeleccionado.objects.filter(usuario=usuario, activo=True).exists(),
    }


# ────────────────────────────────────────────────────────────────────────────
# Deshacer
# ────────────────────────────────────────────────────────────────────────────

def deshacer(usuario, token: str) -> dict:
    try:
        payload = signing.loads(token, salt=_SALT, max_age=_MAX_AGE_DESHACER)
    except signing.SignatureExpired:
        return {'ok': False, 'error': 'Ya pasó el tiempo para deshacer este registro (10 minutos).'}
    except signing.BadSignature:
        return {'ok': False, 'error': 'El enlace para deshacer no es válido.'}

    if payload.get('usuario_id') != usuario.id:
        return {'ok': False, 'error': 'No puedes deshacer un registro de otro usuario.'}

    try:
        registro = RegistroMensual.objects.get(pk=payload['registro_id'], usuario=usuario)
    except RegistroMensual.DoesNotExist:
        return {'ok': False, 'error': 'El registro ya no existe.'}

    deltas = {k: Decimal(v) for k, v in payload['deltas'].items()}
    for campo, delta in deltas.items():
        actual = getattr(registro, campo)
        if actual < delta:
            return {
                'ok': False,
                'error': 'El registro cambió después de guardarlo (lo editaste manualmente); '
                         'no se puede deshacer automáticamente. Edítalo tú mismo si hace falta.',
            }

    with transaction.atomic():
        for campo, delta in deltas.items():
            setattr(registro, campo, getattr(registro, campo) - delta)

        si_quedo_vacio = payload.get('creado_registro') and all(
            getattr(registro, c) == 0 for c in _TODOS_LOS_CAMPOS
        )
        if si_quedo_vacio:
            registro.delete()
        else:
            registro.save()

        usuario.registros_voz = max(0, (usuario.registros_voz or 0) - 1)
        usuario.save(update_fields=['registros_voz'])

    return {'ok': True}


# ────────────────────────────────────────────────────────────────────────────
# Responder preguntas
# ────────────────────────────────────────────────────────────────────────────

def responder(usuario, consulta: dict) -> dict:
    """`consulta` = {tipo, campo, periodo} (financiero.voz._extraer_consulta).
    Devuelve {texto, detalle}."""
    periodo_pasado = consulta.get('periodo') == 'pasado'
    periodo = _mes_anterior(mes_actual()) if periodo_pasado else mes_actual()
    etiqueta_periodo = 'el mes pasado' if periodo_pasado else 'este mes'
    tipo = consulta.get('tipo')

    registro = RegistroMensual.objects.filter(usuario=usuario, periodo=periodo).first()

    if tipo == 'comparacion':
        actual = RegistroMensual.objects.filter(usuario=usuario, periodo=mes_actual()).first()
        pasado = RegistroMensual.objects.filter(usuario=usuario, periodo=_mes_anterior(mes_actual())).first()
        if not actual or not pasado:
            return {'texto': 'Necesito tu registro de este mes y del mes pasado para comparar.', 'detalle': None}
        diff = actual.gasto_total - pasado.gasto_total
        if diff > 0.5:
            return {'texto': f'Gastaste S/ {diff:.2f} más que el mes pasado.', 'detalle': None}
        if diff < -0.5:
            return {'texto': f'Gastaste S/ {abs(diff):.2f} menos que el mes pasado. ¡Bien ahí!', 'detalle': None}
        return {'texto': 'Gastaste prácticamente lo mismo que el mes pasado.', 'detalle': None}

    if not registro:
        return {'texto': f'No tienes ningún registro de {etiqueta_periodo}.', 'detalle': None}

    if tipo == 'gasto_total':
        return {
            'texto': f'Gastaste S/ {registro.gasto_total:.2f} {etiqueta_periodo}.',
            'detalle': registro.gastos_por_categoria(),
        }

    if tipo == 'ingreso_total':
        return {'texto': f'Ingresaste S/ {registro.ing_total:.2f} {etiqueta_periodo}.', 'detalle': None}

    if tipo == 'ahorro':
        ahorro = registro.ahorro_bruto
        if ahorro >= 0:
            return {'texto': f'Llevas S/ {ahorro:.2f} ahorrados {etiqueta_periodo}.', 'detalle': None}
        return {
            'texto': f'{etiqueta_periodo.capitalize()} estás en déficit: gastaste '
                     f'S/ {abs(ahorro):.2f} más de lo que ingresó.',
            'detalle': None,
        }

    if tipo == 'gasto_categoria':
        if not consulta.get('campo'):
            return {'texto': 'No entendí de qué categoría. Prueba: "¿cuánto gasté en transporte?"', 'detalle': None}
        etiqueta = _etiqueta_categoria(consulta['campo'])
        monto = float(getattr(registro, consulta['campo']))
        return {'texto': f'Gastaste S/ {monto:.2f} en {etiqueta} {etiqueta_periodo}.', 'detalle': None}

    if tipo == 'top_categoria':
        gastos = registro.gastos_por_categoria()
        if not any(gastos.values()):
            return {'texto': f'Todavía no registras gastos {etiqueta_periodo}.', 'detalle': None}
        categoria, monto = max(gastos.items(), key=lambda kv: kv[1])
        return {
            'texto': f'Tu categoría con más gasto es {categoria}, con S/ {monto:.2f} {etiqueta_periodo}.',
            'detalle': gastos,
        }

    if tipo == 'saldo_categoria':
        from recomendaciones.analitica import presupuesto_por_categoria
        from recomendaciones.models import PlanSeleccionado

        plan = PlanSeleccionado.objects.filter(usuario=usuario, activo=True).first()
        if not plan:
            return {'texto': 'Todavía no tienes un plan de ahorro activo para calcular tu presupuesto.', 'detalle': None}
        filas = presupuesto_por_categoria(plan, registro)
        if not consulta.get('campo'):
            return {'texto': 'Dime de qué categoría quieres saber tu presupuesto disponible.', 'detalle': filas}
        etiqueta = _etiqueta_categoria(consulta['campo'])
        fila = next((f for f in filas if f['categoria'] == etiqueta), None)
        if not fila:
            return {'texto': f'Tu plan no tiene un presupuesto sugerido para {etiqueta}.', 'detalle': None}
        if fila['excedido']:
            return {
                'texto': f'Ya te pasaste S/ {fila["excedente"]:.2f} en {etiqueta} '
                         f'(presupuesto: S/ {fila["sugerido"]:.2f}).',
                'detalle': fila,
            }
        return {
            'texto': f'Te quedan S/ {fila["disponible"]:.2f} en {etiqueta} de tu '
                     f'presupuesto de S/ {fila["sugerido"]:.2f}.',
            'detalle': fila,
        }

    if tipo == 'cumple_plan':
        from recomendaciones.analitica import comparacion_plan
        from recomendaciones.models import PlanSeleccionado

        plan = PlanSeleccionado.objects.filter(usuario=usuario, activo=True).first()
        if not plan:
            return {'texto': 'No tienes un plan de ahorro activo todavía.', 'detalle': None}
        comparacion = comparacion_plan(usuario, plan)
        entrada = next((c for c in comparacion if c['registro'] == registro), None)
        if not entrada:
            return {'texto': 'Todavía no hay suficientes datos para saber si estás cumpliendo tu plan.', 'detalle': None}
        if entrada['cumple']:
            return {
                'texto': f'Vas cumpliendo tu plan: tu ahorro de {etiqueta_periodo} es S/ {entrada["ahorro_real"]:.2f}.',
                'detalle': entrada,
            }
        return {
            'texto': f'Todavía no cumples tu plan {etiqueta_periodo}: te falta S/ {abs(entrada["diff"]):.2f}.',
            'detalle': entrada,
        }

    return {'texto': 'No supe responder esa pregunta todavía. Prueba con otra forma de decirlo.', 'detalle': None}
