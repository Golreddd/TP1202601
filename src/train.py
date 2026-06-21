# -*- coding: utf-8 -*-
"""
Entrenamiento de SmartSave — XGBoost Classifier binario (Déficit / Ahorra).

Pipeline ÚNICO y honesto (sin K-Means, sin regresión):
  1. dataset2.csv -> limpieza (ingreso>0 + dedup + IQR 2.5) -> features honestas.
  2. Split ESTRATIFICADO 70/20/10 (el 10% test se evalúa una sola vez).
  3. Optuna maximizando macro-F1 por VALIDACIÓN CRUZADA 3-fold (robusto, no depende
     de un único split).
  4. XGBClassifier(objective='binary:logistic') + early stopping sobre validación.
  5. SHAP TreeExplainer + persistencia de modelo, scaler, params y métricas.

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
    idx = np.arange(len(y))
    rest, test = train_test_split(idx, test_size=0.10, random_state=seed, stratify=y)
    tr, va = train_test_split(rest, test_size=2 / 9, random_state=seed, stratify=y[rest])
    return tr, va, test, rest


def _eval(model, X, y) -> dict:
    p = model.predict(X)
    return {
        "accuracy": float(accuracy_score(y, p)),
        "precision": float(precision_score(y, p, zero_division=0)),
        "recall": float(recall_score(y, p, zero_division=0)),
        "f1": float(f1_score(y, p)),
        "roc_auc": float(roc_auc_score(y, model.predict_proba(X)[:, 1])),
    }


def _tune(X, y, rest, n_trials: int = 40):
    """Optuna -> maximiza macro-F1 de CV 3-fold sobre `rest` (scaler por fold)."""
    def cv_macro_f1(params):
        skf = StratifiedKFold(3, shuffle=True, random_state=RANDOM_STATE)
        scores = []
        for a, b in skf.split(rest, y[rest]):
            ia, ib = rest[a], rest[b]
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


def _cv_metrics(X, y, params, splits: int = 5) -> dict:
    """Estimado central por CV estratificada (scaler por fold, sin early stopping)."""
    skf = StratifiedKFold(splits, shuffle=True, random_state=RANDOM_STATE)
    acc, rec, f1s, auc = [], [], [], []
    for a, b in skf.split(X, y):
        sc = StandardScaler().fit(X.iloc[a])
        m = _clf(n_estimators=600, **params)
        m.fit(sc.transform(X.iloc[a]), y[a])
        Xb = sc.transform(X.iloc[b])
        p = m.predict(Xb)
        acc.append(accuracy_score(y[b], p)); rec.append(recall_score(y[b], p, zero_division=0))
        f1s.append(f1_score(y[b], p)); auc.append(roc_auc_score(y[b], m.predict_proba(Xb)[:, 1]))
    return {"accuracy": float(np.mean(acc)), "accuracy_std": float(np.std(acc)),
            "recall": float(np.mean(rec)), "f1": float(np.mean(f1s)),
            "roc_auc": float(np.mean(auc))}


def _multiseed_test(X, y, params, seeds=(42, 1, 7, 13, 99)) -> dict:
    """Estimado central honesto del test promediando varias semillas (con early stopping)."""
    acc, rec, f1s, auc = [], [], [], []
    for sd in seeds:
        tr, va, te, _ = _split(y, seed=sd)
        sc = StandardScaler().fit(X.iloc[tr])
        m = _clf(seed=sd, early_stopping=True, n_estimators=1500, **params)
        m.fit(sc.transform(X.iloc[tr]), y[tr], eval_set=[(sc.transform(X.iloc[va]), y[va])], verbose=False)
        Xte = sc.transform(X.iloc[te])
        p = m.predict(Xte)
        acc.append(accuracy_score(y[te], p)); rec.append(recall_score(y[te], p, zero_division=0))
        f1s.append(f1_score(y[te], p)); auc.append(roc_auc_score(y[te], m.predict_proba(Xte)[:, 1]))
    return {"accuracy": float(np.mean(acc)), "recall": float(np.mean(rec)),
            "f1": float(np.mean(f1s)), "roc_auc": float(np.mean(auc)),
            "accuracy_std": float(np.std(acc)), "n_seeds": len(seeds)}


def main(n_trials: int = 40) -> dict:
    os.makedirs(_MODELS, exist_ok=True)

    df = add_features(clean_dataset(str(_DATASET), iqr_factor=2.5, verbose=True))
    feats = referential_features(df)
    y = binary_target(df)
    X = df[feats]
    tr, va, te, rest = _split(y)

    # 1) Optuna (CV macro-F1) -> mejores hiperparámetros
    best, best_cv_f1 = _tune(X, y, rest, n_trials=n_trials)

    # 2) Modelo FINAL: scaler en train, early stopping en validación
    scaler = StandardScaler().fit(X.iloc[tr])
    Xtr, Xva, Xte = scaler.transform(X.iloc[tr]), scaler.transform(X.iloc[va]), scaler.transform(X.iloc[te])
    model = _clf(early_stopping=True, n_estimators=1500, **best)
    model.fit(Xtr, y[tr], eval_set=[(Xva, y[va])], verbose=False)
    n_trees = int(model.best_iteration) + 1

    # 3) SHAP sobre el modelo final
    explainer = shap.TreeExplainer(model)

    # 4) Métricas (train / valid / test + CV + multi-semilla)
    metrics = {
        "modelo": "XGBoost Classifier binario (Déficit / Ahorra)",
        "clases": CLASS_LABELS,
        "n_features": len(feats),
        "features": feats,
        "excluidas_por_fuga": ["GASTO_OTROS_BIENES", "CAPACIDAD_BRUTA", "ING_TOTAL",
                               "montos crudos de gasto", "EDAD"],
        "n_total": int(len(df)), "n_train": int(len(tr)),
        "n_valid": int(len(va)), "n_test": int(len(te)),
        "baseline_clase_mayoritaria_acc": float(max(np.mean(y == 0), np.mean(y == 1))),
        "n_arboles_early_stopping": n_trees,
        "best_cv_macro_f1": best_cv_f1,
        "train": _eval(model, Xtr, y[tr]),
        "valid": _eval(model, Xva, y[va]),
        "test": _eval(model, Xte, y[te]),
        "cv_5fold": _cv_metrics(X, y, best),
        "multi_semilla_test": _multiseed_test(X, y, best),
    }
    metrics["gap_accuracy_train_test"] = round(metrics["train"]["accuracy"] - metrics["test"]["accuracy"], 4)

    # 5) Persistencia de artefactos
    joblib.dump(model, _MODELS / "xgb_clf_model.pkl")
    joblib.dump(scaler, _MODELS / "scaler.pkl")
    joblib.dump(explainer, _MODELS / "shap_explainer.pkl")
    with open(_MODELS / "features.json", "w", encoding="utf-8") as f:
        json.dump(feats, f, ensure_ascii=False, indent=2)
    with open(_MODELS / "xgb_best_params.json", "w", encoding="utf-8") as f:
        json.dump({**best, "n_estimators_max": 1500, "n_arboles_usados": n_trees,
                   "objective": "binary:logistic", "early_stopping_rounds": 50}, f,
                  ensure_ascii=False, indent=2)
    with open(_MODELS / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    return metrics


if __name__ == "__main__":
    rep = main()
    t = rep["test"]; cv = rep["cv_5fold"]; ms = rep["multi_semilla_test"]
    print("\n=========== CLASIFICADOR BINARIO ENTRENADO ===========")
    print(f"Features honestas: {rep['n_features']} | filas: {rep['n_total']} | árboles: {rep['n_arboles_early_stopping']}")
    print(f"TEST        -> acc={t['accuracy']:.3f}  recall={t['recall']:.3f}  F1={t['f1']:.3f}  AUC={t['roc_auc']:.3f}")
    print(f"CV 5-fold   -> acc={cv['accuracy']:.3f}  recall={cv['recall']:.3f}  F1={cv['f1']:.3f}  AUC={cv['roc_auc']:.3f}")
    print(f"Multi-semilla-> acc={ms['accuracy']:.3f}  recall={ms['recall']:.3f}  F1={ms['f1']:.3f}  AUC={ms['roc_auc']:.3f}")
    print(f"gap train-test = {rep['gap_accuracy_train_test']} | baseline = {rep['baseline_clase_mayoritaria_acc']:.3f}")
    print("Artefactos guardados en models/: xgb_clf_model.pkl, scaler.pkl, shap_explainer.pkl, features.json, xgb_best_params.json, metrics.json")
