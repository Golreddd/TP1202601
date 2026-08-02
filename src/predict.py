# -*- coding: utf-8 -*-
"""
Inferencia de SmartSave — clasificación + SHAP + recomendaciones (counterfactual).

Carga los artefactos entrenados (NUNCA re-entrena) y expone:
  - classify(user)        -> Perfil (0=Déficit / 1=Ahorra) + probabilidad (modelo honesto).
  - ahorro_identidad(user)-> ahorro real exacto = ingreso − gasto.
  - shap_explain(user)    -> variables que más empujan la clasificación (diagnóstico),
                              con magnitud relativa y accionabilidad (spec §7).
  - recommend(user, ...)  -> VARIAS opciones de recomendación para elegir, con meta
                              dinámica (incluye override §6 y menú de alternativas §4).

Diseño realista (sin fuga): el clasificador NO recibe los gastos discrecionales
(OTROS_BIENES, vestido, comunicaciones) ni montos crudos de gasto, así que el
counterfactual NO se hace moviendo variables dentro del modelo. Se opera sobre el
PRESUPUESTO REAL con la identidad contable exacta (cada sol recortado = un sol más de
ahorro), con recortes acotados por categoría (compresibilidad realista: más en gastos
hormiga, menos en lo esencial), y cada opción se re-clasifica con el modelo.

Perfil vs. resultado del mes (clave metodológica, spec §1.1 del diseño): `classify()`
predice una TENDENCIA ESTRUCTURAL de ahorro a partir de variables honestas (ingreso,
demografía, ratios de gasto comprometido) — NO mira el resultado exacto del mes
(`ahorro_identidad`, que es una resta exacta y trivial). Cuando ambos coinciden, el
diagnóstico se refuerza; cuando DIFIEREN (perfil ahorrador con mes en déficit, o
perfil deficitario con mes positivo) es el caso más rico y el que más valor aporta,
y el motor lo trata explícitamente (ver `_plan_objetivo`, escenarios *_override).
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .preprocessing import (CLASS_LABELS, ESENCIAL, GASTO_COLS,
                            ahorro_identidad, build_feature_row, gasto_total, ing_total)

_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
_CACHE: dict = {}

MAX_CUT_FRAC = 0.40  # fallback si una categoría no está en MAX_CUT_BY_CAT

# Compresibilidad realista POR CATEGORÍA: cuánto se puede recortar como máximo de cada
# gasto en un mes. NO es plano: lo esencial tiene piso de subsistencia (se recorta poco);
# los gastos hormiga / discrecionales se pueden recortar mucho más. Corroborado con el
# dataset: los hogares que AHORRAN gastan menos en todas las categorías y la mayor brecha
# es Otros Bienes (ahorradores ~0.41 vs déficit ~1.03 del ingreso). Valores ajustables.
# Nota metodológica: el spec habla de un tope "40% por categoría"; aquí se refina a
# compresibilidad ESPECÍFICA por categoría (0.15–0.70) porque un tope plano no distingue
# gasto hormiga de gasto esencial — más defendible y más realista para el usuario.
MAX_CUT_BY_CAT = {
    "GASTO_OTROS_BIENES":       0.70,  # gasto hormiga: muy recortable
    "GASTO_VESTIDO":            0.60,  # discrecional
    "GASTO_COMUNICACIONES":     0.50,  # discrecional (plan/datos)
    "GASTO_EDUCACION":          0.30,  # flexible
    "GASTO_SALUD":              0.25,  # flexible (no descuidar)
    "GASTO_TRANSPORTE":         0.20,  # esencial con algo de margen
    "GASTO_ALIMENTOS":          0.15,  # esencial: piso de subsistencia
    "GASTO_VIVIENDA_SERVICIOS": 0.15,  # esencial: piso (alquiler/servicios)
}


def cut_frac(cat: str) -> float:
    """Fracción máxima recortable de una categoría (compresibilidad realista por tipo)."""
    return MAX_CUT_BY_CAT.get(cat, MAX_CUT_FRAC)


# TIERS de recorte por prioridad: un especialista recorta primero lo más prescindible.
# Dentro de cada tier el recorte se reparte de forma GRADUAL (proporcional a la capacidad),
# SIN agotar una categoría antes de tocar las otras. Vivienda y alimentos van SIEMPRE al final.
_TIER_HORMIGA  = ["GASTO_OTROS_BIENES", "GASTO_VESTIDO", "GASTO_COMUNICACIONES"]   # discrecional
_TIER_FLEXIBLE = ["GASTO_SALUD", "GASTO_EDUCACION", "GASTO_TRANSPORTE"]            # ajustable
_TIER_ESENCIAL = ["GASTO_VIVIENDA_SERVICIOS", "GASTO_ALIMENTOS"]                   # último recurso
# Orden de prioridad de recorte (para mostrar siempre lo prescindible primero, esencial al final).
_CUT_ORDER = _TIER_HORMIGA + _TIER_FLEXIBLE + _TIER_ESENCIAL
_CUT_PRIO = {c: i for i, c in enumerate(_CUT_ORDER)}

# Estrategias: se diferencian por hasta qué tier están dispuestas a llegar (no por cuánto
# rebanan de cada categoría: eso lo fija la meta dinámica + el tope por categoría).
_STRATEGIES = [
    {"nombre": "Suave", "tiers": [_TIER_HORMIGA],
     "desc": "Ajuste ligero, solo en gastos hormiga y discrecionales (otros bienes, vestido, "
             "comunicaciones). Pensado para empezar a crear el hábito sin que se note."},
    {"nombre": "Equilibrado", "tiers": [_TIER_HORMIGA, _TIER_FLEXIBLE],
     "desc": "Primero discrecionales y, si hace falta, flexibles (salud, educación, transporte). "
             "No toca vivienda ni alimentos."},
    {"nombre": "Decidido", "tiers": [_TIER_HORMIGA, _TIER_FLEXIBLE, _TIER_ESENCIAL],
     "desc": "Si la meta lo exige, ajusta también lo esencial — vivienda y alimentos al final "
             "y lo mínimo posible."},
]

# Metas de ahorro DINÁMICAS (personalizadas por ingreso y perfil). NUNCA se propone subir
# ingresos ni cambiar estrato/miembros: el plan es siempre vía recorte de gasto.
_PASO_AHORRADOR       = 0.10   # perfil con hábito: sube la meta ~10% del ingreso
_PASO_NO_AHORRADOR    = 0.05   # perfil sin hábito: pasos más suaves (~5%)
_UMBRAL_TOLERANCIA    = 0.05   # spec §6: banda de "casi equilibrio" = 5% del ingreso
                                # (unifica el umbral: aplica tanto al override de perfil
                                # ahorrador con balance negativo como al déficit genuino bajo)
_AHORRO_MINIMO_FRAC   = 0.03   # primer ahorro mínimo ~3% del ingreso
_PASO_MIN             = 20.0   # paso mínimo en soles para que la meta tenga sentido
_IDEAL_INGRESO_FRAC   = 0.20   # regla 50/30/20 (spec §4, Opción A.2)
_MES_ATIPICO_FACTOR   = 2.0    # spec §6: gasto > 2x promedio histórico => mes atípico

# Escenarios de déficit: el objetivo es una función pura de (ahorro, ingreso, perfil),
# el usuario NUNCA elige nada (spec §4) -> nunca se "congelan" al reproducir un análisis
# pasado (ver forzar_escenario en _plan_objetivo). Los demás (meta_usuario, escalamiento,
# ideal_20, meta_largo_plazo, incremental) sí involucran una elección o un candidato
# externo (historial, MetaLargoPlazo) y por eso sí se fijan para reproducir fielmente.
_ESCENARIOS_DETERMINISTAS = {
    "deficit", "deficit_bajo", "deficit_leve_override", "deficit_significativo_override",
}


def load_models() -> dict:
    global _CACHE
    if _CACHE:
        return _CACHE
    needed = {"model": "xgb_clf_model.pkl", "scaler": "scaler.pkl", "shap": "shap_explainer.pkl"}
    out = {}
    for key, fname in needed.items():
        path = _MODELS_DIR / fname
        if not path.exists():
            raise FileNotFoundError(f"Artefacto no encontrado: {path}. Ejecuta `python -m src.train`.")
        out[key] = joblib.load(path)
    with open(_MODELS_DIR / "features.json", encoding="utf-8") as f:
        out["features"] = json.load(f)
    metrics_path = _MODELS_DIR / "metrics.json"
    if metrics_path.exists():
        with open(metrics_path, encoding="utf-8") as f:
            out["metrics"] = json.load(f)
    _CACHE = out
    return out


def _vector(user: dict, models: dict) -> np.ndarray:
    row = build_feature_row(user, models["features"])
    return models["scaler"].transform(row)


def classify(user: dict) -> dict:
    """Clasifica el PERFIL ESTRUCTURAL de ahorro (no el resultado exacto del mes:
    ver `ahorro_identidad` para eso). `label`/`clase` se mantienen por compatibilidad
    (persistidos en BD); `perfil_label` es la redacción honesta para mostrar al usuario."""
    models = load_models()
    proba = float(models["model"].predict_proba(_vector(user, models))[0, 1])
    clase = int(proba >= 0.5)
    margen = abs(proba - 0.5)
    confianza = "Alta" if margen > 0.30 else ("Media" if margen > 0.15 else "Baja")
    return {
        "clase": clase,
        "label": CLASS_LABELS[clase],
        "perfil_label": PERFIL_LABELS[clase],
        "probabilidad_ahorra": proba,
        "probabilidad_deficit": 1.0 - proba,
        "confianza": confianza,
    }


PERFIL_LABELS = {
    0: "Perfil con tendencia al déficit",
    1: "Perfil con tendencia al ahorro",
}

# Clasificación honesta de cada feature del modelo, para el SHAP interpretable (spec §7):
# tipo determina si es accionable en el corto plazo. Ingreso/demografía NUNCA son
# accionables (el plan nunca sugiere subir ingresos ni cambiar estrato/miembros); los
# ratios de gasto comprometido son PARCIALMENTE accionables (se optimizan, no se cortan
# de golpe). Ninguna feature del modelo es un gasto discrecional puro (se excluyeron por
# diseño anti-fuga): por eso el "puente" hacia el plan de recortes es siempre necesario.
FEATURE_TIPO = {
    "NIVEL_EDUC": "demografico", "MIEMBROS_HOGAR": "demografico", "ESTRATO_SOC": "demografico",
    "DEPENDE_INFORMAL": "ingreso", "ING_PLANILLA": "ingreso", "ING_INFORMAL": "ingreso",
    "LOG_ING": "ingreso", "ING_PER_CAPITA": "ingreso", "INFORMAL_SHARE": "ingreso",
    "TIPO_FORMAL": "ingreso", "TIPO_INFORMAL": "ingreso", "TIPO_MIXTO": "ingreso",
    "PRESION_FINANCIERA": "gasto_comprometido", "COMMIT_PER_CAPITA": "gasto_comprometido",
    "GASTO_ALIMENTOS_R": "gasto_comprometido", "GASTO_VIVIENDA_SERVICIOS_R": "gasto_comprometido",
    "GASTO_TRANSPORTE_R": "gasto_comprometido", "GASTO_SALUD_R": "gasto_comprometido",
    "GASTO_EDUCACION_R": "gasto_comprometido",
}
_ACCIONABLES = {"gasto_comprometido"}  # el resto (ingreso/demografico) no se toca nunca

FEATURE_LABELS = {
    "NIVEL_EDUC": "Nivel educativo", "MIEMBROS_HOGAR": "Miembros del hogar",
    "DEPENDE_INFORMAL": "Dependencia informal", "ING_PLANILLA": "Ingreso planilla",
    "ING_INFORMAL": "Ingreso informal", "LOG_ING": "Ingreso total",
    "ING_PER_CAPITA": "Ingreso per cápita", "INFORMAL_SHARE": "Proporción informal",
    "PRESION_FINANCIERA": "Presión financiera", "COMMIT_PER_CAPITA": "Gasto comprometido per cápita",
    "GASTO_ALIMENTOS_R": "Gasto en alimentos", "GASTO_VIVIENDA_SERVICIOS_R": "Gasto en vivienda",
    "GASTO_TRANSPORTE_R": "Gasto en transporte", "GASTO_SALUD_R": "Gasto en salud",
    "GASTO_EDUCACION_R": "Gasto en educación", "ESTRATO_SOC": "Estrato social",
    "TIPO_FORMAL": "Empleo formal", "TIPO_INFORMAL": "Empleo informal", "TIPO_MIXTO": "Empleo mixto",
}


def _feature_legible(f: str) -> str:
    return FEATURE_LABELS.get(f, f.replace("_", " ").title())


def shap_explain(user: dict, top: int | None = None) -> list:
    """Contribuciones SHAP hacia 'Ahorra'. shap < 0 empuja hacia Déficit (prioridad de acción).

    Cada item incluye, además del signo (spec §7 — interpretabilidad mejorada):
      - pct_impacto: magnitud RELATIVA dentro del top devuelto (no solo signo).
      - tipo / accionable: si el usuario puede actuar sobre esa variable este mes.
    """
    models = load_models()
    feats = models["features"]
    sv = models["shap"](_vector(user, models))
    vals = np.asarray(sv.values).reshape(-1)
    out = sorted(
        [{"feature": f, "shap_value": float(vals[i])} for i, f in enumerate(feats)],
        key=lambda d: abs(d["shap_value"]), reverse=True,
    )
    out = out if top is None else out[:top]
    total_abs = sum(abs(d["shap_value"]) for d in out) or 1.0
    for d in out:
        tipo = FEATURE_TIPO.get(d["feature"], "ingreso")
        d["feature_label"] = _feature_legible(d["feature"])
        d["tipo"] = tipo
        d["accionable"] = tipo in _ACCIONABLES
        d["pct_impacto"] = round(abs(d["shap_value"]) / total_abs * 100, 1)
    return out


def _frase_puente_shap(shap_top: list) -> str:
    """Une el diagnóstico SHAP (estructural) con el plan de recortes (discrecional),
    spec §7: prioriza lo accionable, pero si la causa dominante NO es accionable lo dice
    explícitamente en vez de ocultarlo."""
    if not shap_top:
        return ""
    dominante = shap_top[0]
    nombre, pct = dominante["feature_label"], dominante["pct_impacto"]
    if dominante["accionable"]:
        return (f"Tu factor de mayor peso es «{nombre}» ({pct:.0f}% del diagnóstico): es un gasto "
                f"comprometido, así que además de los recortes flexibles de abajo, vale la pena "
                f"revisarlo con calma (cambiar de plan, renegociar, buscar una alternativa).")
    return (f"Tu factor de mayor peso es «{nombre}» ({pct:.0f}% del diagnóstico): es estructural "
            f"(ingreso o perfil) y no se ajusta en un mes. Por eso el plan de abajo actúa sobre "
            f"tus gastos flexibles, que sí puedes mover ahora.")


def es_mes_atipico(user: dict, promedio_gasto_historico: float | None) -> bool:
    """Spec §6: gasto total > 2x el promedio histórico del usuario => mes atípico."""
    if not promedio_gasto_historico or promedio_gasto_historico <= 0:
        return False
    return gasto_total(user) > _MES_ATIPICO_FACTOR * promedio_gasto_historico


def _crecimiento_por_categoria(historial: list | None) -> dict:
    """Crecimiento de cada categoría a lo largo del historial (capa de contexto MULTI-MES).

    `historial` es una lista de user-dicts en orden cronológico (antiguo -> reciente).
    Devuelve {GASTO_COL: crecimiento} = promedio reciente − promedio antiguo, solo para
    las categorías que REALMENTE crecieron (crecimiento > 0). Vacío si no hay ≥2 meses.
    Esto permite que el counterfactual ataque el gasto que viene aumentando en el tiempo,
    no solo la foto del mes actual.
    """
    if not historial or len(historial) < 2:
        return {}
    mitad = len(historial) // 2
    antiguos = historial[:mitad] or historial[:1]
    recientes = historial[mitad:]
    out = {}
    for c in GASTO_COLS:
        ant = sum(float(h.get(c, 0)) for h in antiguos) / len(antiguos)
        rec = sum(float(h.get(c, 0)) for h in recientes) / len(recientes)
        crec = rec - ant
        if crec > 0.5:
            out[c] = round(crec, 2)
    return out


def _categoria_lider(prioridad: dict, evitar: str | None = None) -> str | None:
    """Categoría con mayor crecimiento. Si coincide con `evitar` (categoría objetivo del
    mes anterior) y hay una segunda opción válida, rota a la siguiente — anti-estatismo
    (spec §3): nunca repetir la misma categoría objetivo 2 meses seguidos si los datos
    permiten variar."""
    if not prioridad:
        return None
    ranked = sorted(prioridad.items(), key=lambda kv: kv[1], reverse=True)
    if evitar:
        for cat, _ in ranked:
            if cat != evitar:
                return cat
    return ranked[0][0]


def _allocate(user: dict, tiers: list, needed: float, prioridad: dict | None = None):
    """Recorta `needed` recorriendo los TIERS en orden (lo más prescindible primero;
    vivienda y alimentos al final).

    Si se pasa `prioridad` (crecimiento por categoría del historial), DENTRO de cada tier
    se atacan PRIMERO las categorías que más han crecido en el tiempo (cada una hasta su
    tope), y solo después se reparte el resto de forma proporcional. Sin `prioridad`, el
    reparto es gradual y proporcional (comportamiento por defecto, foto del mes actual).
    Devuelve (gastos_optimizados, faltante). faltante>0 => infactible dentro de los topes.
    """
    gastos = {c: float(user.get(c, 0)) for c in GASTO_COLS}
    opt = dict(gastos)
    remaining = max(needed, 0.0)
    for tier in tiers:
        if remaining <= 1e-9:
            break
        caps = {c: gastos[c] * cut_frac(c) for c in tier}
        cap_total = sum(caps.values())
        if cap_total <= 1e-9:
            continue
        if prioridad:
            # 1) Categorías que crecieron (mayor crecimiento primero), cada una a su tope.
            crecen = sorted((c for c in tier if prioridad.get(c, 0) > 0),
                            key=lambda c: prioridad[c], reverse=True)
            for c in crecen:
                if remaining <= 1e-9:
                    break
                corte = min(caps[c], remaining)
                opt[c] -= corte
                remaining -= corte
            # 2) El resto del tier, proporcional con lo que quede por recortar.
            resto = [c for c in tier if prioridad.get(c, 0) <= 0]
            cap_resto = sum(caps[c] for c in resto)
            if remaining > 1e-9 and cap_resto > 1e-9:
                ratio = min(1.0, remaining / cap_resto)
                for c in resto:
                    opt[c] -= caps[c] * ratio
                remaining -= cap_resto * ratio
        else:
            ratio = 1.0 if remaining >= cap_total else remaining / cap_total  # reparto proporcional
            for c in tier:
                opt[c] -= caps[c] * ratio
            remaining -= cap_total * ratio
    return opt, remaining


def _opcion(user: dict, strat: dict, needed: float, prioridad: dict | None = None,
           cat_lider: str | None = None) -> dict:
    opt, faltante = _allocate(user, strat["tiers"], needed, prioridad)
    user_opt = {**user, **opt}
    ahorro_res = ing_total(user) - sum(opt[c] for c in GASTO_COLS)
    clase_opt = classify(user_opt)
    # Solo se marca la categoría LÍDER (ya con anti-estatismo aplicado por el llamador)
    # con el badge; la asignación sí prioriza todas las que crecieron.
    reducciones = []
    for c in GASTO_COLS:
        rec = float(user.get(c, 0)) - opt[c]
        if rec > 0.5:
            reducciones.append({
                "categoria": c.replace("GASTO_", "").replace("_", " ").title(),
                "original": round(float(user.get(c, 0)), 2),
                "sugerido": round(opt[c], 2),
                "recorte": round(rec, 2),
                "pct": round(rec / max(float(user.get(c, 0)), 0.01) * 100, 1),
                # True si es la categoría líder de crecimiento (multi-mes, con rotación).
                "por_tendencia": (c == cat_lider),
                "_prio": _CUT_PRIO.get(c, 99),
            })
    reducciones.sort(key=lambda r: r["_prio"])  # prescindible primero, vivienda/alimentos al final
    return {
        "nombre": strat["nombre"],
        "descripcion": strat["desc"],
        "alcanza_meta": faltante <= 1.0,
        "faltante": round(max(faltante, 0.0), 2),
        "ahorro_resultante": round(ahorro_res, 2),
        "reduccion_total": round(sum(r["recorte"] for r in reducciones), 2),
        "reducciones": reducciones,
        "clase_modelo": clase_opt["label"],
        "prob_ahorra_modelo": round(clase_opt["probabilidad_ahorra"], 3),
        "gastos_optimizados": {c: round(opt[c], 2) for c in GASTO_COLS},
    }


def _plan_objetivo(user: dict, cls: dict, meta: float | None = None,
                   alternativa: str | None = None, candidatos_meta: dict | None = None,
                   forzar_escenario: str | None = None, forzar_objetivo: float | None = None) -> dict:
    """Define el objetivo de ahorro DINÁMICO y personalizado (rol de especialista).

    No es estático: depende del ingreso, del perfil del modelo (con/sin hábito), del
    ahorro real del mes y — si aplica — de la meta elegida por el usuario en el menú de
    alternativas (spec §4). Reglas (spec §4 y §6):
      • Meta del usuario (Opción B)     -> se respeta; advierte si supera lo disponible
                                            tras gastos esenciales.
      • Perfil ahorrador + balance real negativo (contradicción, §6):
          - déficit ≤5% del ingreso     -> "leve": meta = equilibrio (0), mensaje conciliador.
          - déficit >5% del ingreso     -> "significativo": OVERRIDE — se trata como déficit
                                            funcional aunque el modelo diga "ahorra"; meta = 0,
                                            sin escalamiento ni metas ambiciosas.
      • Perfil deficitario + balance real negativo (déficit genuino, mismo umbral 5%):
          - "bajo"                      -> meta = pequeño ahorro mínimo (~3% ingreso).
          - "alto"                      -> meta = equilibrio (0).
      • Balance real ≥0 (cualquier perfil) -> flujo normal: si hay `alternativa` elegida
        del menú (escalamiento / 20% ingreso / meta largo plazo) se usa esa; si no, se
        aplica automáticamente el escalamiento (Modo 3) cuando está disponible, o un
        incremento gradual acotado (Modo 1/2) en caso contrario.
    Nunca propone subir ingresos ni cambiar estrato/miembros.
    """
    ing = ing_total(user)
    ahorro = ahorro_identidad(user)
    umbral = ing * _UMBRAL_TOLERANCIA
    ahorro_min = max(round(ing * _AHORRO_MINIMO_FRAC), _PASO_MIN)

    candidatos = dict(candidatos_meta or {})
    candidatos.setdefault("ideal_20", max(round(ing * _IDEAL_INGRESO_FRAC), _PASO_MIN))

    # ── Reproducción fiel de un análisis pasado (ResultadoML.recomputar) ─────────
    # Reusa el MISMO escenario y monto ya resueltos entonces, sin re-derivar reglas:
    # evita que revisar el historial cambie el tipo de meta mostrado solo porque pasó
    # el tiempo, cambió el historial multi-mes, o (antes de esta corrección) porque
    # recomputar() reenviaba meta_validada como meta explícita y todo colapsaba a
    # "meta_usuario" perdiendo el mensaje original (escalamiento, overrides, etc.).
    #
    # EXCEPCIÓN IMPORTANTE: los escenarios de déficit son 100% deterministas —objetivo
    # es una función pura de (ahorro, ingreso, perfil), sin ninguna elección del usuario
    # de por medio— así que NUNCA se congelan con forzar_objetivo. Si se congelaran,
    # una fila con un monto corrupto (p. ej. de antes de una corrección de reglas)
    # quedaría atascada en ese valor para siempre, porque cada recompute reproduciría
    # el mismo número equivocado en vez de autosanarse. Al dejarlas caer al flujo
    # normal de abajo, se re-derivan siempre desde los datos actuales del registro.
    if forzar_escenario is not None and forzar_escenario not in _ESCENARIOS_DETERMINISTAS:
        return {"escenario": forzar_escenario, "objetivo": float(forzar_objetivo or 0.0),
                "paso": 0.0, "ahorro": ahorro, "ing": ing, "advertencia": None,
                "candidatos": candidatos, "menu": []}

    # ── Balance real negativo: el sistema IMPONE la meta, el usuario no la define
    # libremente (spec §4) — se evalúa ANTES que la meta/alternativa explícita para que
    # nadie pueda "saltarse" el equilibrio obligatorio con una meta libre optimista. ────
    if ahorro < 0:
        if cls["clase"] == 1:
            # Contradicción: el modelo dice "ahorra" pero el mes real está en déficit.
            if abs(ahorro) <= umbral:
                escenario = "deficit_leve_override"
                menu = [{"clave": "equilibrio", "nombre": "Equilibrio sólido", "monto": 0.0,
                         "descripcion": "Consolida tu balance en cero antes de pensar en escalar.",
                         "activa": True}]
            else:
                escenario = "deficit_significativo_override"
                menu = []
            objetivo = 0.0  # equilibrio primero; sin escalamiento ni metas ambiciosas
        else:
            if abs(ahorro) <= umbral:
                escenario, objetivo, menu = "deficit_bajo", float(ahorro_min), []
            else:
                escenario, objetivo, menu = "deficit", 0.0, []
        return {"escenario": escenario, "objetivo": objetivo, "paso": 0.0,
                "ahorro": ahorro, "ing": ing, "advertencia": None,
                "candidatos": candidatos, "menu": menu}

    # ── Opción B: meta libre definida por el usuario (solo si ya no está en déficit) ──
    if meta is not None and float(meta) > 0:
        objetivo = float(meta)
        disponible = max(ing - sum(float(user.get(c, 0)) for c in ESENCIAL), 0.0)
        advertencia = None
        if objetivo > disponible:
            advertencia = (
                f"Esta meta (S/. {objetivo:.0f}) puede ser difícil de alcanzar con tu perfil "
                f"actual (disponible tras gastos esenciales ≈ S/. {disponible:.0f}). "
                "¿Deseas ajustarla o continuar?"
            )
        return {"escenario": "meta_usuario", "objetivo": objetivo, "paso": 0.0,
                "ahorro": ahorro, "ing": ing, "advertencia": advertencia,
                "candidatos": candidatos, "menu": []}

    # ── Balance real ≥ 0: flujo normal, menú de alternativas (spec §4) ───────────
    cap_disc = sum(float(user.get(c, 0)) * cut_frac(c) for c in _TIER_HORMIGA)
    paso_incremental = max(round(min(
        max(ing * (_PASO_AHORRADOR if cls["clase"] == 1 else _PASO_NO_AHORRADOR), _PASO_MIN),
        0.5 * cap_disc)), _PASO_MIN)

    menu = []
    if candidatos.get("escalamiento"):
        menu.append({"clave": "escalamiento", "nombre": "Escalamiento progresivo",
                     "monto": float(candidatos["escalamiento"]),
                     "descripcion": "Promedio de tus últimos 3 meses ×1.25 — sigue tu ritmo de mejora."})
    menu.append({"clave": "ideal_20", "nombre": "20% de tu ingreso",
                 "monto": float(candidatos["ideal_20"]),
                 "descripcion": "Regla 50/30/20: destina una quinta parte de tu ingreso al ahorro."})
    if candidatos.get("meta_largo_plazo"):
        nombre_meta = candidatos.get("meta_largo_plazo_nombre", "tu meta")
        menu.append({"clave": "meta_largo_plazo", "nombre": f"Meta: {nombre_meta}",
                     "monto": float(candidatos["meta_largo_plazo"]),
                     "descripcion": "Cuota mensual necesaria para cumplirla en el plazo definido."})

    if alternativa and candidatos.get(alternativa):
        escenario, objetivo = alternativa, float(candidatos[alternativa])
    elif candidatos.get("escalamiento"):
        # Modo 3: 3+ meses cumpliendo meta => escalamiento automático (spec §5).
        escenario, objetivo = "escalamiento", float(candidatos["escalamiento"])
    else:
        escenario, objetivo = "incremental", round(ahorro + paso_incremental, 2)

    for m in menu:
        m["activa"] = (m["clave"] == escenario)

    return {"escenario": escenario, "objetivo": objetivo, "paso": paso_incremental,
            "ahorro": ahorro, "ing": ing, "advertencia": None,
            "candidatos": candidatos, "menu": menu}


def _mensaje_especialista(plan: dict, cls: dict) -> str:
    """Mensaje en rol de especialista en finanzas personales, según escenario + perfil."""
    ahorro, ing, esc = plan["ahorro"], plan["ing"], plan["escenario"]
    obj = plan["objetivo"]

    # Nota por discrepancia perfil (modelo) vs realidad contable del mes — solo para los
    # casos que NO tienen ya su propio mensaje de contradicción dedicado.
    nota = ""
    if cls["clase"] == 0 and ahorro >= 0:
        nota = (" Aunque tu perfil estructural tiende al déficit, este mes ahorraste: "
                "mantener el hábito ya es un logro, vamos paso a paso.")

    if esc == "deficit":
        return (f"Este mes gastaste S/. {abs(ahorro):.0f} más de lo que ingresó. La prioridad #1 "
                f"es volver al equilibrio (ahorro 0) antes de pensar en guardar." + nota)
    if esc == "deficit_bajo":
        return (f"Tu déficit (S/. {abs(ahorro):.0f}) es bajo frente a tu ingreso "
                f"({abs(ahorro) / max(ing, 1.0) * 100:.0f}%). Volvamos a 0 y, ya que estás cerca, "
                f"intentemos guardar al menos S/. {obj:.0f} — un primer ahorro pequeño pero real." + nota)
    if esc == "deficit_leve_override":
        return (f"Tu balance este mes es casi neutro (S/. {ahorro:.0f}). Estás muy cerca del "
                f"equilibrio financiero. Tu perfil tiende a ahorrar, así que consolidar el balance "
                f"en 0 debería ser un ajuste manejable.")
    if esc == "deficit_significativo_override":
        return (f"El modelo detecta patrones positivos en tu perfil, pero tu balance real este mes "
                f"es negativo (S/. {ahorro:.0f}). Te ayudamos a llegar al equilibrio primero, sin "
                f"metas ambiciosas todavía — eso viene después.")
    if esc == "escalamiento":
        return (f"¡Llevas varios meses cumpliendo tu meta! Es hora de subir el nivel: tu nueva meta "
                f"es S/. {obj:.0f} (promedio de tus últimos 3 meses ×1.25)." + nota)
    if esc == "ideal_20":
        return (f"Para consolidar un hábito de ahorro saludable (regla 50/30/20), tu meta este mes "
                f"es S/. {obj:.0f} — el 20% de tu ingreso." + nota)
    if esc == "meta_largo_plazo":
        return (f"Para cumplir tu meta a largo plazo en el plazo que definiste, este mes te conviene "
                f"ahorrar S/. {obj:.0f}." + nota)
    if esc == "incremental":
        return (f"¡Bien! Este mes ahorraste S/. {ahorro:.0f}. Para consolidar el hábito subamos la "
                f"meta poco a poco: el próximo objetivo es S/. {obj:.0f}, sin sacrificios bruscos." + nota)
    if esc == "meta_usuario":
        if ahorro >= obj:
            return (f"¡Excelente! Ya alcanzas tu meta de S/. {obj:.0f} "
                    f"(ahorras S/. {ahorro:.0f}). Mantén tus hábitos y, cuando te sientas "
                    f"cómodo, súbela para seguir creciendo." + nota)
        return f"Trabajemos hacia tu meta de S/. {obj:.0f} (ahorro actual S/. {ahorro:.0f})." + nota
    return f"Trabajemos hacia tu meta de S/. {obj:.0f} (ahorro actual S/. {ahorro:.0f})." + nota


def recommend(user: dict, meta: float | None = None, historial: list | None = None,
             alternativa: str | None = None, candidatos_meta: dict | None = None,
             anti_estatismo: dict | None = None, forzar_escenario: str | None = None,
             forzar_objetivo: float | None = None) -> dict:
    """Plan de ahorro personalizado (rol: especialista en finanzas personales).

    Fija un objetivo DINÁMICO según perfil + ahorro real + elección del usuario en el
    menú de alternativas (ver `_plan_objetivo`) y genera varias estrategias de recorte
    por tiers (gradual, vivienda/alimentos al final). Cada opción reporta su ahorro
    resultante y la clase que el modelo asigna tras el cambio. La opción `recomendada`
    es la más suave que alcanza el objetivo (la más manejable).

    Parámetros multi-mes / anti-estatismo (spec §3 y §5):
      historial       -- user-dicts cronológicos (antiguo -> reciente); prioriza recortar
                          las categorías que MÁS han crecido en el tiempo.
      candidatos_meta -- dict opcional {"escalamiento", "ideal_20", "meta_largo_plazo",
                          "meta_largo_plazo_nombre"} calculado por el llamador (capa
                          Django, que sí conoce metas a largo plazo y el historial en BD).
      alternativa     -- clave del menú elegida por el usuario ("escalamiento" |
                          "ideal_20" | "meta_largo_plazo"); None = automático.
      anti_estatismo  -- {"categoria_objetivo": str} del análisis INMEDIATO ANTERIOR del
                          usuario. Si la nueva categoría líder coincidiría con la del mes
                          pasado, se rota a la siguiente disponible (nunca se repite la
                          misma variable de intervención 2 meses seguidos si los datos
                          lo permiten).
      forzar_escenario / forzar_objetivo -- reproducción fiel de un análisis pasado
                          (usado por ResultadoML.recomputar()): si se pasan, se usa
                          exactamente ese escenario/monto sin re-derivar reglas.
    """
    cls = classify(user)
    ah = ahorro_identidad(user)
    plan = _plan_objetivo(user, cls, meta, alternativa, candidatos_meta,
                          forzar_escenario, forzar_objetivo)
    needed = max(plan["objetivo"] - ah, 0.0)

    prioridad = _crecimiento_por_categoria(historial)
    categoria_previa = (anti_estatismo or {}).get("categoria_objetivo")
    cat_lider = _categoria_lider(prioridad, evitar=categoria_previa)
    cat_tend = cat_lider.replace("GASTO_", "").replace("_", " ").title() if cat_lider else None

    shap_top = shap_explain(user, top=3)

    base = {
        "ahorro_actual": round(ah, 2),
        "clase_actual": cls,
        "escenario": plan["escenario"],
        "meta": round(plan["objetivo"], 2),
        "paso": plan["paso"],
        "advertencia_meta": plan.get("advertencia"),
        "menu_alternativas": plan.get("menu", []),
        "mensaje": _mensaje_especialista(plan, cls),
        "diagnostico_shap": shap_top,
        "shap_puente": _frase_puente_shap(shap_top),
        "categoria_tendencia": cat_tend,        # None si no hay historial con crecimiento
        "categoria_objetivo": cat_lider,         # clave cruda (para persistir anti-estatismo)
        "usa_historial": bool(prioridad),
    }

    if needed <= 1e-6:
        return {**base, "ya_cumple": True, "necesita_recortar": 0.0, "opciones": []}

    opciones, vistos = [], set()
    for strat in _STRATEGIES:
        op = _opcion(user, strat, needed, prioridad, cat_lider)
        if not op["reducciones"]:               # sin recortes aplicables en esos tiers
            continue
        firma = tuple((r["categoria"], r["recorte"]) for r in op["reducciones"])
        if firma in vistos:                     # evita opciones idénticas
            continue
        vistos.add(firma)
        opciones.append(op)

    # Recomendada = la opción más suave que alcanza el objetivo (la más manejable que funciona);
    # si ninguna lo logra solo con recortes realistas, se recomienda la más completa.
    rec_idx = next((i for i, o in enumerate(opciones) if o["alcanza_meta"]),
                   len(opciones) - 1 if opciones else -1)
    for i, o in enumerate(opciones):
        o["recomendada"] = (i == rec_idx)

    return {**base, "ya_cumple": False, "necesita_recortar": round(needed, 2), "opciones": opciones}
