# -*- coding: utf-8 -*-
"""
Entrenamiento de SmartSave — XGBoost Classifier binario (Déficit / Ahorra).

Protocolo 80/20: el 20 % de VALIDACIÓN no interviene en ninguna decisión de entrenamiento
(la prueba con datos nuevos se hace con los usuarios reales del sistema):
  1. dataset2.csv -> limpieza (ingreso>0 + dedup + winsorización 1 % del ahorro continuo
     + IQR 2.5) -> features honestas -> etiqueta binaria (ahorro >= 0).
  2. Split ESTRATIFICADO 80/20: entrenamiento (80 %) / validación (20 %), semilla 42.
  3. Optuna (TPE, 40 trials) maximizando macro-F1 por CV 3-fold SOLO sobre el 80 %.
  4. Early stopping sobre un 10 % interno del 80 % (estratificado): fija el número de
     árboles; luego el modelo final se reentrena con ese número sobre todo el 80 %.
  5. CV 5-fold SOLO sobre el 80 % como estimación de estabilidad.
  6. Evaluación ÚNICA sobre el 20 % de validación.
  7. SHAP TreeExplainer + persistencia de modelo, scaler, params y métricas.

Uso:  python -m src.train
"""

import json
import os
import warnings
from pathlib import Path

import joblib
import numpy as np
import optuna
import shap
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from .preprocessing import (CLASS_LABELS, add_features, binary_target,
                            clean_dataset, referential_features)

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

RANDOM_STATE = 42
N_TRIALS = 40
INNER_ES_FRAC = 0.10          # fracción del 80 % reservada para early stopping
_ROOT = Path(__file__).resolve().parent.parent
_MODELS = _ROOT / "models"
_DATASET = _ROOT / "dataset2.csv"


def _clf(seed=RANDOM_STATE, early_stopping=False, **params) -> XGBClassifier:
    base = dict(objective="binary:logistic", random_state=seed,
                tree_method="hist", verbosity=0, eval_metric="logloss", **params)
    if early_stopping:
        base["early_stopping_rounds"] = 50
    return XGBClassifier(**base)


def _split(y, seed=RANDOM_STATE):
    """80 % entrenamiento / 20 % validación (estratificado). La validación no se usa hasta el final."""
    idx = np.arange(len(y))
    tr, te = train_test_split(idx, test_size=0.20, random_state=seed, stratify=y)
    return tr, te


def _inner_split(y, tr, seed=RANDOM_STATE):
    """Parte interna del entrenamiento para early stopping (10 %, estratificada)."""
    a, b = train_test_split(tr, test_size=INNER_ES_FRAC, random_state=seed, stratify=y[tr])
    return a, b


def _eval(model, X, y) -> dict:
    p = model.predict(X)
    return {
        "accuracy": float(accuracy_score(y, p)),
        "precision": float(precision_score(y, p, zero_division=0)),
        "recall": float(recall_score(y, p, zero_division=0)),
        "f1": float(f1_score(y, p)),
        "roc_auc": float(roc_auc_score(y, model.predict_proba(X)[:, 1])),
    }


def _tune(X, y, idx, n_trials: int = N_TRIALS):
    """Optuna -> maximiza macro-F1 de CV 3-fold sobre `idx` (solo entrenamiento)."""
    def cv_macro_f1(params):
        skf = StratifiedKFold(3, shuffle=True, random_state=RANDOM_STATE)
        scores = []
        for a, b in skf.split(idx, y[idx]):
            ia, ib = idx[a], idx[b]
            sc = StandardScaler().fit(X.iloc[ia])
            m = _clf(n_estimators=500, **params)
            m.fit(sc.transform(X.iloc[ia]), y[ia])
            scores.append(f1_score(y[ib], m.predict(sc.transform(X.iloc[ib])), average="macro"))
        return float(np.mean(scores))

    def objective(t):
        params = dict(
            max_depth=t.suggest_int("max_depth", 3, 7),
            learning_rate=t.suggest_float("learning_rate", 0.01, 0.1, log=True),
            min_child_weight=t.suggest_int("min_child_weight", 2, 30),
            reg_alpha=t.suggest_float("reg_alpha", 0.0, 5.0),
            reg_lambda=t.suggest_float("reg_lambda", 1.0, 10.0),
            subsample=t.suggest_float("subsample", 0.6, 1.0),
            colsample_bytree=t.suggest_float("colsample_bytree", 0.6, 1.0),
            gamma=t.suggest_float("gamma", 0.0, 1.0),
        )
        return cv_macro_f1(params)

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return study.best_params, float(study.best_value)


def fit_final(X, y, tr, params, seed=RANDOM_STATE):
    """Scaler en el 80 %; early stopping en el 10 % interno; reajuste en todo el 80 %."""
    scaler = StandardScaler().fit(X.iloc[tr])
    a, b = _inner_split(y, tr, seed)
    probe = _clf(seed=seed, early_stopping=True, n_estimators=1500, **params)
    probe.fit(scaler.transform(X.iloc[a]), y[a],
              eval_set=[(scaler.transform(X.iloc[b]), y[b])], verbose=False)
    n_trees = int(probe.best_iteration) + 1
    model = _clf(seed=seed, n_estimators=n_trees, **params)
    model.fit(scaler.transform(X.iloc[tr]), y[tr])
    return model, scaler, n_trees


def _cv_metrics(X, y, idx, params, n_trees, splits: int = 5) -> dict:
    """CV estratificada SOLO sobre el entrenamiento (scaler por fold)."""
    skf = StratifiedKFold(splits, shuffle=True, random_state=RANDOM_STATE)
    acc, pre, rec, f1s, auc = [], [], [], [], []
    for a, b in skf.split(idx, y[idx]):
        ia, ib = idx[a], idx[b]
        sc = StandardScaler().fit(X.iloc[ia])
        m = _clf(n_estimators=n_trees, **params)
        m.fit(sc.transform(X.iloc[ia]), y[ia])
        Xb = sc.transform(X.iloc[ib])
        p = m.predict(Xb)
        acc.append(accuracy_score(y[ib], p)); pre.append(precision_score(y[ib], p, zero_division=0))
        rec.append(recall_score(y[ib], p, zero_division=0))
        f1s.append(f1_score(y[ib], p)); auc.append(roc_auc_score(y[ib], m.predict_proba(Xb)[:, 1]))
    return {"accuracy": float(np.mean(acc)), "accuracy_std": float(np.std(acc)),
            "precision": float(np.mean(pre)), "recall": float(np.mean(rec)),
            "f1": float(np.mean(f1s)), "roc_auc": float(np.mean(auc)),
            "roc_auc_std": float(np.std(auc))}


def load_xy(drop=()):
    df = add_features(clean_dataset(str(_DATASET), iqr_factor=2.5, verbose=True))
    feats = [f for f in referential_features(df) if f not in drop]
    return df, feats, df[feats], binary_target(df)


def main(n_trials: int = N_TRIALS, drop=(), save: bool = True) -> dict:
    os.makedirs(_MODELS, exist_ok=True)
    df, feats, X, y = load_xy(drop)
    tr, te = _split(y)

    best, best_cv_f1 = _tune(X, y, tr, n_trials=n_trials)          # 1) solo 80 %
    model, scaler, n_trees = fit_final(X, y, tr, best)             # 2) ES interno
    explainer = shap.TreeExplainer(model)

    Xtr, Xte = scaler.transform(X.iloc[tr]), scaler.transform(X.iloc[te])
    metrics = {
        "modelo": "XGBoost Classifier binario (Déficit / Ahorra)",
        "protocolo": "80/20 entrenamiento/validación; Optuna, CV y early stopping solo en el 80 %",
        "clases": CLASS_LABELS,
        "n_features": len(feats),
        "features": feats,
        "excluidas_por_fuga": ["GASTO_OTROS_BIENES", "GASTO_VESTIDO", "GASTO_COMUNICACIONES",
                               "CAPACIDAD_BRUTA", "ING_TOTAL", "montos crudos de gasto", "EDAD"],
        "n_total": int(len(df)), "n_train": int(len(tr)), "n_valid": int(len(te)),
        "n_early_stopping_interno": int(round(len(tr) * INNER_ES_FRAC)),
        "baseline_clase_mayoritaria_acc": float(max(np.mean(y[te] == 0), np.mean(y[te] == 1))),
        "n_arboles_early_stopping": n_trees,
        "best_cv_macro_f1": best_cv_f1,
        "train": _eval(model, Xtr, y[tr]),
        "valid": _eval(model, Xte, y[te]),
        "cv_5fold_train": _cv_metrics(X, y, tr, best, n_trees),
    }
    metrics["gap_accuracy_train_valid"] = round(metrics["train"]["accuracy"] - metrics["valid"]["accuracy"], 4)

    if save:
        joblib.dump(model, _MODELS / "xgb_clf_model.pkl")
        joblib.dump(scaler, _MODELS / "scaler.pkl")
        joblib.dump(explainer, _MODELS / "shap_explainer.pkl")
        with open(_MODELS / "features.json", "w", encoding="utf-8") as f:
            json.dump(feats, f, ensure_ascii=False, indent=2)
        with open(_MODELS / "xgb_best_params.json", "w", encoding="utf-8") as f:
            json.dump({**best, "n_estimators_max": 1500, "n_arboles_usados": n_trees,
                       "objective": "binary:logistic", "early_stopping_rounds": 50,
                       "early_stopping_sobre": "10 % interno del entrenamiento"}, f,
                      ensure_ascii=False, indent=2)
        with open(_MODELS / "metrics.json", "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
    return metrics


if __name__ == "__main__":
    rep = main()
    tr_m, te_m, cv = rep["train"], rep["valid"], rep["cv_5fold_train"]
    print("\n=========== CLASIFICADOR BINARIO ENTRENADO ===========")
    print(f"Features: {rep['n_features']} | filas: {rep['n_total']} | árboles: {rep['n_arboles_early_stopping']}")
    print(f"TRAIN     -> acc={tr_m['accuracy']:.3f}  F1={tr_m['f1']:.3f}  AUC={tr_m['roc_auc']:.3f}")
    print(f"VALID 20% -> acc={te_m['accuracy']:.3f}  P={te_m['precision']:.3f}  R={te_m['recall']:.3f}  F1={te_m['f1']:.3f}  AUC={te_m['roc_auc']:.3f}")
    print(f"CV5 (80%) -> acc={cv['accuracy']:.3f}±{cv['accuracy_std']:.3f}  F1={cv['f1']:.3f}  AUC={cv['roc_auc']:.3f}")
    print(f"gap train-valid = {rep['gap_accuracy_train_valid']} | baseline = {rep['baseline_clase_mayoritaria_acc']:.3f}")
