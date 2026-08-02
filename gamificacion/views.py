import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.constants import MESES_ES_ABREV
from gamificacion.models import Logro, LogroUsuario


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

    comparacion_plan = []
    if plan_activo:
        # Evaluar el plan desde el MES para el que fue generado (el mes actual del
        # análisis), no desde antes: un mes que ya transcurrió no pudo seguir un plan
        # que aún no existía. Fallback al mes de adopción si no hay resultado asociado.
        if plan_activo.resultado_id and plan_activo.resultado.registro_id:
            mes_inicio = plan_activo.resultado.registro.periodo.replace(day=1)
        else:
            mes_inicio = plan_activo.fecha_seleccion.date().replace(day=1)
        regs_post = RegistroMensual.objects.filter(
            usuario=request.user,
            periodo__gte=mes_inicio,
        ).order_by('periodo')[:6]

        # Umbral con 10% de tolerancia hacia abajo, válido también si el ahorro
        # proyectado es NEGATIVO (plan que solo reduce el déficit). Usar *0.90 fallaba
        # con proyecciones negativas (hacía el umbral más exigente que la propia meta).
        proj = plan_activo.ahorro_proyectado
        umbral_plan = proj - 0.10 * abs(proj)
        for reg in regs_post:
            ahorro_real = float(reg.ahorro_bruto)
            cumple = ahorro_real >= umbral_plan
            comparacion_plan.append({
                'registro':        reg,
                'ahorro_real':     round(ahorro_real, 2),
                'ahorro_objetivo': plan_activo.ahorro_proyectado,
                'cumple':          cumple,
                'diff':            round(ahorro_real - plan_activo.ahorro_proyectado, 2),
                'porcentaje':      round(ahorro_real / plan_activo.ahorro_proyectado * 100, 1)
                                   if plan_activo.ahorro_proyectado > 0 else 0,
            })

    # ── Presupuesto por categoría (spec §8.1) ─────────────────────────────────
    # Pantalla persistente y consultiva: monto máximo sugerido por categoría (del plan
    # elegido) vs. lo YA gastado en el mes más reciente desde que se adoptó el plan.
    # Solo referencia visual — nunca dispara alertas (coherente con §2: sin tiempo real).
    presupuesto_categorias = []
    registro_actual_plan = None
    if plan_activo:
        # comparacion_plan ya está en orden ascendente por periodo (regs_post): el
        # último elemento es el registro más reciente desde que se adoptó el plan.
        registro_actual_plan = comparacion_plan[-1]['registro'] if comparacion_plan else (
            RegistroMensual.objects.filter(usuario=request.user, periodo__gte=mes_inicio)
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
    })
