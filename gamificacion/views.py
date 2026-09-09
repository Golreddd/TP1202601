import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.constants import MESES_ES_ABREV
from gamificacion.models import Logro, LogroUsuario


def _listar_nombres(nombres):
    """'A' | 'A y B' | 'A, B y C' — para armar los mensajes de alerta_presupuesto."""
    nombres = list(nombres)
    if not nombres:
        return ''
    if len(nombres) == 1:
        return nombres[0]
    return ', '.join(nombres[:-1]) + ' y ' + nombres[-1]


@login_required
def logros(request):
    """GET /gamificacion/logros/"""
    todos_logros = Logro.objects.all().order_by('orden')
    obtenidos_ids = set(
        LogroUsuario.objects.filter(usuario=request.user)
        .values_list('logro_id', flat=True)
    )
    logros_ctx = [
        {'logro': logro, 'desbloqueado': logro.id in obtenidos_ids}
        for logro in todos_logros
    ]
    total_desbloqueados = len(obtenidos_ids)
    # Puntos reales = suma del campo `puntos` de los logros obtenidos
    # (NO count*10: cada logro vale distinto, de 10 a 200).
    puntos_total = sum(l.puntos for l in todos_logros if l.id in obtenidos_ids)
    return render(request, 'gamificacion/logros.html', {
        'logros':              logros_ctx,
        'total_desbloqueados': total_desbloqueados,
        'total_pendientes':    todos_logros.count() - total_desbloqueados,
        'puntos_total':        puntos_total,
    })


@login_required
def progreso(request):
    """GET /gamificacion/progreso/"""
    from financiero.models import RegistroMensual
    from gamificacion.models import Logro, LogroUsuario
    from recomendaciones.models import PlanSeleccionado
    from recomendaciones.trends import comparacion_plan as calcular_comparacion_plan, mes_inicio_plan

    registros = list(
        RegistroMensual.objects.filter(usuario=request.user).order_by('-periodo')[:12]
    )
    registros_chart = list(reversed(registros))

    meses_labels = json.dumps([MESES_ES_ABREV.get(r.periodo.month, '') for r in registros_chart])
    ahorro_data  = json.dumps([float(r.ahorro_bruto) for r in registros_chart])
    tasa_data    = json.dumps([float(r.tasa_ahorro)  for r in registros_chart])

    mejor_tasa = max((r.tasa_ahorro for r in registros), default=0)

    total_logros          = LogroUsuario.objects.filter(usuario=request.user).count()
    total_logros_posibles = Logro.objects.count()

    # ── Plan activo y comparación mes a mes ───────────────────────────────────
    plan_activo = PlanSeleccionado.objects.filter(
        usuario=request.user, activo=True
    ).select_related('resultado__registro').first()

    # Regla de "cumple/no cumple" un plan: única fuente en recomendaciones.trends,
    # reutilizada también por gamificacion.services para los logros de constancia.
    comparacion_plan = calcular_comparacion_plan(request.user, plan_activo)

    # ── Presupuesto por categoría (spec §8.1, Tarea 3) ────────────────────────
    # Monto máximo sugerido por categoría (del plan elegido) vs. lo YA gastado en el mes
    # más reciente desde que se adoptó el plan. Ya no es "solo referencia visual": más
    # abajo se deriva `alerta_presupuesto` a partir de estos mismos datos — sin
    # persistencia, se recalcula en cada render, no hay botón de "aplicar".
    presupuesto_categorias = []
    registro_actual_plan = None
    if plan_activo:
        # comparacion_plan ya está en orden ascendente por periodo (regs_post): el
        # último elemento es el registro más reciente desde que se adoptó el plan.
        registro_actual_plan = comparacion_plan[-1]['registro'] if comparacion_plan else (
            RegistroMensual.objects.filter(usuario=request.user, periodo__gte=mes_inicio_plan(plan_activo))
            .order_by('-periodo').first()
        )
    if plan_activo and registro_actual_plan:
        MAPA_LABEL = {
            'GASTO_ALIMENTOS': 'Alimentos', 'GASTO_VESTIDO': 'Vestido',
            'GASTO_VIVIENDA_SERVICIOS': 'Vivienda/Serv.', 'GASTO_SALUD': 'Salud',
            'GASTO_TRANSPORTE': 'Transporte', 'GASTO_COMUNICACIONES': 'Comunicaciones',
            'GASTO_EDUCACION': 'Educación', 'GASTO_OTROS_BIENES': 'Otros',
        }
        MAPA_ICONO = {
            'GASTO_ALIMENTOS': '🍽️', 'GASTO_VESTIDO': '👕',
            'GASTO_VIVIENDA_SERVICIOS': '🏠', 'GASTO_SALUD': '💊',
            'GASTO_TRANSPORTE': '🚌', 'GASTO_COMUNICACIONES': '📶',
            'GASTO_EDUCACION': '🎓', 'GASTO_OTROS_BIENES': '🛍️',
        }
        gastos_reales = registro_actual_plan.gastos_por_categoria()
        for clave, sugerido in (plan_activo.gastos_sugeridos or {}).items():
            label = MAPA_LABEL.get(clave, clave)
            sugerido = float(sugerido)
            gastado = float(gastos_reales.get(label, 0.0))
            pct = round(gastado / max(sugerido, 0.01) * 100, 1)
            presupuesto_categorias.append({
                'categoria':  label,
                'icono':      MAPA_ICONO.get(clave, '💰'),
                'sugerido':   round(sugerido, 2),
                'gastado':    round(gastado, 2),
                'disponible': round(max(sugerido - gastado, 0.0), 2),
                'excedente':  round(max(gastado - sugerido, 0.0), 2),
                'excedido':   gastado > sugerido,
                'pct':        min(pct, 999),
                'pct_barra':  min(pct, 100),
            })
        presupuesto_categorias.sort(key=lambda c: c['pct'], reverse=True)

    # ── Alerta de presupuesto (spec Tarea 3) ──────────────────────────────────
    # Sin persistencia: se deriva de nuevo en cada render. NO se recalcula "cumple" de
    # otra forma — se toma tal cual de comparacion_plan (10% de tolerancia ya aplicado
    # ahí), y las categorías/montos salen tal cual de presupuesto_categorias.
    alerta_presupuesto = None
    categorias_excedidas = [c for c in presupuesto_categorias if c['excedido']]
    if categorias_excedidas:
        entrada_mes_actual = next(
            (c for c in comparacion_plan if c['registro'] == registro_actual_plan), None
        )
        # Si el mes actual no aparece en comparacion_plan (p. ej. queda fuera de la
        # ventana de 6 meses evaluados) no hay un "cumple" confiable que consultar —
        # se omite la alerta en vez de inventar un estado.
        if entrada_mes_actual is not None:
            total_excedente = sum(c['excedente'] for c in presupuesto_categorias)
            total_disponible = sum(
                c['disponible'] for c in presupuesto_categorias if not c['excedido']
            )
            nombres_excedidas = _listar_nombres(c['categoria'] for c in categorias_excedidas)

            if entrada_mes_actual['cumple']:
                alerta_presupuesto = {
                    'nivel': 'success',
                    'mensaje': (
                        f'Te pasaste en {nombres_excedidas} pero lo compensaste en otras '
                        f'y aun así alcanzaste tu meta de ahorro de este mes.'
                    ),
                }
            elif total_disponible >= total_excedente:
                nombres_disponibles = _listar_nombres(
                    c['categoria'] for c in presupuesto_categorias
                    if not c['excedido'] and c['disponible'] > 0
                )
                alerta_presupuesto = {
                    'nivel': 'warning',
                    'mensaje': (
                        f'Te pasaste S/ {total_excedente:.0f} en {nombres_excedidas}, pero '
                        f'tenías S/ {total_disponible:.0f} disponibles en {nombres_disponibles} '
                        f'que lo hubieran cubierto. El faltante frente a tu meta viene de otro '
                        f'lado, no de estas categorías.'
                    ),
                }
            else:
                alerta_presupuesto = {
                    'nivel': 'error',
                    'mensaje': (
                        f'No se puede cubrir tu exceso de gasto con lo disponible en otras '
                        f'categorías: gastaste S/ {total_excedente - total_disponible:.0f} más '
                        f'de lo presupuestado en total, por eso no cumpliste la meta de ahorro '
                        f'de este mes. Considera ajustar tu meta a tu capacidad real de ahorro.'
                    ),
                }

    return render(request, 'gamificacion/progreso.html', {
        'registros':               registros,
        'meses_labels':            meses_labels,
        'ahorro_data':             ahorro_data,
        'tasa_data':               tasa_data,
        'mejor_tasa':              mejor_tasa,
        'total_logros':            total_logros,
        'total_logros_posibles':   total_logros_posibles,
        'plan_activo':             plan_activo,
        'comparacion_plan':        comparacion_plan,
        'presupuesto_categorias':  presupuesto_categorias,
        'registro_actual_plan':    registro_actual_plan,
        'alerta_presupuesto':      alerta_presupuesto,
    })
