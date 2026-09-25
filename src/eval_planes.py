# -*- coding: utf-8 -*-
"""
Evaluacion de los planes de ajuste presupuestario sobre los usuarios en DEFICIT del
conjunto de validacion (20 %, misma particion de train.py, semilla 42).

Cada registro se pasa a recommend() con los mismos campos que envia la aplicacion
(RegistroMensual.to_user_dict): nivel educativo, miembros del hogar, ingresos y las
ocho categorias de gasto. Reporta por plan:
  validez      : % de planes cuyo faltante es 0 (alcanzan el objetivo a*)
  cambia_clase : % de planes que cambian la clase predicha por XGBoost
  proximity    : recorte total / gasto total (media)
  sparsity     : n.º de categorias modificadas (media)
y en global: factibilidad (usuarios con al menos un plan valido), diversidad (L1 media
en soles entre planes de un mismo usuario), tiempo medio y desplazamiento de la
probabilidad predicha.

Uso:   python -m src.eval_planes
Salida: models/planes_eval.json
"""
import json
import time
from itertools import combinations

import numpy as np

from .predict import recommend
from .preprocessing import GASTO_COLS, binary_target, clean_dataset
from .train import _DATASET, _MODELS, _split

CAMPOS_APP = ["NIVEL_EDUC", "MIEMBROS_HOGAR", "ING_PLANILLA", "ING_INFORMAL"] + GASTO_COLS


def main() -> dict:
    df = clean_dataset(str(_DATASET), iqr_factor=2.5)
    y = binary_target(df)
    _, te = _split(y)
    deficit = df.iloc[te][y[te] == 0]

    por_plan, feasible, tiempos, divers, dprob = {}, 0, [], [], []
    for _, row in deficit.iterrows():
        u = {c: float(row[c]) for c in CAMPOS_APP}
        t0 = time.perf_counter()
        out = recommend(u)
        tiempos.append((time.perf_counter() - t0) * 1000)
        opciones = out.get("opciones", [])
        feasible += int(any(o["alcanza_meta"] for o in opciones))
        gasto = sum(u[c] for c in GASTO_COLS)
        p0 = out["clase_actual"]["probabilidad_ahorra"]
        c0 = out["clase_actual"]["clase"]
        for o in opciones:
            d = por_plan.setdefault(o["nombre"], {"n": 0, "val": 0, "cambia": 0, "prox": [], "spars": []})
            d["n"] += 1
            d["val"] += int(o["alcanza_meta"])
            d["cambia"] += int(int(o["prob_ahorra_modelo"] >= 0.5) != c0)
            d["prox"].append(o["reduccion_total"] / max(gasto, 1e-6))
            d["spars"].append(len(o["reducciones"]))
            dprob.append(o["prob_ahorra_modelo"] - p0)
        for a, b in combinations(opciones, 2):
            divers.append(sum(abs(a["gastos_optimizados"][c] - b["gastos_optimizados"][c]) for c in GASTO_COLS))

    n = len(deficit)
    rep = {
        "n_usuarios_deficit_valid": int(n),
        "n_planes": int(sum(v["n"] for v in por_plan.values())),
        "planes_que_cambian_clase": int(sum(v["cambia"] for v in por_plan.values())),
        "feasibility_pct": round(100 * feasible / max(n, 1), 1),
        "diversity_L1_soles": round(float(np.mean(divers)), 2) if divers else None,
        "tiempo_ms_medio": round(float(np.mean(tiempos)), 1),
        "delta_prob_media": round(float(np.mean(dprob)), 3),
        "delta_prob_max": round(float(np.max(dprob)), 3),
        "delta_prob_min": round(float(np.min(dprob)), 3),
        "por_plan": {k: {"n": v["n"],
                         "validez_pct": round(100 * v["val"] / v["n"], 1),
                         "cambia_clase_pct": round(100 * v["cambia"] / v["n"], 1),
                         "proximity_media": round(float(np.mean(v["prox"])), 3),
                         "sparsity_media": round(float(np.mean(v["spars"])), 2)}
                     for k, v in por_plan.items()},
    }
    with open(_MODELS / "planes_eval.json", "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return rep


if __name__ == "__main__":
    main()
