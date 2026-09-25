# -*- coding: utf-8 -*-
"""
Comparacion de algoritmos y pruebas estadisticas sobre el CONJUNTO DE VALIDACION (20 %).

Comparacion equivalente (observacion del revisor):
  - Logistic Regression y Random Forest se ajustan con el MISMO procedimiento que
    XGBoost: Optuna (TPE, 40 trials, semilla 42) maximizando macro-F1 por CV 3-fold
    SOLO sobre el 80 % de entrenamiento, con el mismo escalado.
  - XGBoost es el modelo de produccion (models/xgb_clf_model.pkl), ajustado con ese
    mismo protocolo en src/train.py.
  - El 20 % de validacion solo se usa aqui, una vez, para evaluar.

Calcula sobre la validacion:
  1. Metricas (Accuracy, Precision, Recall, F1, AUC-ROC, MCC) de los tres modelos e
     IC 95 % bootstrap (2,000 repeticiones).
  2. DeLong (AUC), McNemar (aciertos pareados) y bootstrap pareado de F1.

Uso:   python -m src.stats_tests
Salida: models/stats_tests.json
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import optuna
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, f1_score, matthews_corrcoef,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

from .train import N_TRIALS, RANDOM_STATE, _MODELS, _split, load_xy

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)


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
# Ajuste de hiperparametros de LR y RF (mismo protocolo que XGBoost)
# --------------------------------------------------------------------------

def _lr(p):
    return LogisticRegression(C=p["C"], penalty=p["penalty"], solver="liblinear",
                              max_iter=5000, random_state=RANDOM_STATE)


def _rf(p):
    return RandomForestClassifier(n_estimators=p["n_estimators"], max_depth=p["max_depth"],
                                  min_samples_leaf=p["min_samples_leaf"],
                                  max_features=p["max_features"],
                                  random_state=RANDOM_STATE, n_jobs=-1)


def _tune(builder, space, X, y, idx, n_trials=N_TRIALS):
    def objective(t):
        p = space(t)
        skf = StratifiedKFold(3, shuffle=True, random_state=RANDOM_STATE)
        sc_ = []
        for a, b in skf.split(idx, y[idx]):
            ia, ib = idx[a], idx[b]
            s = StandardScaler().fit(X[ia])
            m = builder(p).fit(s.transform(X[ia]), y[ia])
            sc_.append(f1_score(y[ib], m.predict(s.transform(X[ib])), average="macro"))
        return float(np.mean(sc_))
    st = optuna.create_study(direction="maximize",
                             sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE))
    st.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return st.best_params, float(st.best_value)


LR_SPACE = lambda t: {"C": t.suggest_float("C", 1e-3, 1e2, log=True),
                      "penalty": t.suggest_categorical("penalty", ["l1", "l2"])}
RF_SPACE = lambda t: {"n_estimators": t.suggest_int("n_estimators", 200, 800, step=100),
                      "max_depth": t.suggest_int("max_depth", 3, 20),
                      "min_samples_leaf": t.suggest_int("min_samples_leaf", 1, 30),
                      "max_features": t.suggest_categorical("max_features", ["sqrt", "log2", 0.5])}


def main(n_boot=2000, seed=42):
    _, feats, Xdf, y = load_xy()
    X = Xdf.astype(float).values
    tr, te = _split(y)
    y_te = y[te]

    sc = joblib.load(_MODELS / "scaler.pkl")
    xgb = joblib.load(_MODELS / "xgb_clf_model.pkl")
    Xs = sc.transform(Xdf)

    best_lr, cv_lr = _tune(_lr, LR_SPACE, X, y, tr)
    best_rf, cv_rf = _tune(_rf, RF_SPACE, X, y, tr)
    lr = _lr(best_lr).fit(Xs[tr], y[tr])
    rf = _rf(best_rf).fit(Xs[tr], y[tr])
    modelos = {"Logistic Regression": lr, "Random Forest": rf, "XGBoost": xgb}

    pred = {k: m.predict(Xs[te]) for k, m in modelos.items()}
    prob = {k: m.predict_proba(Xs[te])[:, 1] for k, m in modelos.items()}

    rep = {"n_valid": int(len(y_te)), "n_boot": n_boot, "seed": seed,
           "baseline_clase_mayoritaria": float(max(y_te.mean(), 1 - y_te.mean())),
           "hiperparametros": {"Logistic Regression": {**best_lr, "cv_macro_f1": cv_lr},
                               "Random Forest": {**best_rf, "cv_macro_f1": cv_rf}},
           "metricas": {}, "delong": {}, "mcnemar": {}, "bootstrap_f1": {}}

    print(f"\nValidacion: n = {len(y_te)} | LR {best_lr} | RF {best_rf}\n")
    for nombre in modelos:
        m = _metrics(y_te, pred[nombre], prob[nombre])
        m["mcc"] = matthews_corrcoef(y_te, pred[nombre])
        ci = bootstrap_ci(y_te, pred[nombre], prob[nombre], n_boot, seed)
        rep["metricas"][nombre] = {k: {"valor": float(v), **ci.get(k, {})} for k, v in m.items()}
        print(nombre, "  ".join(f"{k}={v:.3f}" for k, v in m.items()))

    for a, b in [("XGBoost", "Logistic Regression"), ("XGBoost", "Random Forest")]:
        auc_a, auc_b, p = delong_test(y_te, prob[a], prob[b])
        rep["delong"][f"{a} vs {b}"] = {"auc_a": auc_a, "auc_b": auc_b,
                                        "diferencia": auc_a - auc_b, "p_value": p}
        nb, nc, pm, met = mcnemar_test(y_te, pred[a], pred[b])
        rep["mcnemar"][f"{a} vs {b}"] = {"solo_a_acierta": nb, "solo_b_acierta": nc,
                                         "p_value": pm, "metodo": met}
        obs, lo, hi, pf = paired_bootstrap_f1(y_te, pred[a], pred[b], n_boot, seed)
        rep["bootstrap_f1"][f"{a} vs {b}"] = {"diferencia": obs, "ci_low": lo,
                                              "ci_high": hi, "p_value": pf}
        print(f"{a} vs {b}: DeLong dif={auc_a-auc_b:+.4f} p={p:.4f} | McNemar p={pm:.4f} "
              f"| F1 dif={obs:+.4f} IC[{lo:+.4f},{hi:+.4f}] p={pf:.4f}")

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
