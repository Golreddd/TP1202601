# -*- coding: utf-8 -*-
"""
Inferencia de SmartSave — clasificación + SHAP + recomendaciones (counterfactual).

Carga los artefactos entrenados (NUNCA re-entrena) y expone:
  - classify(user)        -> Déficit (0) / Ahorra (1) + probabilidad (modelo honesto).
  - ahorro_identidad(user)-> ahorro real exacto = ingreso − gasto.
  - shap_explain(user)    -> variables que más empujan la clasificación (diagnóstico).
  - recommend(user, meta) -> VARIAS opciones de recomendación para elegir.

Diseño realista (sin fuga): el clasificador NO recibe los gastos discrecionales
(OTROS_BIENES, vestido, comunicaciones) ni montos crudos de gasto, así que el
counterfactual NO se hace moviendo variables dentro del modelo. Se opera sobre el
PRESUPUESTO REAL con la identidad contable exacta (cada sol recortado = un sol más de
ahorro), con recortes acotados por categoría (compresibilidad realista: más en gastos
hormiga, menos en lo esencial), y cada opción se re-clasifica con
el modelo para validarla.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .preprocessing import (CLASS_LABELS, GASTO_COLS,
                            ahorro_identidad, build_feature_row, gasto_total, ing_total)

_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
_CACHE: dict = {}

MAX_CUT_FRAC = 0.40  # fallback si una categoría no está en MAX_CUT_BY_CAT

# Compresibilidad realista POR CATEGORÍA: cuánto se puede recortar como máximo de cada
# gasto en un mes. NO es plano: lo esencial tiene piso de subsistencia (se recorta poco);
# los gastos hormiga / discrecionales se pueden recortar mucho más. Corroborado con el
# dataset: los hogares que AHORRAN gastan menos en todas las categorías y la mayor brecha
# es Otros Bienes (ahorradores ~0.41 vs déficit ~1.03 del ingreso). Valores ajustables.
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
_PASO_AHORRADOR      = 0.10   # perfil con hábito: sube la meta ~10% del ingreso
_PASO_NO_AHORRADOR   = 0.05   # perfil sin hábito: pasos más suaves (~5%)
_UMBRAL_DEFICIT_BAJO = 0.10   # déficit "bajo" si es ≤10% del ingreso
_AHORRO_MINIMO_FRAC  = 0.03   # primer ahorro mínimo ~3% del ingreso
_PASO_MIN            = 20.0   # paso mínimo en soles para que la meta tenga sentido


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
    models = load_models()
    proba = float(models["model"].predict_proba(_vector(user, models))[0, 1])
    clase = int(proba >= 0.5)
    margen = abs(proba - 0.5)
    confianza = "Alta" if margen > 0.30 else ("Media" if margen > 0.15 else "Baja")
    return {
        "clase": clase,
        "label": CLASS_LABELS[clase],
        "probabilidad_ahorra": proba,
        "probabilidad_deficit": 1.0 - proba,
        "confianza": confianza,
    }


def shap_explain(user: dict, top: int | None = None) -> list:
    """Contribuciones SHAP hacia 'Ahorra'. shap < 0 empuja hacia Déficit (prioridad de acción)."""
    models = load_models()
    feats = models["features"]
    sv = models["shap"](_vector(user, models))
    vals = np.asarray(sv.values).reshape(-1)
    out = sorted(
        [{"feature": f, "shap_value": float(vals[i])} for i, f in enumerate(feats)],
        key=lambda d: abs(d["shap_value"]), reverse=True,
    )
    return out if top is None else out[:top]


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


def _opcion(user: dict, strat: dict, needed: float, prioridad: dict | None = None) -> dict:
    opt, faltante = _allocate(user, strat["tiers"], needed, prioridad)
    user_opt = {**user, **opt}
    ahorro_res = ing_total(user) - sum(opt[c] for c in GASTO_COLS)
    clase_opt = classify(user_opt)
    # Solo se marca la categoría que MÁS creció (coincide con la tarjeta de tendencia);
    # la asignación sí prioriza todas las que crecieron, pero el badge resalta la líder.
    cat_lider = max(prioridad, key=prioridad.get) if prioridad else None
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
                # True si es la categoría que más viene creciendo en el historial (multi-mes).
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


def _plan_objetivo(user: dict, cls: dict, meta: float | None = None) -> dict:
    """Define el objetivo de ahorro DINÁMICO y personalizado (rol de especialista).

    No es estático: depende del ingreso, del perfil del modelo (con/sin hábito) y del
    ahorro real del mes. Reglas:
      • Déficit alto  -> meta = volver a 0 (equilibrio) antes de pensar en ahorrar.
      • Déficit bajo  -> volver a 0 y, además, guardar una mínima parte (≈3% del ingreso).
      • Ya ahorra     -> subir la meta poco a poco (paso = % del ingreso según perfil).
      • Meta del user -> se respeta si la define.
    Nunca propone subir ingresos ni cambiar estrato/miembros.
    """
    ing = ing_total(user)
    ahorro = ahorro_identidad(user)
    es_perfil_ahorrador = cls["clase"] == 1
    paso = max(round(ing * (_PASO_AHORRADOR if es_perfil_ahorrador else _PASO_NO_AHORRADOR)), _PASO_MIN)
    ahorro_min = max(round(ing * _AHORRO_MINIMO_FRAC), _PASO_MIN)

    if meta is not None and float(meta) > 0:
        escenario, objetivo = "meta_usuario", float(meta)
    elif ahorro < 0:
        if abs(ahorro) / max(ing, 1.0) <= _UMBRAL_DEFICIT_BAJO:
            escenario, objetivo = "deficit_bajo", float(ahorro_min)
        else:
            escenario, objetivo = "deficit", 0.0
    else:
        # ya ahorra: subir poco a poco con un paso GRADUAL acotado por el margen discrecional
        # (tier 1), para que sea alcanzable SIN tocar lo flexible/esencial (sin sacrificios bruscos).
        cap_disc = sum(float(user.get(c, 0)) * cut_frac(c) for c in _TIER_HORMIGA)
        paso = max(round(min(paso, 0.5 * cap_disc)), _PASO_MIN)
        escenario, objetivo = "ya_ahorra", round(ahorro + paso, 2)

    return {"escenario": escenario, "objetivo": objetivo, "paso": paso,
            "ahorro": ahorro, "ing": ing}


def _mensaje_especialista(plan: dict, cls: dict) -> str:
    """Mensaje en rol de especialista en finanzas personales, según escenario + perfil."""
    ahorro, ing, esc = plan["ahorro"], plan["ing"], plan["escenario"]
    obj, paso = plan["objetivo"], plan["paso"]
    # Nota por discrepancia perfil (modelo) vs realidad contable del mes.
    nota = ""
    if cls["clase"] == 1 and ahorro < 0:
        nota = (" Tu perfil tiende a ahorrar, así que este déficit parece puntual: "
                "recuperarlo debería ser manejable.")
    elif cls["clase"] == 0 and ahorro >= 0:
        nota = (" Aunque tu perfil estructural tiende al déficit, este mes ahorraste: "
                "mantener el hábito ya es un logro, vamos paso a paso.")

    if esc == "deficit":
        return (f"Este mes gastaste S/. {abs(ahorro):.0f} más de lo que ingresó. La prioridad #1 "
                f"es volver al equilibrio (ahorro 0) antes de pensar en guardar." + nota)
    if esc == "deficit_bajo":
        return (f"Tu déficit (S/. {abs(ahorro):.0f}) es bajo frente a tu ingreso "
                f"({abs(ahorro) / max(ing, 1.0) * 100:.0f}%). Volvamos a 0 y, ya que estás cerca, "
                f"intentemos guardar al menos S/. {obj:.0f} — un primer ahorro pequeño pero real." + nota)
    if esc == "ya_ahorra":
        return (f"¡Bien! Este mes ahorraste S/. {ahorro:.0f}. Para consolidar el hábito subamos la "
                f"meta poco a poco: el próximo objetivo es S/. {obj:.0f} (+S/. {paso:.0f}), sin "
                f"sacrificios bruscos." + nota)
    if ahorro >= obj:
        return (f"¡Excelente! Ya alcanzas tu meta de S/. {obj:.0f} "
                f"(ahorras S/. {ahorro:.0f}). Mantén tus hábitos y, cuando te sientas "
                f"cómodo, súbela para seguir creciendo." + nota)
    return f"Trabajemos hacia tu meta de S/. {obj:.0f} (ahorro actual S/. {ahorro:.0f})." + nota


def recommend(user: dict, meta: float | None = None, historial: list | None = None) -> dict:
    """Plan de ahorro personalizado (rol: especialista en finanzas personales).

    Fija un objetivo DINÁMICO según perfil + ahorro real (ver `_plan_objetivo`) y genera
    varias estrategias de recorte por tiers (gradual, vivienda/alimentos al final). Cada
    opción reporta su ahorro resultante y la clase que el modelo asigna tras el cambio. La
    opción `recomendada` es la más suave que alcanza el objetivo (la más manejable).

    Si se pasa `historial` (lista de user-dicts de meses anteriores, cronológico), el
    counterfactual deja de mirar SOLO el mes actual: prioriza recortar las categorías que
    MÁS han crecido en el tiempo (respetando topes y orden de tiers). Esto implementa el
    "modo seguimiento" del spec sin tocar el clasificador.
    """
    cls = classify(user)
    ah = ahorro_identidad(user)
    plan = _plan_objetivo(user, cls, meta)
    needed = max(plan["objetivo"] - ah, 0.0)
    prioridad = _crecimiento_por_categoria(historial)

    # Categoría líder de crecimiento (humanizada), para mensajes/UI.
    cat_tend = None
    if prioridad:
        _k = max(prioridad, key=prioridad.get)
        cat_tend = _k.replace("GASTO_", "").replace("_", " ").title()

    base = {
        "ahorro_actual": round(ah, 2),
        "clase_actual": cls,
        "escenario": plan["escenario"],
        "meta": round(plan["objetivo"], 2),
        "paso": plan["paso"],
        "mensaje": _mensaje_especialista(plan, cls),
        "diagnostico_shap": shap_explain(user, top=3),
        "categoria_tendencia": cat_tend,        # None si no hay historial con crecimiento
        "usa_historial": bool(prioridad),
    }

    if needed <= 1e-6:
        return {**base, "ya_cumple": True, "necesita_recortar": 0.0, "opciones": []}

    opciones, vistos = [], set()
    for strat in _STRATEGIES:
        op = _opcion(user, strat, needed, prioridad)
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
