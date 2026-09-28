# -*- coding: utf-8 -*-
"""
Analisis complementarios sobre el CONJUNTO DE VALIDACION (20 %) con el modelo de produccion.

  1. Matriz de confusion y curva ROC (figuras).
  2. SHAP: importancia media |SHAP|, summary plot y un caso local.
  3. Desempeno por subgrupos (tipo de ingreso, educacion, ingreso).
  4. Estabilidad frente a la particion: 5 semillas (42, 1, 7, 13, 99), mismo protocolo.
  5. Sensibilidad a la limpieza: 6 configuraciones, mismos hiperparametros y protocolo.

Uso:   python -m src.research.analisis_validacion
Salida: models/investigacion/analisis_validacion.json y figuras en models/investigacion/figuras/
"""
from __future__ import annotations

import json
import warnings

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from scipy.stats.mstats import winsorize
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, roc_auc_score,
                             roc_curve)

from ..pipeline.preprocessing import (DEDUP_COLS, GASTO_COLS, add_features, binary_target,
                                      referential_features)
from ..pipeline.train import _DATASET, _INVESTIGACION, _MODELS, _split, fit_final, load_xy

warnings.filterwarnings("ignore")
FIG = _INVESTIGACION / "figuras"
SEEDS = [42, 1, 7, 13, 99]

NOMBRES = {
    "LOG_ING": "Log. del ingreso", "PRESION_FINANCIERA": "Presión financiera",
    "GASTO_SALUD_R": "Ratio salud", "GASTO_EDUCACION_R": "Ratio educación",
    "GASTO_VIVIENDA_SERVICIOS_R": "Ratio vivienda", "GASTO_ALIMENTOS_R": "Ratio alimentos",
    "GASTO_TRANSPORTE_R": "Ratio transporte", "COMMIT_PER_CAPITA": "Gasto comprometido p.c.",
    "ING_PER_CAPITA": "Ingreso per cápita", "ING_INFORMAL": "Ingreso informal",
    "ING_PLANILLA": "Ingreso de planilla", "INFORMAL_SHARE": "Participación informal",
    "MIEMBROS_HOGAR": "Miembros del hogar", "NIVEL_EDUC": "Nivel educativo",
    "DEPENDE_INFORMAL": "Depende de informal", "TIPO_FORMAL": "Tipo formal",
    "TIPO_INFORMAL": "Tipo informal", "TIPO_MIXTO": "Tipo mixto",
}


def _hp():
    with open(_MODELS / "xgb_best_params.json", encoding="utf-8") as f:
        best = json.load(f)
    return {k: v for k, v in best.items()
            if k not in ("objective", "early_stopping_rounds", "early_stopping_sobre",
                         "n_estimators_max", "n_arboles_usados")}


def _sub(y, p, pr):
    tn, fp, fn, tp = confusion_matrix(y, p, labels=[0, 1]).ravel()
    return {"n": int(len(y)), "roc_auc": float(roc_auc_score(y, pr)),
            "f1": float(f1_score(y, p)), "fnr": float(fn / max(fn + tp, 1)),
            "fpr": float(fp / max(fp + tn, 1))}


def _clean_cfg(dedup=True, wins=True, iqr=2.5):
    df = pd.read_csv(_DATASET)
    df = df[df["ING_PLANILLA"] + df["ING_INFORMAL"] > 0].reset_index(drop=True)
    if dedup:
        df = df.drop_duplicates(subset=DEDUP_COLS).reset_index(drop=True)
    if wins:
        df["TARGET_AHORRO"] = winsorize(df["TARGET_AHORRO"], limits=[0.01, 0.01]).data
    if iqr is not None:
        mask = pd.Series(True, index=df.index)
        for c in ["TARGET_AHORRO"] + GASTO_COLS:
            q1, q3 = df[c].quantile(0.25), df[c].quantile(0.75)
            mask &= (df[c] >= q1 - iqr * (q3 - q1)) & (df[c] <= q3 + iqr * (q3 - q1))
        df = df[mask].reset_index(drop=True)
    return add_features(df)


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    df, feats, X, y = load_xy()
    tr, te = _split(y)
    sc = joblib.load(_MODELS / "scaler.pkl")
    m = joblib.load(_MODELS / "xgb_clf_model.pkl")
    Xte = sc.transform(X.iloc[te])
    y_te = y[te]
    prob = m.predict_proba(Xte)[:, 1]
    pred = (prob >= 0.5).astype(int)
    rep = {"n_valid": int(len(te))}

    # 1) matriz de confusion y ROC
    cm = confusion_matrix(y_te, pred, labels=[0, 1])
    rep["confusion"] = {"tn": int(cm[0, 0]), "fp": int(cm[0, 1]),
                        "fn": int(cm[1, 0]), "tp": int(cm[1, 1])}
    fig, ax = plt.subplots(figsize=(4, 3.5), dpi=200)
    ax.imshow(cm, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=14,
                    color="white" if cm[i, j] > cm.max() / 2 else "black")
    ax.set_xticks([0, 1], ["Déficit", "Ahorra"]); ax.set_yticks([0, 1], ["Déficit", "Ahorra"])
    ax.set_xlabel("Predicción"); ax.set_ylabel("Real")
    ax.set_title(f"Matriz de confusión (validación, n={len(te)})", fontsize=10)
    fig.tight_layout(); fig.savefig(FIG / "cm_valid.png"); plt.close(fig)

    auc = roc_auc_score(y_te, prob)
    fpr, tpr, _ = roc_curve(y_te, prob)
    fig, ax = plt.subplots(figsize=(4, 3.3), dpi=200)
    ax.plot(fpr, tpr, label=f"XGBoost (AUC = {auc:.3f})")
    ax.plot([0, 1], [0, 1], "--", color="gray", label="Aleatorio (AUC = 0.500)")
    ax.set_xlabel("Tasa de Falsos Positivos"); ax.set_ylabel("Tasa de Verdaderos Positivos")
    ax.set_title("Curva ROC, conjunto de validación", fontsize=9); ax.legend(fontsize=7, loc="lower right")
    fig.tight_layout(); fig.savefig(FIG / "roc_valid.png"); plt.close(fig)

    # 2) SHAP
    expl = shap.TreeExplainer(m)
    sv = expl.shap_values(Xte)
    imp = pd.Series(np.abs(sv).mean(0), index=feats).sort_values(ascending=False)
    rep["shap_mean_abs"] = {k: float(v) for k, v in imp.items()}
    Xraw = X.iloc[te].reset_index(drop=True)
    shap.summary_plot(sv, Xraw.rename(columns=NOMBRES), max_display=12, show=False,
                      plot_size=(6, 4.5))
    fig = plt.gcf()
    fig.axes[0].set_xlabel("Valor SHAP (impacto en la salida del modelo)")
    if len(fig.axes) > 1:                      # barra de color
        cb = fig.axes[-1]
        cb.set_ylabel("Valor de la variable")
        cb.set_yticklabels(["Bajo", "Alto"])
    fig.set_dpi(200); plt.tight_layout(); plt.savefig(FIG / "shap_valid.png", dpi=200)
    plt.close("all")
    # caso local: usuario en deficit bien clasificado (con alimentos, vivienda y transporte
    # registrados) cuyo ingreso es el mas cercano a la mediana del grupo en deficit
    dte = df.iloc[te].reset_index(drop=True)
    ok = np.where((y_te == 0) & (pred == 0) & (dte[["GASTO_ALIMENTOS", "GASTO_VIVIENDA_SERVICIOS",
                                                     "GASTO_TRANSPORTE"]].gt(0).all(axis=1).values))[0]
    med = np.median(dte.loc[y_te == 0, "ING_TOTAL"])
    k = ok[np.argmin(np.abs(dte.loc[ok, "ING_TOTAL"].values - med))]
    top = pd.Series(sv[k], index=feats).sort_values()
    rep["shap_local"] = {"prob_ahorra": float(prob[k]),
                         "ing_total": float(dte.loc[k, "ING_TOTAL"]),
                         "valores": {f: float(Xraw.loc[k, f]) for f in top.index[:3]},
                         "contribuciones": {f: float(top[f]) for f in top.index[:3]},
                         "criterio": "déficit bien clasificado, con gasto esencial registrado, cuyo ingreso es el más cercano a la mediana del grupo en déficit"}

    # 3) subgrupos
    d = df.iloc[te].reset_index(drop=True)
    tipo = d[["TIPO_FORMAL", "TIPO_INFORMAL", "TIPO_MIXTO"]].idxmax(axis=1)
    edu_med = df["NIVEL_EDUC"].iloc[tr].median()
    ing_med = d["ING_TOTAL"].median()
    grupos = {
        "Ingreso formal": (tipo == "TIPO_FORMAL").values,
        "Ingreso informal": (tipo == "TIPO_INFORMAL").values,
        "Ingreso mixto": (tipo == "TIPO_MIXTO").values,
        "Educación ≤ mediana": (d["NIVEL_EDUC"] <= edu_med).values,
        "Educación > mediana": (d["NIVEL_EDUC"] > edu_med).values,
        "Ingreso ≤ mediana": (d["ING_TOTAL"] <= ing_med).values,
        "Ingreso > mediana": (d["ING_TOTAL"] > ing_med).values,
    }
    rep["subgrupos"] = {g: _sub(y_te[msk], pred[msk], prob[msk]) for g, msk in grupos.items()}
    rep["mediana_ingreso_valid"] = float(ing_med)
    rep["mediana_educ_train"] = float(edu_med)

    # 4) multi-semilla (misma configuracion, distinta particion)
    hp = _hp()
    acc, aucs = [], []
    for s in SEEDS:
        a, b = _split(y, seed=s)
        mm, ss, _ = fit_final(X, y, a, hp, seed=s)
        pp = mm.predict_proba(ss.transform(X.iloc[b]))[:, 1]
        acc.append(accuracy_score(y[b], (pp >= 0.5).astype(int))); aucs.append(roc_auc_score(y[b], pp))
    rep["multisemilla"] = {"seeds": SEEDS, "accuracy": acc, "roc_auc": aucs,
                           "acc_mean": float(np.mean(acc)), "acc_std": float(np.std(acc)),
                           "auc_mean": float(np.mean(aucs)), "auc_std": float(np.std(aucs))}

    # 5) sensibilidad a la limpieza
    cfgs = {"Final (dedup + winsor. 1 % + IQR 2.5)": dict(),
            "Sin deduplicar": dict(dedup=False), "Sin winsorización": dict(wins=False),
            "Sin filtro IQR": dict(iqr=None), "IQR 3.0": dict(iqr=3.0), "IQR 1.5": dict(iqr=1.5)}
    rep["sensibilidad"] = {}
    for nombre, kw in cfgs.items():
        dd = _clean_cfg(**kw)
        ff = referential_features(dd)
        yy = binary_target(dd)
        a, b = _split(yy)
        mm, ss, _ = fit_final(dd[ff], yy, a, hp)
        pp = mm.predict_proba(ss.transform(dd[ff].iloc[b]))[:, 1]
        rep["sensibilidad"][nombre] = {"n": int(len(dd)), "roc_auc": float(roc_auc_score(yy[b], pp)),
                                       "accuracy": float(accuracy_score(yy[b], (pp >= 0.5).astype(int)))}

    with open(_INVESTIGACION / "analisis_validacion.json", "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in rep.items() if k != "shap_mean_abs"}, ensure_ascii=False, indent=1))
    print("SHAP:", {k: round(v, 3) for k, v in rep["shap_mean_abs"].items()})
    return rep


if __name__ == "__main__":
    main()
