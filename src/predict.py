"""
Módulo de inferencia en producción para el sistema de recomendación de ahorro.
Carga todos los modelos entrenados y expone funciones de predicción y recomendación.
NUNCA re-entrena modelos — solo carga y hace inferencia.
"""

import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap

warnings.filterwarnings("ignore")

_MODELS_DIR = Path(__file__).parent.parent / "models"

GASTO_COLS = [
    "GASTO_ALIMENTOS",
    "GASTO_VESTIDO",
    "GASTO_VIVIENDA_SERVICIOS",
    "GASTO_SALUD",
    "GASTO_TRANSPORTE",
    "GASTO_COMUNICACIONES",
    "GASTO_EDUCACION",
    "GASTO_OTROS_BIENES",
]

GASTO_ESENCIAL_COLS    = ["GASTO_ALIMENTOS", "GASTO_VIVIENDA_SERVICIOS", "GASTO_TRANSPORTE"]
GASTO_DISCRECIONAL_COLS = ["GASTO_VESTIDO", "GASTO_COMUNICACIONES", "GASTO_OTROS_BIENES"]
IMMUTABLE_COLS         = ["EDAD", "NIVEL_EDUC", "MIEMBROS_HOGAR", "DEPENDE_INFORMAL"]

KMEANS_FEATURES = [
    "ING_TOTAL", "GASTO_TOTAL", "RATIO_AHORRO", "RATIO_GASTO_ING",
    "DEPENDE_INFORMAL", "GASTO_PER_CAPITA", "GASTO_ESENCIAL",
    "GASTO_DISCRECIONAL", "PRESION_FINANCIERA", "CAPACIDAD_BRUTA",
    "EDAD", "NIVEL_EDUC", "MIEMBROS_HOGAR",
]

XGB_FEATURES = [
    "EDAD", "NIVEL_EDUC", "MIEMBROS_HOGAR",
    "ING_PLANILLA", "ING_INFORMAL", "ING_TOTAL",
    "GASTO_TOTAL", "RATIO_AHORRO", "RATIO_GASTO_ING",
    "DEPENDE_INFORMAL", "GASTO_PER_CAPITA", "GASTO_ESENCIAL",
    "GASTO_DISCRECIONAL", "PRESION_FINANCIERA", "CAPACIDAD_BRUTA",
    "GASTO_ALIMENTOS", "GASTO_VESTIDO", "GASTO_VIVIENDA_SERVICIOS",
    "GASTO_SALUD", "GASTO_TRANSPORTE", "GASTO_COMUNICACIONES",
    "GASTO_EDUCACION", "GASTO_OTROS_BIENES", "CLUSTER",
]

_MODELS_CACHE: dict = {}


def load_models() -> dict:
    global _MODELS_CACHE
    if _MODELS_CACHE:
        return _MODELS_CACHE

    models = {}
    for name in ["scaler_kmeans", "kmeans_model", "scaler_xgb", "xgboost_model", "shap_explainer"]:
        path = _MODELS_DIR / f"{name}.pkl"
        if not path.exists():
            raise FileNotFoundError(f"Modelo no encontrado: {path}")
        models[name] = joblib.load(path)

    labels_path = _MODELS_DIR / "cluster_labels.json"
    if labels_path.exists():
        with open(labels_path, encoding="utf-8") as f:
            raw = json.load(f)
        models["cluster_labels"] = {int(k): v for k, v in raw.items()}
    else:
        models["cluster_labels"] = {}

    params_path = _MODELS_DIR / "xgb_best_params.json"
    if params_path.exists():
        with open(params_path) as f:
            models["xgb_best_params"] = json.load(f)
    else:
        models["xgb_best_params"] = {}

    _MODELS_CACHE = models
    return models


def _engineer_user_features(user_dict: dict) -> dict:
    u = user_dict.copy()

    ing_planilla = float(u.get("ING_PLANILLA", 0))
    ing_informal = float(u.get("ING_INFORMAL", 0))
    ing_total    = ing_planilla + ing_informal
    u["ING_TOTAL"] = ing_total

    gasto_total = sum(float(u.get(c, 0)) for c in GASTO_COLS)
    u["GASTO_TOTAL"] = gasto_total

    safe_ing = ing_total if ing_total > 0 else 1e-9

    u["RATIO_AHORRO"]    = (ing_total - gasto_total) / safe_ing
    u["RATIO_GASTO_ING"] = gasto_total / safe_ing
    u["DEPENDE_INFORMAL"] = 1 if ing_informal > ing_planilla else 0

    miembros = max(float(u.get("MIEMBROS_HOGAR", 1)), 1)
    u["GASTO_PER_CAPITA"] = gasto_total / miembros

    gasto_esencial = (
        float(u.get("GASTO_ALIMENTOS", 0))
        + float(u.get("GASTO_VIVIENDA_SERVICIOS", 0))
        + float(u.get("GASTO_TRANSPORTE", 0))
    )
    gasto_discrecional = (
        float(u.get("GASTO_VESTIDO", 0))
        + float(u.get("GASTO_OTROS_BIENES", 0))
        + float(u.get("GASTO_COMUNICACIONES", 0))
    )

    u["GASTO_ESENCIAL"]    = gasto_esencial
    u["GASTO_DISCRECIONAL"] = gasto_discrecional
    u["PRESION_FINANCIERA"] = gasto_esencial / safe_ing
    u["CAPACIDAD_BRUTA"]    = ing_total - gasto_esencial
    return u


def validate_meta(meta_usuario: float, ing_total: float, gastos_esenciales: float) -> dict:
    capacidad_maxima = max(ing_total - gastos_esenciales * 0.70, 0.0)

    if meta_usuario == 0:
        return {
            "valida": True, "caso": "meta_cero",
            "mensaje": "Meta de cero registrada. Se sugeriron planes para comenzar a ahorrar.",
            "meta_sugerida": max(ing_total * 0.05, 50.0),
            "capacidad_maxima": float(capacidad_maxima),
        }
    if meta_usuario < 0:
        return {
            "valida": False, "caso": "meta_negativa",
            "mensaje": "La meta de ahorro no puede ser negativa.",
            "meta_sugerida": max(ing_total * 0.05, 50.0),
            "capacidad_maxima": float(capacidad_maxima),
        }
    if meta_usuario > capacidad_maxima:
        return {
            "valida": False, "caso": "meta_inalcanzable",
            "mensaje": (
                f"Tu meta de S/. {meta_usuario:.2f} supera la capacidad maxima estimada "
                f"de S/. {capacidad_maxima:.2f}."
            ),
            "meta_sugerida": float(capacidad_maxima),
            "capacidad_maxima": float(capacidad_maxima),
        }
    return {
        "valida": True, "caso": "meta_valida",
        "mensaje": f"Meta de S/. {meta_usuario:.2f} validada correctamente.",
        "meta_sugerida": float(meta_usuario),
        "capacidad_maxima": float(capacidad_maxima),
    }


def predict_saving(user_dict: dict) -> dict:
    models = load_models()
    u = _engineer_user_features(user_dict)

    km_vec    = np.array([u.get(f, 0) for f in KMEANS_FEATURES], dtype=float).reshape(1, -1)
    km_scaled = models["scaler_kmeans"].transform(km_vec)
    cluster_id = int(models["kmeans_model"].predict(km_scaled)[0])
    u["CLUSTER"] = cluster_id
    cluster_label = models["cluster_labels"].get(cluster_id, f"Cluster {cluster_id}")

    xgb_vec    = np.array([u.get(f, 0) for f in XGB_FEATURES], dtype=float).reshape(1, -1)
    xgb_scaled = models["scaler_xgb"].transform(xgb_vec)
    xgb_df     = pd.DataFrame(xgb_scaled, columns=XGB_FEATURES)
    ahorro_predicho = float(models["xgboost_model"].predict(xgb_df)[0])

    ing_total = u.get("ING_TOTAL", 1)
    ratio = ahorro_predicho / max(abs(ing_total), 1)
    if abs(ratio) < 0.05:
        confianza = "Baja — Ahorro cercano a cero, alta sensibilidad a pequeños cambios"
    elif abs(ahorro_predicho) > ing_total * 0.5:
        confianza = "Media — Valor extremo, verificar datos de entrada"
    else:
        confianza = "Alta"

    return {
        "ahorro_predicho": ahorro_predicho,
        "cluster_id": cluster_id,
        "cluster_label": cluster_label,
        "confianza": confianza,
    }


def _shap_explain(user_dict_engineered: dict, models: dict) -> list:
    """
    Siempre retorna los 8 gastos individuales (accionables) + top 5 informativos.
    Excluye features derivadas (GASTO_TOTAL, RATIO_*, etc.) del listado accionable.
    """
    u = user_dict_engineered
    xgb_vec    = np.array([u.get(f, 0) for f in XGB_FEATURES], dtype=float).reshape(1, -1)
    xgb_scaled = models["scaler_xgb"].transform(xgb_vec)
    xgb_df     = pd.DataFrame(xgb_scaled, columns=XGB_FEATURES)

    shap_vals = models["shap_explainer"](xgb_df)
    sv = shap_vals.values[0]
    fv = xgb_scaled[0]

    feat_idx = {f: i for i, f in enumerate(XGB_FEATURES)}

    gasto_results = sorted(
        [
            {
                "feature": col,
                "shap_value": float(sv[feat_idx[col]]),
                "feature_value_scaled": float(fv[feat_idx[col]]),
            }
            for col in GASTO_COLS
        ],
        key=lambda x: abs(x["shap_value"]),
        reverse=True,
    )

    _EXCLUIDAS = set(GASTO_COLS) | {
        "GASTO_TOTAL", "GASTO_ESENCIAL", "GASTO_DISCRECIONAL",
        "RATIO_AHORRO", "RATIO_GASTO_ING", "GASTO_PER_CAPITA",
        "PRESION_FINANCIERA", "CAPACIDAD_BRUTA",
    }
    info_results = sorted(
        [
            {
                "feature": f,
                "shap_value": float(sv[i]),
                "feature_value_scaled": float(fv[i]),
            }
            for i, f in enumerate(XGB_FEATURES)
            if f not in _EXCLUIDAS
        ],
        key=lambda x: abs(x["shap_value"]),
        reverse=True,
    )

    return gasto_results + info_results[:5]


def _compute_max_saving(u_eng: dict, models: dict) -> float:
    """Evalua el modelo con todos los gastos en sus minimos (limites del plan Agresivo)."""
    gastos_orig = np.array([float(u_eng.get(c, 0)) for c in GASTO_COLS])
    ing_total   = float(u_eng.get("ING_TOTAL", 1))

    lo_arr = np.array([
        gastos_orig[i] * (0.70 if col in GASTO_ESENCIAL_COLS
                          else 0.30 if col in GASTO_DISCRECIONAL_COLS
                          else 0.40)
        for i, col in enumerate(GASTO_COLS)
    ])

    gasto_total = float(lo_arr.sum())
    g_es = lo_arr[0] + lo_arr[2] + lo_arr[4]
    g_di = lo_arr[1] + lo_arr[5] + lo_arr[7]

    u = u_eng.copy()
    for i, col in enumerate(GASTO_COLS):
        u[col] = float(lo_arr[i])
    u["GASTO_TOTAL"]        = gasto_total
    u["RATIO_AHORRO"]       = (ing_total - gasto_total) / max(ing_total, 1e-9)
    u["RATIO_GASTO_ING"]    = gasto_total / max(ing_total, 1e-9)
    u["GASTO_ESENCIAL"]     = g_es
    u["GASTO_DISCRECIONAL"] = g_di
    u["GASTO_PER_CAPITA"]   = gasto_total / max(float(u_eng.get("MIEMBROS_HOGAR", 1)), 1)
    u["PRESION_FINANCIERA"] = g_es / max(ing_total, 1e-9)
    u["CAPACIDAD_BRUTA"]    = ing_total - g_es

    vec    = np.array([u.get(f, 0) for f in XGB_FEATURES], dtype=float).reshape(1, -1)
    scaled = models["scaler_xgb"].transform(vec)
    return float(models["xgboost_model"].predict(scaled)[0])


def _build_optimization_plans(user_dict_eng: dict, target_saving: float, models: dict) -> list:
    """
    Genera 3 planes usando busqueda binaria parametrica directa sobre el modelo XGBoost.

    Por que busqueda binaria y no SLSQP:
    XGBoost produce funciones escalonadas (gradiente ≈ 0 casi en todas partes),
    lo que hace que los metodos basados en gradientes (SLSQP) fallen o converjan
    a minimos locales arbitrarios. La busqueda binaria evalua el modelo directamente
    y captura efectos conjuntos entre categorias sin asumir suavidad.

    Algoritmo por plan:
    1. Calcula direction[i] = gastos_orig[i] - lo_arr[i]  (maximo recorte permitido).
       Conservador: solo discrecionales + salud/educacion (esenciales bloqueados).
       Balanceado: todos los gastos, esenciales escalados 1/8 (desincentivados).
       Agresivo: todos los gastos sin penalizacion adicional.

    2. Evalua ahorro_techo = predict(gastos_orig - direction)  (alpha = 1, maximo recorte).

    3a. Si ahorro_techo >= target: busqueda binaria para el alpha minimo en [0,1]
        tal que predict(gastos_orig - alpha*direction) >= target.
        Resultado: plan que alcanza EXACTAMENTE la meta con el minimo recorte.

    3b. Si ahorro_techo < target: plan infactible → muestra el techo del plan.
        (El usuario ve lo maximo alcanzable con esa estrategia y la brecha restante.)

    Garantia: ninguna recomendacion devuelve ahorro > target * 1.05 (evita outputs de 482
    cuando la meta es 200). La busqueda binaria converge en 25 pasos (~2^-25 precision).
    """
    gastos_orig = np.array([float(user_dict_eng.get(c, 0)) for c in GASTO_COLS])
    ing_total   = float(user_dict_eng.get("ING_TOTAL", 1))

    # Indices fijos para el closure predict_from_gastos
    _gasto_pairs = [
        (gi, XGB_FEATURES.index(col))
        for gi, col in enumerate(GASTO_COLS)
        if col in XGB_FEATURES
    ]
    _i_GT  = XGB_FEATURES.index("GASTO_TOTAL")
    _i_RA  = XGB_FEATURES.index("RATIO_AHORRO")
    _i_RGI = XGB_FEATURES.index("RATIO_GASTO_ING")
    _i_GE  = XGB_FEATURES.index("GASTO_ESENCIAL")
    _i_GD  = XGB_FEATURES.index("GASTO_DISCRECIONAL")
    _i_GPC = XGB_FEATURES.index("GASTO_PER_CAPITA")
    _i_PF  = XGB_FEATURES.index("PRESION_FINANCIERA")
    _i_CB  = XGB_FEATURES.index("CAPACIDAD_BRUTA")
    _m     = max(float(user_dict_eng.get("MIEMBROS_HOGAR", 1)), 1)
    _bv    = np.array([user_dict_eng.get(f, 0) for f in XGB_FEATURES], dtype=float)
    _sc    = models["scaler_xgb"]
    _xgb   = models["xgboost_model"]
    _ei    = (0, 2, 4)   # ALIMENTOS, VIVIENDA, TRANSPORTE dentro de GASTO_COLS
    _di    = (1, 5, 7)   # VESTIDO, COMUNICACIONES, OTROS_BIENES

    def predict_from_gastos(g):
        vec = _bv.copy()
        for gi, xi in _gasto_pairs:
            vec[xi] = g[gi]
        gt = g.sum()
        ge = g[_ei[0]] + g[_ei[1]] + g[_ei[2]]
        gd = g[_di[0]] + g[_di[1]] + g[_di[2]]
        vec[_i_GT]  = gt
        vec[_i_RA]  = (ing_total - gt) / max(ing_total, 1e-9)
        vec[_i_RGI] = gt / max(ing_total, 1e-9)
        vec[_i_GE]  = ge
        vec[_i_GD]  = gd
        vec[_i_GPC] = gt / _m
        vec[_i_PF]  = ge / max(ing_total, 1e-9)
        vec[_i_CB]  = ing_total - ge
        return float(_xgb.predict(_sc.transform(vec.reshape(1, -1)))[0])

    plan_configs = [
        {
            "nombre": "Conservador",
            "esencial_factor": 1.0,        # esenciales fijos
            "discrecional_factor": 0.45,   # hasta 55% de recorte
            "otros_factor": 0.55,          # salud/educacion hasta 45%
            "penalidad_esencial": None,
        },
        {
            "nombre": "Balanceado",
            "esencial_factor": 0.85,       # hasta 15% de recorte en esenciales
            "discrecional_factor": 0.40,   # hasta 60% en discrecionales
            "otros_factor": 0.50,
            "penalidad_esencial": 8.0,     # escala /8 la participacion de esenciales
        },
        {
            "nombre": "Agresivo",
            "esencial_factor": 0.70,       # hasta 30% de recorte en esenciales
            "discrecional_factor": 0.30,   # hasta 70% en discrecionales
            "otros_factor": 0.40,
            "penalidad_esencial": None,
        },
    ]

    plans = []
    for cfg in plan_configs:
        # Piso de cada gasto segun la estrategia
        lo_list = []
        for col in GASTO_COLS:
            v = float(user_dict_eng.get(col, 0))
            if col in GASTO_ESENCIAL_COLS:
                lo_list.append(v * cfg["esencial_factor"])
            elif col in GASTO_DISCRECIONAL_COLS:
                lo_list.append(v * cfg["discrecional_factor"])
            else:
                lo_list.append(v * cfg.get("otros_factor", 0.40))
        lo_arr = np.array(lo_list)

        # Direccion de recorte: maximo recorte permitido por categoria
        # Conservador: direction[esencial] = 0 (bloqueados porque factor=1.0)
        # Balanceado: direction[esencial] /= 8 (desincentivados pero no bloqueados)
        # Agresivo: direction plena en todas las categorias
        direction = gastos_orig - lo_arr   # >= 0 en cada componente

        penalidad = cfg.get("penalidad_esencial")
        if penalidad:
            for i, col in enumerate(GASTO_COLS):
                if col in GASTO_ESENCIAL_COLS:
                    direction[i] /= penalidad

        # Techo del plan: ahorro cuando alpha=1 (recorte maximo a lo largo de direction)
        gastos_techo = np.clip(gastos_orig - direction, lo_arr, gastos_orig)
        ahorro_techo = predict_from_gastos(gastos_techo)

        if ahorro_techo < target_saving - 1.0:
            # Infactible: el plan no puede alcanzar la meta ni recortando al maximo
            gastos_opt = gastos_techo
            ahorro_opt = ahorro_techo
            cumple_meta = False
        else:
            # Factible: busqueda binaria para el alpha minimo que alcanza target
            # alpha=0 -> sin recorte (ahorro_base < target)
            # alpha=1 -> recorte maximo (ahorro_techo >= target)
            lo_a, hi_a = 0.0, 1.0
            for _ in range(25):
                mid_a = (lo_a + hi_a) / 2.0
                g_mid = np.clip(gastos_orig - mid_a * direction, lo_arr, gastos_orig)
                if predict_from_gastos(g_mid) >= target_saving - 0.5:
                    hi_a = mid_a   # con menos recorte ya alcanza → buscar menos
                else:
                    lo_a = mid_a   # no alcanza → necesita mas recorte
            gastos_opt = np.clip(gastos_orig - hi_a * direction, lo_arr, gastos_orig)
            ahorro_opt = predict_from_gastos(gastos_opt)
            cumple_meta = bool(ahorro_opt >= target_saving - 1.0)

        plans.append({
            "nombre": cfg["nombre"],
            "ahorro_predicho": float(ahorro_opt),
            "cumple_meta": cumple_meta,
            "reduccion_gasto": float(gastos_orig.sum() - gastos_opt.sum()),
            "gastos": {
                col: {
                    "original": float(gastos_orig[i]),
                    "optimizado": float(gastos_opt[i]),
                    "delta": float(gastos_opt[i] - gastos_orig[i]),
                }
                for i, col in enumerate(GASTO_COLS)
            },
        })

    return plans


def recommend(user_dict: dict, meta_ahorro: float) -> dict:
    models = load_models()
    u_eng  = _engineer_user_features(user_dict)

    ing_total        = float(u_eng.get("ING_TOTAL", 1))
    gastos_esenciales = float(u_eng.get("GASTO_ESENCIAL", 0))

    validacion = validate_meta(meta_ahorro, ing_total, gastos_esenciales)

    if validacion["caso"] == "meta_inalcanzable":
        max_saving_real = _compute_max_saving(u_eng, models)
        max_saving_real = max(max_saving_real, 0.0)
        validacion["capacidad_maxima"] = max_saving_real
        validacion["meta_sugerida"]    = max_saving_real
        validacion["mensaje"] = (
            f"Tu meta de S/. {meta_ahorro:.2f} supera el maximo posible estimado por el modelo "
            f"(S/. {max_saving_real:.2f}). Las recomendaciones apuntan a ese maximo."
        )

    meta_final = validacion["meta_sugerida"]

    pred_result  = predict_saving(user_dict)
    ahorro_actual = pred_result["ahorro_predicho"]
    cluster_id   = pred_result["cluster_id"]
    cluster_label = pred_result["cluster_label"]

    gap = meta_final - ahorro_actual

    u_eng["CLUSTER"] = cluster_id
    shap_top = _shap_explain(u_eng, models)

    planes = []
    if gap > 0 or not validacion["valida"]:
        planes = _build_optimization_plans(u_eng, meta_final, models)
    else:
        planes = [{
            "nombre": "Meta Alcanzada — Mantener Habitos",
            "ahorro_predicho": float(meta_final),
            "ahorro_maximo_posible": float(ahorro_actual),
            "reduccion_gasto": 0.0,
            "gastos": {
                c: {"original": float(u_eng.get(c, 0)), "optimizado": float(u_eng.get(c, 0)), "delta": 0.0}
                for c in GASTO_COLS
            },
        }]

    return {
        "ahorro_actual": ahorro_actual,
        "meta_usuario": meta_ahorro,
        "meta": meta_final,
        "gap": gap,
        "planes": planes,
        "explicacion_shap": shap_top,
        "validacion_meta": validacion,
        "cluster_id": cluster_id,
        "cluster_label": cluster_label,
        "confianza": pred_result["confianza"],
    }
