# -*- coding: utf-8 -*-
"""
Umbral de decisión específico para el segmento de menor ingreso (observación del revisor).

1. El segmento se define con la mediana del ingreso del ENTRENAMIENTO (no de la validación).
2. El umbral se elige SOLO con predicciones fuera de muestra del entrenamiento (CV 5-fold,
   mismos hiperparámetros y número de árboles del modelo de producción), maximizando la
   accuracy balanceada (índice de Youden) en el segmento de menor ingreso.
3. Se aplica una sola vez sobre la validación (20 %) y se compara con el umbral común 0.5.

Uso:   python -m src.research.umbral_segmento
Salida: models/investigacion/umbral_segmento.json
"""
import json

import joblib
import numpy as np
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

from ..pipeline.train import RANDOM_STATE, _INVESTIGACION, _MODELS, _clf, _split, load_xy


def _m(y, p):
    tn, fp, fn, tp = confusion_matrix(y, p, labels=[0, 1]).ravel()
    return {"n": int(len(y)), "f1": float(f1_score(y, p)), "fnr": float(fn / (fn + tp)),
            "fpr": float(fp / (fp + tn)), "bal_acc": float((tp / (tp + fn) + tn / (tn + fp)) / 2),
            "acc": float((tp + tn) / len(y))}


def main():
    df, feats, X, y = load_xy()
    tr, va = _split(y)
    hp = json.load(open(_MODELS / "xgb_best_params.json", encoding="utf-8"))
    n_trees = hp["n_arboles_usados"]
    hp = {k: v for k, v in hp.items() if k not in ("objective", "early_stopping_rounds", "early_stopping_sobre",
                                                   "n_estimators_max", "n_arboles_usados")}
    ing = df["ING_TOTAL"].values
    med = float(np.median(ing[tr]))

    # predicciones fuera de muestra en el entrenamiento
    oof = np.zeros(len(tr))
    for a, b in StratifiedKFold(5, shuffle=True, random_state=RANDOM_STATE).split(tr, y[tr]):
        ia, ib = tr[a], tr[b]
        sc = StandardScaler().fit(X.iloc[ia])
        m = _clf(n_estimators=n_trees, **hp).fit(sc.transform(X.iloc[ia]), y[ia])
        oof[b] = m.predict_proba(sc.transform(X.iloc[ib]))[:, 1]
    low_tr = ing[tr] <= med
    grid = np.round(np.arange(0.20, 0.61, 0.01), 2)
    scores = [_m(y[tr][low_tr], (oof[low_tr] >= t).astype(int))["bal_acc"] for t in grid]
    t_low = float(grid[int(np.argmax(scores))])

    # evaluación única en validación
    sc = joblib.load(_MODELS / "scaler.pkl"); model = joblib.load(_MODELS / "xgb_clf_model.pkl")
    p = model.predict_proba(sc.transform(X.iloc[va]))[:, 1]
    yv, low = y[va], ing[va] <= med
    base = (p >= 0.5).astype(int)
    adj = np.where(low, (p >= t_low).astype(int), base)
    rep = {"mediana_ingreso_train": med, "umbral_bajo_ingreso": t_low, "criterio": "max. accuracy balanceada, OOF 5-fold en entrenamiento",
           "bajo_ingreso": {"umbral_0.5": _m(yv[low], base[low]), "umbral_ajustado": _m(yv[low], adj[low])},
           "alto_ingreso": _m(yv[~low], base[~low]),
           "global": {"umbral_0.5": _m(yv, base), "umbral_ajustado": _m(yv, adj)}}
    json.dump(rep, open(_INVESTIGACION / "umbral_segmento.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
