# -*- coding: utf-8 -*-
"""
Pruebas estadisticas para el paper (observacion 5).

Calcula sobre el CONJUNTO DE VALIDACION:
  1. Intervalos de confianza al 95 % (bootstrap percentil) de Accuracy, Precision,
     Recall, F1 y AUC-ROC para Logistic Regression, Random Forest y XGBoost.
  2. Test de DeLong para comparar AUC entre modelos (correlacionado, mismo conjunto).
  3. Test de McNemar para comparar las clasificaciones (aciertos/errores pareados).
  4. Bootstrap pareado para la diferencia de F1.

Uso:
    python -m src.stats_tests
    python -m src.stats_tests --n-boot 2000 --seed 42

Salida: tabla por consola y archivo models/stats_tests.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.preprocessing import StandardScaler

from .preprocessing import add_features, binary_target, referential_features
from .train import _MODELS, _ROOT, _clf, _split

# Dataset YA LIMPIO (salida de clean_dataset, no el crudo dataset2.csv que no se
# versiona): mismo n_total=9527 que reporta models/metrics.json. NO se le vuelve a
# aplicar clean_dataset() aqui -- winsorizar/filtrar IQR una segunda vez sobre datos
# ya limpios recorta de mas (9527 -> 6950) y deja de coincidir con el split real
# (7621/1906, 80/20) con el que se entreno el modelo que esta desplegado.
_DATASET_LIMPIO = _ROOT / "dataset_final_limpio.csv"

# --------------------------------------------------------------------------
# DeLong (Sun & Xu, 2014): varianza del AUC y test para AUCs correlacionados
# --------------------------------------------------------------------------


def _midrank(x: np.ndarray) -> np.ndarray:
    J = np.argsort(x)
    Z = x[J]
    N = len(x)
    T = np.zeros(N, dtype=float)
    i = 0
    while i < N:
        j = i
        while j < N and Z[j] == Z[i]:
            j += 1
        T[i:j] = 0.5 * (i + j - 1) + 1
        i = j
    out = np.empty(N, dtype=float)
    out[J] = T
    return out


def _fast_delong(predictions_sorted_transposed: np.ndarray, label_1_count: int):
    m = label_1_count
    n = predictions_sorted_transposed.shape[1] - m
    positive = predictions_sorted_transposed[:, :m]
    negative = predictions_sorted_transposed[:, m:]
    k = predictions_sorted_transposed.shape[0]

    tx = np.empty([k, m], dtype=float)
    ty = np.empty([k, n], dtype=float)
    tz = np.empty([k, m + n], dtype=float)
    for r in range(k):
        tx[r, :] = _midrank(positive[r, :])
        ty[r, :] = _midrank(negative[r, :])
        tz[r, :] = _midrank(predictions_sorted_transposed[r, :])

    aucs = tz[:, :m].sum(axis=1) / m / n - float(m + 1.0) / 2.0 / n
    v01 = (tz[:, :m] - tx[:, :]) / n
    v10 = 1.0 - (tz[:, m:] - ty[:, :]) / m
    sx = np.cov(v01)
    sy = np.cov(v10)
    delongcov = sx / m + sy / n
    return aucs, np.atleast_2d(delongcov)


def delong_test(y_true: np.ndarray, p1: np.ndarray, p2: np.ndarray):
    """Devuelve (auc1, auc2, p_value) para dos modelos sobre el mismo conjunto."""
    order = (-y_true).argsort(kind="mergesort")
    label_1_count = int(y_true.sum())
    preds = np.vstack((p1, p2))[:, order]
    aucs, cov = _fast_delong(preds, label_1_count)
    l = np.array([[1, -1]])
    var = float((l @ cov @ l.T).item())
    if var <= 0:
        return float(aucs[0]), float(aucs[1]), 1.0
    z = (aucs[0] - aucs[1]) / np.sqrt(var)
    p = 2.0 * (1.0 - stats.norm.cdf(abs(z)))
    return float(aucs[0]), float(aucs[1]), float(p)


# --------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------

def _metrics(y, pred, prob) -> dict:
    return {
        "accuracy": accuracy_score(y, pred),
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
        "roc_auc": roc_auc_score(y, prob),
    }


def bootstrap_ci(y, pred, prob, n_boot=2000, seed=42) -> dict:
    """IC 95 % percentil, remuestreando indices con reemplazo (estratificado)."""
    rng = np.random.default_rng(seed)
    n = len(y)
    acc, pre, rec, f1s, auc = [], [], [], [], []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if len(np.unique(y[idx])) < 2:          # muestra degenerada
            continue
        acc.append(accuracy_score(y[idx], pred[idx]))
        pre.append(precision_score(y[idx], pred[idx], zero_division=0))
        rec.append(recall_score(y[idx], pred[idx], zero_division=0))
        f1s.append(f1_score(y[idx], pred[idx], zero_division=0))
        auc.append(roc_auc_score(y[idx], prob[idx]))
    out = {}
    for name, vals in [("accuracy", acc), ("precision", pre), ("recall", rec),
                       ("f1", f1s), ("roc_auc", auc)]:
        lo, hi = np.percentile(vals, [2.5, 97.5])
        out[name] = {"ci_low": float(lo), "ci_high": float(hi)}
    return out


def mcnemar_test(y, pred_a, pred_b):
    """McNemar con correccion de continuidad; exacto (binomial) si b+c < 25."""
    correct_a = (pred_a == y)
    correct_b = (pred_b == y)
    b = int(np.sum(correct_a & ~correct_b))   # A acierta, B falla
    c = int(np.sum(~correct_a & correct_b))   # A falla, B acierta
    if b + c == 0:
        return b, c, 1.0, "sin discordancias"
    if b + c < 25:
        p = float(stats.binomtest(b, b + c, 0.5).pvalue)
        return b, c, p, "exacto (binomial)"
    chi2 = (abs(b - c) - 1.0) ** 2 / (b + c)
    p = float(1.0 - stats.chi2.cdf(chi2, df=1))
    return b, c, p, "chi2 con correccion"


def paired_bootstrap_f1(y, pred_a, pred_b, n_boot=2000, seed=42):
    """Diferencia de F1 (A - B) con IC 95 % y p-value bilateral."""
    rng = np.random.default_rng(seed)
    n = len(y)
    diffs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if len(np.unique(y[idx])) < 2:
            continue
        diffs.append(f1_score(y[idx], pred_a[idx], zero_division=0)
                     - f1_score(y[idx], pred_b[idx], zero_division=0))
    diffs = np.array(diffs)
    obs = f1_score(y, pred_a, zero_division=0) - f1_score(y, pred_b, zero_division=0)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    p = 2.0 * min((diffs <= 0).mean(), (diffs >= 0).mean())
    return float(obs), float(lo), float(hi), float(min(p, 1.0))


# --------------------------------------------------------------------------

def main(n_boot=2000, seed=42):
    df = pd.read_csv(str(_DATASET_LIMPIO))
    df = add_features(df)
    y = binary_target(df)
    feats = referential_features(df)
    X = df[feats].astype(float).values
    tr, va = _split(y)
    sc = StandardScaler().fit(X[tr])
    Xs = sc.transform(X)
    y_va = y[va]

    # --- hiperparametros de XGBoost ya optimizados
    with open(_MODELS / "xgb_best_params.json", encoding="utf-8") as f:
        best = json.load(f)
    hp = {k: v for k, v in best.items()
          if k not in ("objective", "early_stopping_rounds",
                       "n_estimators_max", "n_arboles_usados")}
    hp["n_estimators"] = best.get("n_estimators_max", 1500)

    modelos = {}
    xgb = _clf(early_stopping=True, **hp)
    xgb.fit(Xs[tr], y[tr], eval_set=[(Xs[va], y[va])], verbose=False)
    modelos["XGBoost"] = xgb

    lr = LogisticRegression(max_iter=2000, C=1.0, random_state=seed)
    lr.fit(Xs[tr], y[tr])
    modelos["Logistic Regression"] = lr

    rf = RandomForestClassifier(n_estimators=500, min_samples_leaf=2,
                                random_state=seed, n_jobs=-1)
    rf.fit(Xs[tr], y[tr])
    modelos["Random Forest"] = rf

    pred = {k: m.predict(Xs[va]) for k, m in modelos.items()}
    prob = {k: m.predict_proba(Xs[va])[:, 1] for k, m in modelos.items()}

    rep = {"n_valid": int(len(y_va)), "n_boot": n_boot, "seed": seed,
           "puntual_e_ic": {}, "delong": {}, "mcnemar": {}, "bootstrap_f1": {}}

    print(f"\nConjunto de validacion: n = {len(y_va)} | bootstrap: {n_boot} repeticiones\n")
    print("=" * 78)
    print("1) METRICAS PUNTUALES E INTERVALOS DE CONFIANZA AL 95 %")
    print("=" * 78)
    for nombre in modelos:
        m = _metrics(y_va, pred[nombre], prob[nombre])
        ci = bootstrap_ci(y_va, pred[nombre], prob[nombre], n_boot, seed)
        rep["puntual_e_ic"][nombre] = {k: {"valor": float(m[k]), **ci[k]} for k in m}
        print(f"\n{nombre}")
        for k in ["accuracy", "precision", "recall", "f1", "roc_auc"]:
            print(f"   {k:10s} {m[k]:.3f}   IC 95 % [{ci[k]['ci_low']:.3f} - {ci[k]['ci_high']:.3f}]")

    pares = [("XGBoost", "Logistic Regression"), ("XGBoost", "Random Forest"),
             ("Random Forest", "Logistic Regression")]

    print("\n" + "=" * 78)
    print("2) TEST DE DeLONG PARA AUC-ROC (muestras correlacionadas)")
    print("=" * 78)
    for a, b in pares:
        auc_a, auc_b, p = delong_test(y_va, prob[a], prob[b])
        sig = "SIGNIFICATIVA" if p < 0.05 else "no significativa"
        rep["delong"][f"{a} vs {b}"] = {"auc_a": auc_a, "auc_b": auc_b,
                                        "diferencia": auc_a - auc_b, "p_value": p}
        print(f"   {a} ({auc_a:.3f}) vs {b} ({auc_b:.3f}): "
              f"dif = {auc_a - auc_b:+.4f}, p = {p:.4f} -> {sig}")

    print("\n" + "=" * 78)
    print("3) TEST DE McNEMAR PARA LA CLASIFICACION")
    print("=" * 78)
    for a, b in pares:
        nb, nc, p, metodo = mcnemar_test(y_va, pred[a], pred[b])
        sig = "SIGNIFICATIVA" if p < 0.05 else "no significativa"
        rep["mcnemar"][f"{a} vs {b}"] = {"solo_a_acierta": nb, "solo_b_acierta": nc,
                                         "p_value": p, "metodo": metodo}
        print(f"   {a} vs {b}: solo {a} acierta = {nb}, solo {b} acierta = {nc}, "
              f"p = {p:.4f} ({metodo}) -> {sig}")

    print("\n" + "=" * 78)
    print("4) BOOTSTRAP PAREADO PARA LA DIFERENCIA DE F1")
    print("=" * 78)
    for a, b in pares:
        obs, lo, hi, p = paired_bootstrap_f1(y_va, pred[a], pred[b], n_boot, seed)
        sig = "SIGNIFICATIVA" if (lo > 0 or hi < 0) else "no significativa"
        rep["bootstrap_f1"][f"{a} vs {b}"] = {"diferencia": obs, "ci_low": lo,
                                              "ci_high": hi, "p_value": p}
        print(f"   {a} vs {b}: dif F1 = {obs:+.4f}, "
              f"IC 95 % [{lo:+.4f} - {hi:+.4f}], p = {p:.4f} -> {sig}")

    salida = Path(_MODELS) / "stats_tests.json"
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"\nResultados guardados en {salida}\n")
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    main(n_boot=a.n_boot, seed=a.seed)
