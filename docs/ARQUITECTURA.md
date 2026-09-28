# Arquitectura de SIGAMOS (SmartSave)

Este documento describe cómo está organizado el sistema y por qué, como
referencia para la memoria de tesis y para cualquier persona que se incorpore
al proyecto. No sustituye a los docstrings del código (que documentan el
"cómo" de cada función); aquí se explica el "cómo se relacionan las partes".

## 1. Visión general

El sistema tiene dos mitades con responsabilidades distintas:

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│   Aplicación web (Django)   │        │  Pipeline de ML (src/)        │
│                              │        │  independiente de Django      │
│  accounts · financiero       │──────▶│  src/pipeline/                │
│  recomendaciones · gamificacion│ solo  │    preprocessing · train      │
│  panel_admin · api          │ import │    predict (inferencia +      │
│                              │        │    motor de recomendación)    │
└─────────────────────────────┘        │  src/research/                │
                                        │    scripts de validación para │
                                        │    la tesis/paper (no los usa │
                                        │    la app en producción)      │
                                        └──────────────────────────────┘
```

Django nunca reentrena el modelo: solo importa `src.pipeline.predict` para
clasificar y generar recomendaciones sobre los artefactos ya entrenados en
`models/`. El código de `src/` no importa nada de Django — se puede ejecutar
de forma standalone (`python -m src.pipeline.train`) para reproducir el
entrenamiento o los análisis del paper.

## 2. Apps Django y su responsabilidad

| App | Responsabilidad |
|---|---|
| `accounts` | Usuario (autenticación + perfil financiero embebido) y Rol (RBAC) |
| `financiero` | Registro mensual de ingresos/gastos; identidad contable ahorro = ingreso − gasto; asistente de voz (`voz.py`/`voz_servicios.py`, ver §7) |
| `recomendaciones` | Metas de ahorro, orquestación del modelo ML (`ResultadoML`) y planes de recorte counterfactual |
| `gamificacion` | Rachas, catálogo de logros y seguimiento de progreso/presupuesto |
| `panel_admin` | Auditoría administrativa y validación externa del modelo (contraste predicción vs. resultado real) |
| `api` (`api/v1`) | Misma funcionalidad de negocio expuesta como API REST (DRF + JWT), para clientes externos |
| `core` | Utilidades transversales sin modelos propios: permisos DRF, manejo de excepciones, constantes |

`sigamos/` es el paquete de configuración (settings, urls raíz, wsgi), no una
app de negocio.

## 3. Flujo de un análisis ML (extremo a extremo)

1. El usuario registra un mes en `financiero.RegistroMensual`.
2. Desde `recomendaciones` (vista web) o `api.v1.views.recomendaciones` (API),
   se construye un `user_dict` con `RegistroMensual.to_user_dict()`.
3. `recomendaciones.ResultadoML.recomputar()` (o el equivalente en la vista de
   API) llama a `src.pipeline.predict`:
   - `classify(user_dict)` → perfil (Déficit / Ahorra) + probabilidad.
   - `shap_explain(user_dict)` → variables que más explican la clasificación.
   - `recommend(user_dict, meta, ...)` → plan de recorte counterfactual sobre
     el presupuesto real (nunca sobre las variables internas del modelo).
4. El contexto multi-mes (tendencia, anti-estatismo, candidatos de meta) lo
   calcula `recomendaciones.analitica` — son datos que dependen de la base de
   datos (historial del usuario) y que `src/pipeline/predict.py` no puede
   conocer por sí solo, al ser agnóstico de Django.
5. `gamificacion` y `panel_admin` leen el resultado ya persistido
   (`ResultadoML`, `RegistroMensual`) para logros y para la validación
   externa del modelo, respectivamente; no vuelven a invocar el pipeline ML.

## 4. Pipeline ML: producción vs. investigación

`src/` está dividido en dos subpaquetes con ciclos de vida distintos:

- **`src/pipeline/`** — código de producción, consumido por Django:
  `preprocessing.py` (limpieza y features), `train.py` (entrenamiento,
  protocolo 80/20 estricto) y `predict.py` (inferencia + motor de
  recomendación). `train.py` es la única fuente de verdad de las rutas
  (`models/`, `data/`); los demás módulos las reutilizan en vez de
  recalcularlas.
- **`src/research/`** — scripts que **no** ejecuta la aplicación: se corren
  manualmente para producir las tablas y figuras de la tesis/paper
  (`ablation.py`, `eval_planes.py`, `stats_tests.py`,
  `analisis_validacion.py`, `umbral_segmento.py`). Todos leen el modelo de
  producción de `models/` y escriben sus resultados en
  `models/investigacion/`, sin tocar los artefactos de producción.

## 5. Datos y artefactos

- `data/` — datasets fuente (CSV) usados solo por `src/pipeline/train.py` y
  `src/research/ablation.py`. No los usa la aplicación en producción.
- `models/` (raíz) — artefactos que carga Django en tiempo de ejecución:
  modelo (`xgb_clf_model.pkl`), `scaler.pkl`, `shap_explainer.pkl` y los
  metadatos que los acompañan (`features.json`, `metrics.json`,
  `xgb_best_params.json`).
- `models/investigacion/` — salidas de `src/research/*`: no las lee ningún
  código de Django, existen únicamente como evidencia metodológica.

## 6. Limitaciones de diseño conocidas

Documentadas aquí en vez de "corregidas silenciosamente", para que la
memoria de tesis pueda discutirlas si corresponde:

- **Imports diferidos entre apps.** `accounts`, `financiero`, `gamificacion`,
  `recomendaciones` y `api` importan modelos de otras apps *dentro* de
  funciones (no al nivel de módulo) para evitar dependencias circulares
  reales entre ellas. Es una solución pragmática, no una separación de capas
  estricta.
- **Lógica de negocio en vistas.** Algunas vistas extensas
  (`financiero.views`, `panel_admin.views`) combinan lógica HTTP con cálculo
  de negocio, a diferencia de `gamificacion`, que sí aísla parte de esa
  lógica en `services.py`. Se documenta como observación de diseño, sin
  reorganizarlo, para no alterar el comportamiento existente.

## 7. Asistente de voz ("🎤 Habla con SmartSave")

Permite registrar ingresos/gastos y hacer preguntas financieras por voz (o
texto) desde el dashboard. Sin dependencias externas de pago: la
transcripción la hace el navegador (Web Speech API) y la interpretación es
un parser de reglas en Python puro, no un LLM.

```
Navegador (static/js/voz.js)
  SpeechRecognition (es-PE) ── texto ──▶ POST /api/v1/voz/interpretar/
                                              │
                                    financiero/voz.py (interpretar)
                                    puro Python, sin Django ni BD:
                                    normaliza, detecta monto/categoría/
                                    tipo de ingreso, pregunta o simulación
                                              │
                              ¿registro completo?      ¿es pregunta?
                                    │                        │
                    financiero/voz_servicios.py    financiero/voz_servicios.py
                    .previsualizar() (impacto          .responder()
                    en el plan, sin guardar)      (gasto/ingreso/ahorro/
                                    │              presupuesto/comparación)
                                    ▼
                     Usuario confirma → POST /voz/confirmar/
                     .aplicar(): suma al RegistroMensual del mes actual,
                     actualiza Racha y logros (MANOS_LIBRES/ASISTENTE_FIEL),
                     devuelve un token firmado (django.core.signing) para
                     poder deshacer — no se guarda ni el audio ni el texto.
```

Decisiones de diseño relevantes:

- **Todo gasto se asocia a una de las 8 categorías** de `RegistroMensual`
  (nunca se guarda un monto "suelto"): si la frase no la trae, la API
  devuelve `faltante` y el frontend pregunta solo ese dato — el turno
  siguiente se interpreta concatenado con el anterior (`contexto_previo`),
  sin guardar estado de conversación en el servidor.
- **"Actualizar el plan" no re-ejecuta el modelo ML.** El ML se entrena y
  evalúa sobre meses cerrados; sumar un gasto a mitad de mes no amerita
  reclasificar. En su lugar, `voz_servicios.previsualizar()` muestra el
  impacto del gasto sobre el presupuesto por categoría del plan activo
  (`recomendaciones.analitica.presupuesto_por_categoria`, la misma función
  que usa Progreso), con aviso y sugerencia de compensación si excede.
- **La API de voz no confía en el cliente**: `/voz/confirmar/` vuelve a
  validar categoría/tipo y monto (`api/v1/serializers/voz.py`) aunque el
  cliente ya los haya recibido de `/voz/interpretar/`.

## 8. Cómo evolucionar este documento

Si agregas una funcionalidad grande y con decisiones de diseño propias
(como el asistente de voz), documenta aquí el flujo y el porqué de las
decisiones no obvias — no solo el "qué hace el código", que ya está en los
docstrings.
