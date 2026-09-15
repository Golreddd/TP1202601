# -*- coding: utf-8 -*-
"""
Estudio de ablacion por bloques de variables y contraste con variables de fuga
(observacion 3). Genera la Tabla IV del paper.

Todas las configuraciones usan el DATASET LIMPIO (9,527 registros), la misma
particion estratificada 80/20 (train/valid) con semilla 42 de train.py y los
hiperparametros de models/xgb_best_params.json. Solo cambia el subconjunto de
columnas.

Bloques (incrementales, cada uno anade variables al anterior):
    M1  Solo demograficas                        ( 3 features)
    M2  + tipo de ingreso                        ( 7 features)
    M3  + ratios financieros                     (14 features)
    M4  Todas las variables finales              (19 features = features.json)

M4 no se reentrena: carga el modelo de produccion (models/xgb_clf_model.pkl), de
modo que sus metricas coinciden exactamente con metrics.json y con el paper.
    Contraste con variables de fuga      (30 features: incluye ING_TOTAL,
        CAPACIDAD_BRUTA, GASTO_TOTAL y los ocho montos crudos de gasto)

M4 debe reproducir metrics.json. El contraste debe dispararse por encima de 0.98:
esa distancia es la evidencia de que las 19 features no reconstruyen la identidad
contable ingreso - gasto.

Uso (desde la raiz del repo):
    python -m src.ablation
    python -m src.ablation --dataset ruta/al/limpio.csv

Salida: tabla por consola y models/ablation.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import (accuracy_score, f1_score, matthews_corrcoef,
                             precision_score, recall_score, roc_auc_score)
from sklearn.preprocessing import StandardScaler

from .preprocessing import (GASTO_COLS, add_features, binary_target,
                            clean_dataset, referential_features)
from .train import _DATASET, _MODELS, _ROOT, _clf, _split

_CLEAN_DEFAULT = _ROOT / "dataset_final_limpio.csv"

DEMOGRAFICAS = ["NIVEL_EDUC", "MIEMBROS_HOGAR", "ESTRATO_SOC"]
TIPO_INGRESO = ["TIPO_FORMAL", "TIPO_INFORMAL", "TIPO_MIXTO", "DEPENDE_INFORMAL"]
RATIOS = ["PRESION_FINANCIERA", "COMMIT_PER_CAPITA", "GASTO_ALIMENTOS_R",
          "GASTO_VIVIENDA_SERVICIOS_R", "GASTO_TRANSPORTE_R", "GASTO_SALUD_R",
          "GASTO_EDUCACION_R"]
MONTOS_INGRESO = ["ING_PLANILLA", "ING_INFORMAL", "LOG_ING", "ING_PER_CAPITA",
                  "INFORMAL_SHARE"]
# Variables excluidas por fuga: reconstruyen o casi reconstruyen ingreso - gasto
FUGA = ["ING_TOTAL", "CAPACIDAD_BRUTA", "GASTO_TOTAL"] + list(GASTO_COLS)


def _load_clean(dataset: str | None, iqr_factor: float) -> pd.DataFrame:
    path = Path(dataset) if dataset else _CLEAN_DEFAULT
    if path.exists():
        df = pd.read_csv(path)
        print(f"Dataset limpio: {path.name} ({len(df)} registros)")
    else:
        df = clean_dataset(str(_DATASET), iqr_factor=iqr_factor)
        print(f"Dataset limpio reconstruido desde {_DATASET.name} ({len(df)} registros)")
    return add_features(df)


def _evaluar(df, feats, y, tr, va, hp, produccion=False) -> dict:
    """Evalua sobre validacion. Si produccion=True carga el modelo guardado."""
    faltan = [c for c in feats if c not in df.columns]
    if faltan:
        raise KeyError(f"Columnas ausentes en el dataset: {faltan}")
    X = df[feats].astype(float).values
    if produccion and (_MODELS / "xgb_clf_model.pkl").exists():
        sc = joblib.load(_MODELS / "scaler.pkl")
        m = joblib.load(_MODELS / "xgb_clf_model.pkl")
        Xs = sc.transform(X)
    else:
        sc = StandardScaler().fit(X[tr])
        Xs = sc.transform(X)
        m = _clf(early_stopping=True, **hp)
        m.fit(Xs[tr], y[tr], eval_set=[(Xs[va], y[va])], verbose=False)
    pred = m.predict(Xs[va])
    prob = m.predict_proba(Xs[va])[:, 1]
    return {
        "k": len(feats),
        "accuracy": accuracy_score(y[va], pred),
        "precision": precision_score(y[va], pred, zero_division=0),
        "recall": recall_score(y[va], pred, zero_division=0),
        "f1": f1_score(y[va], pred, zero_division=0),
        "roc_auc": roc_auc_score(y[va], prob),
        "mcc": matthews_corrcoef(y[va], pred),
    }


def main(dataset=None, iqr_factor=2.5):
    df = _load_clean(dataset, iqr_factor)
    y = binary_target(df)
    tr, va = _split(y)

    with open(_MODELS / "features.json", encoding="utf-8") as f:
        finales = json.load(f)
    assert finales == referential_features(df), \
        "features.json no coincide con referential_features()"

    with open(_MODELS / "xgb_best_params.json", encoding="utf-8") as f:
        best = json.load(f)
    hp = {k: v for k, v in best.items()
          if k not in ("objective", "early_stopping_rounds",
                       "n_estimators_max", "n_arboles_usados")}
    hp["n_estimators"] = best.get("n_estimators_max", 1500)

    bloques = {
        "M1 Solo demograficas": (DEMOGRAFICAS, False),
        "M2 + tipo de ingreso": (DEMOGRAFICAS + TIPO_INGRESO, False),
        "M3 + ratios financieros": (DEMOGRAFICAS + TIPO_INGRESO + RATIOS, False),
        "M4 Todas las variables finales": (finales, True),   # modelo de produccion
        "Contraste con variables de fuga": (finales + FUGA, False),
    }
    esperado = set(DEMOGRAFICAS + TIPO_INGRESO + RATIOS + MONTOS_INGRESO)
    assert esperado == set(finales), \
        f"Los bloques no suman las 19 features finales: {esperado ^ set(finales)}"

    print(f"\nConjunto de validacion: n = {len(va)}\n")
    print(f"{'Bloque de variables':36s} {'k':>3} {'Acc':>6} {'Prec':>6} "
          f"{'Rec':>6} {'F1':>6} {'AUC':>6} {'MCC':>7}")
    print("-" * 82)

    rep = {"n_valid": int(len(va)), "bloques": {}}
    for nombre, (feats, prod) in bloques.items():
        r = _evaluar(df, feats, y, tr, va, hp, produccion=prod)
        rep["bloques"][nombre] = {k: (int(v) if k == "k" else float(v))
                                  for k, v in r.items()}
        print(f"{nombre:36s} {r['k']:3d} {r['accuracy']:6.3f} {r['precision']:6.3f} "
              f"{r['recall']:6.3f} {r['f1']:6.3f} {r['roc_auc']:6.3f} {r['mcc']:+7.3f}")

    # baseline de clase mayoritaria, como referencia inferior
    mayoritaria = max((y[va] == 0).mean(), (y[va] == 1).mean())
    rep["baseline_clase_mayoritaria"] = float(mayoritaria)
    print("-" * 82)
    print(f"{'Baseline clase mayoritaria':36s} {'—':>3} {mayoritaria:6.3f}")

    m4 = rep["bloques"]["M4 Todas las variables finales"]
    ct = rep["bloques"]["Contraste con variables de fuga"]
    brecha = ct["accuracy"] - m4["accuracy"]
    rep["brecha_accuracy_contraste"] = float(brecha)
    print(f"\nBrecha de Accuracy entre el contraste con fuga y el modelo final: "
          f"{brecha:.3f} ({brecha * 100:.1f} puntos porcentuales)")

    # verificacion contra las metricas publicadas
    ref = _MODELS / "metrics.json"
    if ref.exists():
        with open(ref, encoding="utf-8") as f:
            pub = json.load(f)["valid"]
        print(f"Verificacion M4 vs metrics.json -> accuracy {m4['accuracy']:.4f} "
              f"(publicado {pub['accuracy']:.4f}), auc {m4['roc_auc']:.4f} "
              f"(publicado {pub['roc_auc']:.4f})")

    salida = _MODELS / "ablation.json"
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"\nResultados guardados en {salida}\n")
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=str, default=None,
                    help="CSV limpio (por defecto dataset_final_limpio.csv en la raiz)")
    ap.add_argument("--iqr-factor", type=float, default=2.5)
    a = ap.parse_args()
    main(dataset=a.dataset, iqr_factor=a.iqr_factor)
