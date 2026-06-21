# -*- coding: utf-8 -*-
"""
Preprocesamiento de SmartSave — pipeline ÚNICO de clasificación binaria.

Tarea: clasificar la capacidad de ahorro del mes en  0 = Déficit (ahorro < 0)  o
1 = Ahorra (ahorro >= 0), a partir de features HONESTAS (sin fuga de la identidad
contable `ahorro = ingreso − gasto`).

Control de fuga (núcleo del diseño): el objetivo es la resta ingreso − gasto, así que
se EXCLUYEN del modelo todas las variables que la reconstruyen:
  - ING_TOTAL y CAPACIDAD_BRUTA (corr > 0.7 con el ahorro).
  - los montos CRUDOS de gasto (entran solo como RATIO % del ingreso).
  - GASTO_OTROS_BIENES + gastos discrecionales (vestido, comunicaciones): son la
    palanca de la recomendación; además completarían la identidad.
  - EDAD (sin señal en población 18-30).
Se MANTIENEN: demografía (educación, miembros, estrato, tipo de ingreso) + ingresos
+ gastos COMPROMETIDOS solo como ratio. Resultado: 19 features referenciales honestas.
"""

import numpy as np
import pandas as pd
from scipy.stats.mstats import winsorize

GASTO_COLS = ["GASTO_ALIMENTOS", "GASTO_VESTIDO", "GASTO_VIVIENDA_SERVICIOS", "GASTO_SALUD",
              "GASTO_TRANSPORTE", "GASTO_COMUNICACIONES", "GASTO_EDUCACION", "GASTO_OTROS_BIENES"]
# Gastos COMPROMETIDOS (relativamente fijos): entran como ratio al modelo.
COMMITTED = ["GASTO_ALIMENTOS", "GASTO_VIVIENDA_SERVICIOS", "GASTO_TRANSPORTE", "GASTO_SALUD", "GASTO_EDUCACION"]
# Gastos DISCRECIONALES: palanca de la recomendación -> NUNCA son input del modelo.
DISCRETIONARY = ["GASTO_VESTIDO", "GASTO_COMUNICACIONES", "GASTO_OTROS_BIENES"]
ESENCIAL = ["GASTO_ALIMENTOS", "GASTO_VIVIENDA_SERVICIOS", "GASTO_TRANSPORTE"]
INGRESO_COLS = ["ING_PLANILLA", "ING_INFORMAL"]
DEDUP_COLS = INGRESO_COLS + GASTO_COLS

CLASS_LABELS = {0: "Déficit", 1: "Ahorra"}


def clean_dataset(path: str, iqr_factor: float = 2.5, sep: str = ",",
                  dedup_cols=None, verbose: bool = False) -> pd.DataFrame:
    """Limpieza: ingreso>0 + dedup ingresos+gastos + winsorización 1% + IQR(factor) en target y gastos."""
    df = pd.read_csv(path, sep=sep)
    n0 = len(df)
    df = df[df["ING_PLANILLA"] + df["ING_INFORMAL"] > 0].reset_index(drop=True)
    n_ing = len(df)
    df = df.drop_duplicates(subset=(dedup_cols or DEDUP_COLS)).reset_index(drop=True)
    n_dd = len(df)
    df["TARGET_AHORRO"] = winsorize(df["TARGET_AHORRO"], limits=[0.01, 0.01]).data
    mask = pd.Series(True, index=df.index)
    for c in ["TARGET_AHORRO"] + GASTO_COLS:
        q1, q3 = df[c].quantile(0.25), df[c].quantile(0.75)
        iqr = q3 - q1
        mask &= (df[c] >= q1 - iqr_factor * iqr) & (df[c] <= q3 + iqr_factor * iqr)
    df = df[mask].reset_index(drop=True)
    if verbose:
        print(f"crudo={n0} | ingreso>0={n_ing} | sin duplicados={n_dd} | tras IQR(f={iqr_factor})={len(df)}")
    return df


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Crea las features honestas (ratios % ingreso, log, per cápita) + one-hot de TIPO_INGRESO."""
    df = df.copy()
    df["ING_TOTAL"] = df["ING_PLANILLA"] + df["ING_INFORMAL"]
    df["GASTO_ESENCIAL"] = df[ESENCIAL].sum(axis=1)
    # Derivadas solo para EDA / identidad (NUNCA son features del modelo: referential_features no las lista).
    df["GASTO_TOTAL"] = df[GASTO_COLS].sum(axis=1)
    df["CAPACIDAD_BRUTA"] = df["ING_TOTAL"] - df["GASTO_ESENCIAL"]
    df["PRESION_FINANCIERA"] = df["GASTO_ESENCIAL"] / (df["ING_TOTAL"] + 1e-6)
    df["ING_PER_CAPITA"] = df["ING_TOTAL"] / df["MIEMBROS_HOGAR"].clip(lower=1)
    df["COMMIT_PER_CAPITA"] = df[COMMITTED].sum(axis=1) / df["MIEMBROS_HOGAR"].clip(lower=1)
    df["DEPENDE_INFORMAL"] = (df["ING_INFORMAL"] > df["ING_PLANILLA"]).astype(int)
    df["INFORMAL_SHARE"] = df["ING_INFORMAL"] / (df["ING_TOTAL"] + 1e-6)
    df["LOG_ING"] = np.log1p(df["ING_TOTAL"])
    for c in COMMITTED:
        df[c + "_R"] = df[c] / (df["ING_TOTAL"] + 1e-6)
    if "TIPO_INGRESO" in df.columns:
        df = pd.get_dummies(df, columns=["TIPO_INGRESO"], prefix="TIPO")
    return df


def referential_features(df: pd.DataFrame) -> list:
    """Las 19 features honestas presentes en df (sin variables de resta ni discrecionales)."""
    feats = ["NIVEL_EDUC", "MIEMBROS_HOGAR", "DEPENDE_INFORMAL",
             "ING_PLANILLA", "ING_INFORMAL", "LOG_ING", "ING_PER_CAPITA", "INFORMAL_SHARE",
             "PRESION_FINANCIERA", "COMMIT_PER_CAPITA"]
    feats += [c + "_R" for c in COMMITTED]
    if "ESTRATO_SOC" in df.columns:
        feats.append("ESTRATO_SOC")
    feats += [c for c in df.columns if c.startswith("TIPO_")]
    return [f for f in feats if f in df.columns]


def binary_target(df: pd.DataFrame) -> np.ndarray:
    """0 = Déficit (ahorro < 0), 1 = Ahorra (ahorro >= 0)."""
    return (df["TARGET_AHORRO"].values >= 0).astype(int)


# --------------------------------------------------------------------------- #
# Utilidades de inferencia (1 registro de usuario)
# --------------------------------------------------------------------------- #
def ing_total(user: dict) -> float:
    return float(user.get("ING_PLANILLA", 0)) + float(user.get("ING_INFORMAL", 0))


def gasto_total(user: dict) -> float:
    return sum(float(user.get(c, 0)) for c in GASTO_COLS)


def ahorro_identidad(user: dict) -> float:
    """Ahorro real exacto = ingreso total − gasto total (identidad contable)."""
    return ing_total(user) - gasto_total(user)


def build_feature_row(user: dict, features: list) -> pd.DataFrame:
    """
    Construye un DataFrame de 1 fila con EXACTAMENTE las columnas `features` (el orden
    con que se entrenó el modelo), derivadas desde el input crudo del usuario. Las
    one-hot `TIPO_*` y `ESTRATO_SOC` ausentes se rellenan con 0.
    """
    row = dict(user)
    row.setdefault("TARGET_AHORRO", 0.0)
    df = add_features(pd.DataFrame([row]))
    for f in features:
        if f not in df.columns:
            df[f] = 0.0
    return df[features].astype(float)
