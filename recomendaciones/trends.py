"""
Análisis de tendencia financiera multi-mes (capa Django — NO toca el modelo).

Complementa el análisis de un solo mes de `src/predict.py` con la evolución del
usuario a lo largo de su historial:
  - dirección del ahorro (positiva / negativa / estable),
  - categoría de gasto con mayor crecimiento (dónde enfocar los recortes),
  - meta de escalamiento sugerida (spec Modo 3: promedio últimos 3 meses × 1.25),
  - candidatos para el menú de metas (spec §4, Opción A) y contexto anti-estatismo
    (spec §3) que src/predict.py no puede calcular por sí solo (dependen de BD).

Implementa los "modos adaptativos" del spec sin modificar la lógica de inferencia:
el modelo sigue operando sobre un solo mes; esto es una capa de contexto encima.
"""
import unicodedata

from financiero.models import RegistroMensual


def _avg(valores):
    return sum(valores) / len(valores) if valores else 0.0


def historial_user_dicts(usuario, n=6):
    """Últimos `n` registros del usuario como user-dicts en orden cronológico
    (antiguo -> reciente), listos para pasar a recommend(historial=...)."""
    regs = list(RegistroMensual.objects.filter(usuario=usuario).order_by('-periodo')[:n])
    return [r.to_user_dict() for r in reversed(regs)]


def es_mes_atipico(registro, n=6):
    """Spec §6: True si el gasto total del `registro` supera 2x el promedio histórico
    del usuario (excluyendo el propio registro). Requiere ≥2 OTROS meses para comparar;
    si no hay suficiente historial, no se puede calificar de "atípico" (False)."""
    from src.predict import es_mes_atipico as _es_atipico
    otros = list(
        RegistroMensual.objects.filter(usuario=registro.usuario)
        .exclude(pk=registro.pk).order_by('-periodo')[:n]
    )
    if len(otros) < 2:
        return False
    promedio = _avg([r.gasto_total for r in otros])
    return _es_atipico(registro.to_user_dict(), promedio)


def contexto_anti_estatismo(usuario, antes_de=None):
    """Spec §3 (anti-estatismo): devuelve {"categoria_objetivo": str} del análisis
    INMEDIATO ANTERIOR del usuario (antes de la fecha `antes_de`, o el más reciente si
    no se indica), para que recommend() rote la categoría objetivo si coincidiría con
    la del mes pasado. {} si no hay análisis previo o no guardó categoría."""
    from recomendaciones.models import ResultadoML
    qs = ResultadoML.objects.filter(usuario=usuario).exclude(categoria_objetivo='')
    if antes_de is not None:
        qs = qs.filter(creado_en__lt=antes_de)
    anterior = qs.order_by('-creado_en').first()
    if not anterior:
        return {}
    return {'categoria_objetivo': anterior.categoria_objetivo}


def candidatos_meta(usuario, tendencia=None):
    """Spec §4 (Opción A) y §5 (Modo 3): arma los candidatos numéricos para el menú de
    metas de un usuario cuyo ahorro real del mes ya es ≥0 — src/predict.py NO puede
    calcularlos solo porque dependen de BD (historial + MetaLargoPlazo activa):
      - escalamiento: se reutiliza `tendencia['meta_escalamiento']` (única fuente de la
        fórmula Modo 3 — promedio últimos 3 meses × 1.25 — para no duplicarla; si no se
        pasa `tendencia`, se calcula aquí con `analizar_tendencia`).
      - meta_largo_plazo: SUMA de la cuota mensual sugerida de TODAS las metas activas
        con fecha límite (spec §8.3: cada cuota se recalcula siempre, nunca queda fija).
        Si solo hubiera una meta con fecha límite, el resultado es igual que antes; con
        varias, el monto sugerido cubre el avance de todas a la vez (antes solo se
        tomaba la de fecha más próxima y las demás quedaban fuera del candidato).
    `ideal_20` NO se incluye aquí: src/predict.py ya lo calcula internamente (20% del
    ingreso del propio user_dict, sin depender de BD).
    """
    from recomendaciones.models import MetaLargoPlazo

    out = {}

    if tendencia is None:
        tendencia = analizar_tendencia(usuario)
    if tendencia and tendencia.get('meta_escalamiento'):
        out['escalamiento'] = tendencia['meta_escalamiento']

    metas_activas = (
        MetaLargoPlazo.objects.filter(usuario=usuario, activa=True, fecha_limite__isnull=False)
        .order_by('fecha_limite')
    )
    cuotas = [(m, m.cuota_mensual_sugerida) for m in metas_activas]
    cuotas = [(m, c) for m, c in cuotas if c]
    if cuotas:
        out['meta_largo_plazo'] = round(sum(c for _, c in cuotas), 2)
        nombres = [m.nombre for m, _ in cuotas]
        out['meta_largo_plazo_nombre'] = (
            nombres[0] if len(nombres) == 1
            else ', '.join(nombres[:-1]) + ' y ' + nombres[-1]
        )

    return out


def mes_inicio_plan(plan_activo):
    """Mes desde el que un PlanSeleccionado empieza a evaluarse: el mes del análisis
    que lo originó (mismo período que su `resultado.registro`), o el de adopción si no
    tiene un análisis asociado. Único punto de esta regla — usado por `comparacion_plan`
    y por gamificacion/views.py::progreso para el fallback sin registros posteriores."""
    if plan_activo.resultado_id and plan_activo.resultado.registro_id:
        return plan_activo.resultado.registro.periodo.replace(day=1)
    return plan_activo.fecha_seleccion.date().replace(day=1)


def comparacion_plan(usuario, plan_activo):
    """Compara, mes a mes desde que se adoptó `plan_activo`, el ahorro real contra el
    ahorro proyectado del plan (10% de tolerancia hacia abajo, válida también si la
    proyección es negativa — un plan que solo reduce el déficit).

    Única fuente de la regla "cumple/no cumple" un plan: la usa
    gamificacion/views.py::progreso para la tabla de seguimiento y
    gamificacion/services.py para los logros de constancia de plan (no se duplica el
    umbral en ningún otro lugar)."""
    if not plan_activo:
        return []
    mes_inicio = mes_inicio_plan(plan_activo)
    regs_post = RegistroMensual.objects.filter(
        usuario=usuario, periodo__gte=mes_inicio,
    ).order_by('periodo')[:6]

    proj = plan_activo.ahorro_proyectado
    umbral_plan = proj - 0.10 * abs(proj)
    out = []
    for reg in regs_post:
        ahorro_real = float(reg.ahorro_bruto)
        cumple = ahorro_real >= umbral_plan
        out.append({
            'registro':        reg,
            'ahorro_real':     round(ahorro_real, 2),
            'ahorro_objetivo': plan_activo.ahorro_proyectado,
            'cumple':          cumple,
            'diff':            round(ahorro_real - plan_activo.ahorro_proyectado, 2),
            'porcentaje':      round(ahorro_real / plan_activo.ahorro_proyectado * 100, 1)
                               if plan_activo.ahorro_proyectado > 0 else 0,
        })
    return out


def normalizar_categoria(nombre):
    """Clave canónica para comparar categorías entre la tendencia (labels de
    gastos_por_categoria) y el plan (categorias de predict.py), que difieren
    en acentos y sufijos (ej. 'Educación' vs 'Educacion', 'Otros' vs 'Otros Bienes',
    'Vivienda/Serv.' vs 'Vivienda Servicios'). Quita acentos y toma la 1ra palabra."""
    s = unicodedata.normalize('NFKD', nombre or '').encode('ascii', 'ignore').decode()
    s = s.lower().replace('/', ' ').strip()
    return s.split()[0] if s else ''


def analizar_tendencia(usuario, n=6):
    """
    Analiza la tendencia de los últimos `n` registros del usuario.
    Devuelve None si hay menos de 2 meses (Modo 1 — Diagnóstico, sin tendencia).
    """
    regs = list(
        RegistroMensual.objects.filter(usuario=usuario).order_by('-periodo')[:n]
    )
    if len(regs) < 2:
        return None

    regs = list(reversed(regs))  # orden cronológico: antiguo -> reciente
    ahorros = [r.ahorro_bruto for r in regs]
    ing_prom = _avg([r.ing_total for r in regs])

    # Tendencia = promedio reciente − promedio antiguo (mitades del historial),
    # con umbral del 5% del ingreso (o S/30) para no marcar ruido como tendencia.
    mitad = len(regs) // 2
    antiguos = regs[:mitad] or regs[:1]
    recientes = regs[mitad:]
    ahorro_antiguo = _avg([r.ahorro_bruto for r in antiguos])
    ahorro_reciente = _avg([r.ahorro_bruto for r in recientes])
    delta = ahorro_reciente - ahorro_antiguo
    umbral = max(ing_prom * 0.05, 30)
    if delta > umbral:
        tendencia = 'positiva'
    elif delta < -umbral:
        tendencia = 'negativa'
    else:
        tendencia = 'estable'

    # Categoría de mayor crecimiento: promedio por categoría reciente vs antiguo.
    def _avg_cats(rs):
        acc = {}
        for r in rs:
            for c, v in r.gastos_por_categoria().items():
                acc[c] = acc.get(c, 0) + v
        return {c: v / len(rs) for c, v in acc.items()}

    cini, cfin = _avg_cats(antiguos), _avg_cats(recientes)
    crecimientos = {c: round(cfin.get(c, 0) - cini.get(c, 0), 2) for c in cfin}
    cat_top, cat_delta = max(crecimientos.items(), key=lambda kv: kv[1])

    # Meta de escalamiento (spec Modo 3): si los últimos 3 meses ahorran Y la
    # tendencia no va a la baja, promedio_últimos_3 × 1.25 redondeado a múltiplo de 10.
    # (No tiene sentido sugerir subir la meta cuando el ahorro viene cayendo.)
    meta_escalamiento = None
    ult3 = ahorros[-3:]
    if len(ult3) >= 3 and all(a > 0 for a in ult3) and tendencia != 'negativa':
        meta_escalamiento = round(_avg(ult3) * 1.25 / 10) * 10

    return {
        'n_meses':                len(regs),
        'tendencia':              tendencia,
        'delta_ahorro':           round(delta, 2),
        'ahorro_promedio':        round(_avg(ahorros), 2),
        'ahorro_reciente':        round(ahorro_reciente, 2),
        'cat_mayor_crecimiento':  cat_top,
        'cat_crecimiento_monto':  cat_delta,
        'cat_key':                normalizar_categoria(cat_top),  # para cruzar con el plan
        'crece':                  cat_delta > 0.5,
        'meta_escalamiento':      meta_escalamiento,
    }
