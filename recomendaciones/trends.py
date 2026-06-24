"""
Análisis de tendencia financiera multi-mes (capa Django — NO toca el modelo).

Complementa el análisis de un solo mes de `src/predict.py` con la evolución del
usuario a lo largo de su historial:
  - dirección del ahorro (positiva / negativa / estable),
  - categoría de gasto con mayor crecimiento (dónde enfocar los recortes),
  - meta de escalamiento sugerida (spec Modo 3: promedio últimos 3 meses × 1.25).

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
