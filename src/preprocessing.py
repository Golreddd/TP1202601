"""
Módulo de preprocesamiento para el sistema de recomendación de ahorro financiero.
Contiene funciones para carga, limpieza e ingeniería de características.
"""

import pandas as pd
import numpy as np
from scipy.stats.mstats import winsorize


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


def _remove_iqr_outliers(df: pd.DataFrame, cols: list, factor: float = 3.0) -> pd.DataFrame:
    """Elimina filas con valores atípicos según el método IQR con un factor dado."""
    mask = pd.Series([True] * len(df), index=df.index)
    for col in cols:
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lower = q1 - factor * iqr
        upper = q3 + factor * iqr
        mask &= (df[col] >= lower) & (df[col] <= upper)
    return df[mask].reset_index(drop=True)


def load_and_clean(path: str) -> pd.DataFrame:
    """
    Carga el CSV, aplica winsorización a TARGET_AHORRO, elimina filas con
    ingreso total <= 0 y detecta/elimina outliers con IQR factor 3.0.

    Parámetros
    ----------
    path : str
        Ruta al archivo CSV del dataset.

    Retorna
    -------
    pd.DataFrame
        Dataset limpio con índice reiniciado.
    """
    df = pd.read_csv(path)

    # Winsorización al 1% en ambas colas sobre TARGET_AHORRO
    df["TARGET_AHORRO"] = winsorize(df["TARGET_AHORRO"], limits=[0.01, 0.01]).data

    # Eliminar filas donde el ingreso total es <= 0
    df = df[df["ING_PLANILLA"] + df["ING_INFORMAL"] > 0].reset_index(drop=True)

    # Eliminar outliers con IQR factor 3.0 sobre TARGET_AHORRO y columnas GASTO
    outlier_cols = ["TARGET_AHORRO"] + GASTO_COLS
    df = _remove_iqr_outliers(df, outlier_cols, factor=3.0)

    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crea características derivadas para los modelos de clustering y regresión.

    Características generadas:
    - ING_TOTAL, GASTO_TOTAL, RATIO_AHORRO, RATIO_GASTO_ING
    - DEPENDE_INFORMAL, GASTO_PER_CAPITA
    - GASTO_ESENCIAL, GASTO_DISCRECIONAL
    - PRESION_FINANCIERA, CAPACIDAD_BRUTA

    Parámetros
    ----------
    df : pd.DataFrame
        DataFrame con las columnas originales del dataset.

    Retorna
    -------
    pd.DataFrame
        DataFrame con las nuevas columnas añadidas.
    """
    df = df.copy()

    df["ING_TOTAL"] = df["ING_PLANILLA"] + df["ING_INFORMAL"]
    df["GASTO_TOTAL"] = df[GASTO_COLS].sum(axis=1)

    # Evitar división por cero (no debería ocurrir tras load_and_clean)
    safe_ing = df["ING_TOTAL"].replace(0, np.nan)

    df["RATIO_AHORRO"] = df["TARGET_AHORRO"] / safe_ing
    df["RATIO_GASTO_ING"] = df["GASTO_TOTAL"] / safe_ing
    df["DEPENDE_INFORMAL"] = (df["ING_INFORMAL"] > df["ING_PLANILLA"]).astype(int)
    df["GASTO_PER_CAPITA"] = df["GASTO_TOTAL"] / df["MIEMBROS_HOGAR"].replace(0, 1)

    df["GASTO_ESENCIAL"] = (
        df["GASTO_ALIMENTOS"]
        + df["GASTO_VIVIENDA_SERVICIOS"]
        + df["GASTO_TRANSPORTE"]
    )
    df["GASTO_DISCRECIONAL"] = (
        df["GASTO_VESTIDO"]
        + df["GASTO_OTROS_BIENES"]
        + df["GASTO_COMUNICACIONES"]
    )

    df["PRESION_FINANCIERA"] = df["GASTO_ESENCIAL"] / safe_ing
    df["CAPACIDAD_BRUTA"] = df["ING_TOTAL"] - df["GASTO_ESENCIAL"]

    # Rellenar NaN producidos por divisiones (raro tras filtro de ingreso)
    df = df.fillna(0)

    return df


def get_feature_sets() -> dict:
    """
    Retorna los conjuntos de características usados por cada modelo.

    Retorna
    -------
    dict con claves:
        - kmeans_features: columnas para K-Means clustering
        - xgb_features: columnas para XGBoost (incluye CLUSTER)
        - gasto_cols: columnas de gasto originales
    """
    kmeans_features = [
        "ING_TOTAL",
        "GASTO_TOTAL",
        "RATIO_AHORRO",
        "RATIO_GASTO_ING",
        "DEPENDE_INFORMAL",
        "GASTO_PER_CAPITA",
        "GASTO_ESENCIAL",
        "GASTO_DISCRECIONAL",
        "PRESION_FINANCIERA",
        "CAPACIDAD_BRUTA",
        "EDAD",
        "NIVEL_EDUC",
        "MIEMBROS_HOGAR",
    ]

    xgb_features = [
        "EDAD",
        "NIVEL_EDUC",
        "MIEMBROS_HOGAR",
        "ING_PLANILLA",
        "ING_INFORMAL",
        "ING_TOTAL",
        "GASTO_TOTAL",
        "RATIO_AHORRO",
        "RATIO_GASTO_ING",
        "DEPENDE_INFORMAL",
        "GASTO_PER_CAPITA",
        "GASTO_ESENCIAL",
        "GASTO_DISCRECIONAL",
        "PRESION_FINANCIERA",
        "CAPACIDAD_BRUTA",
        "GASTO_ALIMENTOS",
        "GASTO_VESTIDO",
        "GASTO_VIVIENDA_SERVICIOS",
        "GASTO_SALUD",
        "GASTO_TRANSPORTE",
        "GASTO_COMUNICACIONES",
        "GASTO_EDUCACION",
        "GASTO_OTROS_BIENES",
        "CLUSTER",
    ]

    return {
        "kmeans_features": kmeans_features,
        "xgb_features": xgb_features,
        "gasto_cols": GASTO_COLS,
    }
