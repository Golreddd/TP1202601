# CHANGELOG — SmartSave / SIGAMOS

Registro explícito de todos los cambios hechos en esta sesión de trabajo, organizados por tema. Para cada uno: qué cambió, en qué archivos, y por qué.

> **Nota de alcance:** este documento cubre solo lo desarrollado en esta conversación. El repositorio tiene además otros cambios pendientes (panel de "Validación ML" en `panel_admin`, reentrenamiento del modelo en `src/train.py`, artefactos `.pkl` actualizados) que se hicieron fuera de esta sesión y no se detallan aquí porque no tengo visibilidad completa de esos cambios.

---

## 1. Tarea 5 — Fecha límite de meta: mes en vez de día exacto

**Archivos:** `recomendaciones/forms.py`, `recomendaciones/views.py`

- `MetaLargoPlazoForm.fecha_limite` dejó de ser un `<input type="date">` (día exacto) y pasó a ser un `<input type="month">`, replicando el mismo patrón que ya usaba `RegistroMensualForm.periodo`.
- Se agregó `clean_fecha_limite()`: parsea `"YYYY-MM"` → `date(year, month, 1)`; devuelve `None` si el campo viene vacío; lanza `ValidationError` si el formato es inválido.
- El modelo **no cambió** — sigue siendo un `DateField`, solo que ahora siempre se guarda con día = 1, porque todo el seguimiento de la meta (`meses_restantes`, `cuota_mensual_sugerida`, `desviacion_plazo`) ya razonaba en meses, nunca en días.
- `meta_update` ahora pasa `initial={'fecha_limite': meta.fecha_limite.strftime('%Y-%m')}` al instanciar el formulario en el GET, igual que ya hacía `registro_update` con `periodo`.
- No requirió migración.

---

## 2. Tarea 1 — Catálogo de logros ampliado (13 logros nuevos)

**Archivos:** `gamificacion/services.py`, `gamificacion/migrations/0009_seed_logros_ampliados.py` (nueva), `recomendaciones/trends.py`

Antes de tocar código se refactorizó la lógica de "¿cumple el usuario su plan activo?" que vivía duplicada dentro de la vista `gamificacion/views.py::progreso`, extrayéndola a dos funciones nuevas y reutilizables en `recomendaciones/trends.py`:

- `mes_inicio_plan(plan_activo)` — desde qué mes se empieza a evaluar un plan.
- `comparacion_plan(usuario, plan_activo)` — la comparación mes a mes de ahorro real vs. objetivo del plan (10% de tolerancia), ahora consumida tanto por la vista de Progreso como por los logros nuevos, sin duplicar el umbral en dos lugares.

Logros nuevos agregados vía migración de datos (`orden` 15–27, sin tocar ningún código de logro existente):

| Código | Nombre | Contexto que lo dispara | Condición |
|---|---|---|---|
| `DIEZ_REGISTROS` | Diez Registros | `registro` | ≥10 registros mensuales |
| `VEINTE_REGISTROS` | Veinte Registros | `registro` | ≥20 registros |
| `CINCUENTA_REGISTROS` | Cincuenta Registros | `registro` | ≥50 registros |
| `RACHA_60` | Racha de 60 días | `registro` | `dias_consecutivos` ≥60 |
| `RACHA_90` | Racha de 90 días | `registro` | `dias_consecutivos` ≥90 |
| `CINCO_ML` | Analista Financiero | `ml` | ≥5 análisis ejecutados |
| `DIEZ_ML` | Analista Experto | `ml` | ≥10 análisis |
| `PRIMER_PLAN` | Primer Plan Adoptado | `registro`, `ml` | Existe algún `PlanSeleccionado` histórico |
| `PLAN_3_MESES` | Constancia de Plan | `registro`, `ml` | 3 meses consecutivos cumpliendo el plan activo (`_racha_plan_cumplido`, nueva función en `services.py`) |
| `META_MITAD` | A Mitad de Camino | `meta_completada` | Alguna meta activa con avance ≥50% y no completada |
| `TRES_METAS_ACTIVAS` | Múltiples Objetivos | `meta_completada` | ≥3 metas largo plazo activas a la vez |
| `APORTE_A_META` | Primer Aporte | `meta_completada` | Existe algún `AporteMeta` del usuario |
| `APORTES_CONSTANTES` | Aportante Constante | `meta_completada` | Aportó en 3 meses distintos consecutivos (`_racha_aportes_consecutivos`, nueva función) |

**Decisión de diseño relevante:** `PRIMER_PLAN` y `PLAN_3_MESES` no tienen un disparador dedicado en `ElegirPlanView` (la API que crea el `PlanSeleccionado`) — se evalúan de forma pasiva leyendo el historial existente, bajo los contextos `registro`/`ml` que ya se disparan en cada uso normal de la app. Esto evitó tener que modificar `api/v1/views/recomendaciones.py`.

---

## 3. Tarea 2 — Aportar el ahorro del mes a metas de ahorro

**Archivos nuevos:** `recomendaciones/migrations/0008_aportemeta.py`, `templates/financiero/distribuir_ahorro.html`, `templates/recomendaciones/meta_detalle.html`
**Archivos modificados:** `recomendaciones/models.py`, `financiero/views.py`, `financiero/urls.py`, `recomendaciones/views.py`, `recomendaciones/urls.py`, `templates/recomendaciones/metas.html`

- **Modelo nuevo `AporteMeta`** (`recomendaciones/models.py`): `usuario`, `meta` (FK a `MetaLargoPlazo`, CASCADE), `registro` (FK a `RegistroMensual`, CASCADE), `monto` (`DecimalField`, mínimo S/ 0.01), `creado_en`. Auditable: un registro por cada aporte, sin recalcular nada al vuelo.
- **Flujo en `registro_create`**: si el registro recién guardado cierra con `ahorro_bruto > 0` y el usuario tiene metas activas, en vez de ir directo a la lista se redirige a la nueva vista `financiero:distribuir_ahorro/<registro_id>/`.
- **`distribuir_ahorro`** (vista + template nuevos): muestra una fila por meta activa con un campo de monto (validado en servidor: la suma no puede superar el ahorro del mes); al confirmar crea un `AporteMeta` por cada monto > 0, incrementa `MetaLargoPlazo.monto_actual`, y dispara `verificar_y_otorgar_logros(usuario, 'meta_completada')`. Incluye botón "Omitir por ahora" (opcional, nunca obligatorio).
- **`registro_delete`**: antes de borrar el registro, revierte (resta, sin bajar de 0) el monto de cada `AporteMeta` afectado en su meta correspondiente, con mensaje informativo del total revertido. Los `AporteMeta` se autoeliminan por `on_delete=CASCADE`.
- **`registro_update`**: si el registro ya tenía aportes repartidos, muestra un `messages.warning` no bloqueante (vía `_avisar_si_tiene_aportes`, factorizada como helper reutilizable) con enlaces a cada meta afectada — **no** edita nada automáticamente. Esto se disparaba originalmente en el GET del formulario; se corrigió para que dispare **después de guardar exitosamente el POST**, que es como lo especificaba el diseño original.
- **Vista nueva `meta_detalle`** (`recomendaciones:meta_detalle`, `/recomendaciones/metas/<pk>/`): muestra los datos de la meta y una tabla de sus aportes ordenada por `-registro__periodo`.
- **`metas.html`**: cada tarjeta de meta ganó un botón explícito "👁️ Ver Detalle" junto a Editar/Eliminar (inicialmente se había hecho clickeable solo el nombre, pero no era lo bastante visible).

---

## 4. Tarea 3 — Alertas de presupuesto en Progreso Financiero

**Archivos:** `gamificacion/views.py`, `templates/gamificacion/progreso.html`

Se agregó el contexto `alerta_presupuesto` a la vista `progreso`, construido **sin recalcular** ninguna regla ya existente — reutiliza tal cual `presupuesto_categorias` y `comparacion_plan`:

1. Si ninguna categoría está excedida → sin alerta (como antes).
2. Si hay categorías excedidas y el mes **sí** cumplió el objetivo del plan → alerta suave (verde): *"Te pasaste en X pero lo compensaste en otras y aun así alcanzaste tu meta."*
3. Si hay excedidas y el mes **no** cumplió el objetivo:
   - Si lo disponible en otras categorías cubre el exceso → mensaje neutral (naranja) explicando que el faltante no viene de esas categorías.
   - Si no lo cubre → alerta fuerte (roja) con el monto exacto que faltó y un enlace para regenerar el plan desde ML Insights.

Se actualizó/quitó el texto fijo "Solo es referencia: no genera alertas ni notificaciones", que ya no era cierto.

---

## 5. Análisis de Gastos — reversión de un cambio previo + selector de categoría

**Archivos:** `financiero/views.py`, `templates/financiero/analisis.html`

Un cambio anterior de esta misma sesión (selector de meses específicos por checkbox + gráfico de barras adicional) se **revirtió por completo** a pedido del usuario, restaurando `analisis()` y el template a su versión previa (verificado byte a byte contra el `git show HEAD` del último commit). En su lugar se agregó algo más simple y directo:

- Un `<select>` sobre el gráfico "Tendencia Mensual de Gastos" con la opción "Total" + las 8 categorías de gasto.
- La vista ahora calcula `gastos_categoria_series`: un diccionario `{categoría: [monto por mes]}` para la ventana de meses vigente.
- Al elegir una categoría, un script en el cliente cambia el dataset del gráfico Chart.js para mostrar esa categoría mes a mes en vez del gasto total — sin recargar la página.

---

## 6. ML Insights — menú de metas suma todas las metas activas

**Archivo:** `recomendaciones/trends.py` (función `candidatos_meta`)

Antes, si el usuario tenía varias metas de largo plazo con fecha límite, el menú de "meta sugerida" solo tomaba la de fecha más próxima e ignoraba las demás. Ahora se **suma** la cuota mensual sugerida de todas las metas activas con fecha límite, y el nombre del candidato lista todas ("Meta: Casa De Lujo y Chimbote"). Si solo hay una meta, el comportamiento es idéntico al anterior.

---

## 7. ML Insights — recomendación suave para perfil deficitario

**Archivo:** `src/predict.py` (motor de recomendaciones), `api/v1/serializers/recomendaciones.py`, `recomendaciones/views.py`, `templates/recomendaciones/ml_insights.html`

Cambios en la regla de objetivo (`_plan_objetivo`), acotados **solo** a las ramas que involucran al perfil deficitario y al override del perfil ahorrador en déficit — el resto del motor (modelo, entrenamiento, cálculo SHAP) no se tocó:

- **Nueva función `objetivo_suave_deficitario(user)`**: para perfil deficitario con ahorro real ≥ 0, calcula una meta "suave" — si ya ahorra más del 5% de su ingreso, la meta pasa a ser el 10% del ingreso; si ahorra 5% o menos, la meta es su ahorro actual + un paso del 5%. Siempre queda estrictamente por encima de lo que ya ahorra.
- Sin elección explícita del usuario, un perfil deficitario en verde avanza automáticamente por este escenón `suave_10` (antes usaba escalamiento ×1.25 o incremental, más exigentes para este perfil). El menú de metas en ML Insights le muestra la tarjeta "🌱 Ahorro suave" en vez de "20% de tu ingreso", preseleccionada.
- **Override de perfil ahorrador con déficit leve** (`deficit_leve_override`, ≤5% del ingreso): antes proponía volver a 0 (equilibrio) sin más. Ahora, como el perfil tiende a ahorrar, propone directamente el 10% del ingreso.
- **`recommend()`**: para perfil deficitario, la estrategia recomendada es **siempre** la más suave (Suave), alcance o no toda la meta — antes se recomendaba la primera que sí alcanzaba la meta, lo que para este perfil solía terminar en el plan Decidido.
- Se agregó `'suave_10'` a los valores válidos de `alternativa` en el serializer de la API.

---

## 8. ML Insights — sección de factores (SHAP) más accionable

**Archivos:** `templates/recomendaciones/_resultado_ml.html`, `templates/recomendaciones/_resultado_ml_js.html`

- Se quitaron del bloque de perfil los dos textos redundantes ("Esto NO es el resultado exacto del mes…" y "Resultado real de ese mes (ingreso − gasto): …"), porque esa cifra ya está en la tarjeta grande "Ahorro Real" de abajo.
- El gráfico de factores pasó de mostrar *log-odds* (ilegible para el usuario) a mostrar **% de impacto**, con los factores accionables primero.
- **Nuevo bloque "🔑 Tu mayor palanca este mes"**: una frase resumen sobre el gráfico señalando el factor de mayor peso que el usuario sí puede mover.
- **Nuevo bloque "🎯 incentivo"**: muestra cuánto sube la probabilidad de ahorrar si aplica el plan recomendado (el dato ya se calculaba por plan vía `prob_ahorra_modelo`, solo no se mostraba).
- Bajo cada factor optimizable del glosario, se agregó la acción concreta en soles: a cuánto lo baja el plan recomendado ("el plan Suave lo baja de S/ 120 a S/ 90").

---

## 9. Registros Mensuales — nueva acción "Agregar" montos extra

**Archivos nuevos:** `templates/financiero/registro_agregar.html`
**Archivos modificados:** `financiero/views.py`, `financiero/urls.py`, `templates/financiero/registro_list.html`

- Nueva vista `registro_agregar` (`/financiero/registros/<pk>/agregar/`): formulario con los 3 campos de ingreso y las 8 categorías de gasto, todos vacíos por defecto, que representan montos **a sumar** sobre lo que el registro ya tiene — no lo reemplazan.
- Valida que los montos extra no sean negativos (si el usuario quiere corregir un valor, se le indica usar "Editar").
- Si el registro ya tenía aportes repartidos a metas, reutiliza `_avisar_si_tiene_aportes` para el mismo aviso no bloqueante que usa "Editar".
- Se agregó el botón "➕ Agregar" en la tabla de Mis Registros Mensuales, junto a Editar y Eliminar.

---

## 10. Validación: no se pueden registrar meses futuros

**Archivos:** `financiero/forms.py`, `api/v1/serializers/financiero.py`

- `RegistroMensualForm`: el `<input type="month">` de período ahora tiene el atributo `max` fijado al mes actual (bloquea la selección en el calendario nativo del navegador), y `clean_periodo` rechaza con un `ValidationError` cualquier período posterior al mes en curso — esta es la validación real, no solo la de UI.
- Se replicó la misma regla en `RegistroMensualSerializer.validate_periodo` de la API, para que tampoco se pueda hacer vía API.
- Aplica tanto a crear como a editar (mismo formulario en ambos casos).

---

## 11. Dashboard — rediseño completo

**Archivos:** `templates/financiero/dashboard.html`, `financiero/views.py`, `static/css/sigamos.css`, `templates/base.html`

### Vista (`financiero/views.py::dashboard`)
Se agregó el cálculo de `avance_meta`: compara el ahorro real del último registro contra la `meta_validada` del último análisis ML (sin recalcular ninguna regla del motor, solo lee lo que ya resolvió), y arma un diccionario con `meta`, `ahorro`, `falta`, `pct` (limitado a 100) y un `estado` (`cumplida` / `cerca` / `lejos` / `deficit`) con su mensaje correspondiente.

### Template
- Se agregó un tercer gráfico, **Tendencia Mensual de Gastos**, junto a los ya existentes de Ingresos vs Gastos y Distribución de Gastos.
- Nueva tarjeta **"🎯 Mis Metas de Ahorro"**: hasta 3 metas activas con su barra de avance y porcentaje, en formato compacto.
- Nueva tarjeta **"💡 Tu Meta de Este Mes"**: monto a ahorrar, porcentaje ya alcanzado, barra de progreso y el mensaje de `avance_meta`.
- Se mantuvieron las 4 tarjetas KPI originales (Ingreso Mensual, Gastos del Mes, Ahorro Actual, Registros Totales).
- **Todo el dashboard es ahora interactivo**: cada tarjeta y cada gráfico es un enlace (`class="dash-link"`) a la pantalla donde ese dato se analiza a fondo (Mis Registros, Análisis de Gastos, Progreso Financiero, Metas de Ahorro, ML Insights).
- Se agregó la clase `.dash` que compacta paddings, alturas de gráfico y separaciones **solo dentro del dashboard**, para que todo el contenido entre en una pantalla sin necesidad de scroll; el resto de las vistas del sistema no se vio afectado.

### CSS (`static/css/sigamos.css`)
- **`.btn-primary` dejó de forzar `width:100%`** — esa regla hacía que "+ Nuevo Registro", "+ Nueva Meta" y botones similares se estiraran a todo el ancho de su contenedor como una franja. Ahora ese ancho completo se pide explícitamente con la clase `.btn-full`, que sí se mantuvo en los formularios de login/registro/recuperación de contraseña (`templates/accounts/*.html`), donde el botón de ancho completo es correcto.
- `.page-header .btn{width:auto;flex:0 0 auto;white-space:nowrap;}` — refuerzo para que el botón de cualquier cabecera de página quede siempre del tamaño de su texto y pegado a la derecha.
- `.dash-link, .dash-link *{text-decoration:none;}` — quita el subrayado por defecto del navegador en todo el contenido de una tarjeta clickeable, no solo en el enlace exterior.
- Nuevas clases: `.dash-meta-row`, `.dash-meta-ico`, `.dash-meta-txt`, `.dash-meta-nom`, `.dash-meta-pct`, `.dash-meta-bar` — para el formato compacto de fila de meta usado en la tarjeta "Mis Metas de Ahorro".

### Invalidación de caché
`templates/base.html` sirve el CSS como `sigamos.css?v=N`. Se subió la versión (`v=5` → `v=6`) para forzar a los navegadores a descargar la hoja de estilos actualizada — sin este paso, los cambios de CSS no se reflejaban aunque el archivo ya estuviera corregido en el servidor.

---

## 12. Migraciones nuevas

| Migración | Qué hace |
|---|---|
| `recomendaciones/migrations/0008_aportemeta.py` | Crea la tabla `recomendaciones_aportemeta` (modelo `AporteMeta`). Aditiva, sin tocar datos existentes. |
| `gamificacion/migrations/0009_seed_logros_ampliados.py` | Migración de datos (`RunPython`): inserta los 13 logros nuevos en la tabla `Logro` vía `get_or_create`, con reversa que los elimina por código. |

Ambas se aplicaron y verificaron contra la base de datos de producción en Render (`sigamos_db_hn6u`).

---

## 13. Despliegue

- Commit `d0f47cf` — *"feat: gamificacion ampliada, aportes a metas, mejoras en ML Insights y validaciones"* — agrupa los puntos 1 a 10 de este changelog (25 archivos, +1102/-215 líneas).
- Push a `origin/main` en GitHub, lo que disparó el auto-deploy en Render: el `buildCommand` de `render.yaml` corre `migrate --no-input` automáticamente, así que las dos migraciones nuevas se aplicaron solas en producción.
- Los cambios del punto 11 (Dashboard) y las correcciones de caché de CSS **aún no se han commiteado** — quedan pendientes de tu confirmación para el próximo push.

---

## 14. Trabajo de análisis para la tesis (no afecta el sistema en producción)

- **`src/stats_tests.py`**: corregido para usar `dataset_final_limpio.csv` (el dataset ya limpio, con `n_total=9527` idéntico al de `models/metrics.json`) sin volver a aplicarle `clean_dataset()` — aplicarlo dos veces lo sobre-filtraba a 6950 filas y dejaba de coincidir con el split real del modelo entrenado. Se ejecutó: intervalos de confianza al 95% (bootstrap) de las 3 modelos, test de DeLong (XGBoost vs. Regresión Logística: diferencia de AUC significativa, p=0.013; vs. Random Forest: no significativa), test de McNemar y bootstrap pareado de F1. Resultado en `models/stats_tests.json`.
- **`src/ablation.py`** (`(1).py`, ejecutado vía copia temporal por el nombre con espacios): estudio de ablación por bloques de variables (Tabla IV del paper). Confirma que las 19 features "honestas" del modelo no filtran la identidad contable ingreso−gasto: el contraste con variables de fuga salta a 98.3% de accuracy / AUC 0.998, una brecha de 17.1 puntos porcentuales sobre el modelo final (81.2% accuracy). Resultado en `models/ablation.json`.
- **20 usuarios de validación simulados**, generados a partir de `Validaciones.xlsx` (tasas de ahorro reales de la simulación) y cargados directamente en la base de producción de Render: nombres peruanos, perfiles variados (formal/mixto/informal), 3 registros mensuales cada uno (jun–ago 2026) con análisis ML ejecutado mes a mes (no todo de una vez, para que el motor viera solo el historial real de cada momento), metas de ahorro con sus aportes, y logros otorgados por la lógica real del sistema. Verificado que las tasas de ahorro guardadas coinciden exactamente con el Excel.

---

## 15. Documentación del proyecto (Excel)

Tres archivos regenerados, todos derivados de una única fuente de verdad construida en esta sesión (`hu_data.py`, script auxiliar) para garantizar que estén sincronizados entre sí:

- **`P20261039_Historias de Usuarios_Criterios de Aceptación_ACTUALIZADO.xlsx`**: 104 HU (82 corregidas + 22 nuevas), 193 escenarios. Se corrigieron 25 historias que tenían "Sistema" como rol (violaba el instructivo de la plantilla) y varios desajustes con el sistema real (categoría "entretenimiento" que no existe, K-Means ya reemplazado por el clasificador binario, condición real del aviso de plan desactualizado, guardas reales del endpoint de cambio de rol).
- **`P20261039_Casos_de_Prueba_ACTUALIZADO_v2.xlsx`**: 193 casos de prueba, uno por cada escenario de las HU (trazabilidad 1:1 verificada programáticamente, 0 desajustes). Los 131 casos que ya existían conservan su ID original; 62 son nuevos (CP132–CP193). Autoría repartida entre los dos integrantes (97/96 casos), mezclada aleatoriamente con semilla fija para que sea reproducible.
- **`P20261039_Product Backlog v.1.2.xlsx`**: 104 HU repartidas en 4 sprints (Autenticación → Registro de datos → Análisis+Visualización → Retención+Administración), todas en estado "Completado". Se corrigieron dos defectos del archivo original: la HU46 que faltaba por completo y la HU58 que estaba duplicada.

---

## Resumen de archivos tocados en esta sesión

```
financiero/forms.py                              (Tareas 5, 10)
financiero/views.py                               (Tareas 2, 9, 10, Dashboard)
financiero/urls.py                                (Tareas 2, 9)
recomendaciones/forms.py                          (Tarea 5)
recomendaciones/views.py                          (Tareas 2, 7)
recomendaciones/urls.py                           (Tarea 2)
recomendaciones/models.py                         (Tarea 2 — modelo AporteMeta)
recomendaciones/trends.py                         (Tareas 1, 6)
recomendaciones/migrations/0008_aportemeta.py     (nueva)
gamificacion/services.py                          (Tarea 1)
gamificacion/views.py                             (Tarea 3)
gamificacion/migrations/0009_seed_logros_ampliados.py  (nueva)
api/v1/serializers/recomendaciones.py             (Tarea 7)
api/v1/serializers/financiero.py                  (Tarea 10)
src/predict.py                                    (Tarea 7 — motor de recomendaciones)
templates/financiero/analisis.html                (Tarea 5 → revertida + selector categoría)
templates/financiero/dashboard.html               (Dashboard, reescrito)
templates/financiero/distribuir_ahorro.html       (nueva)
templates/financiero/registro_agregar.html        (nueva)
templates/financiero/registro_list.html           (Tarea 9)
templates/gamificacion/progreso.html              (Tarea 3)
templates/recomendaciones/metas.html              (Tarea 2)
templates/recomendaciones/meta_detalle.html       (nueva)
templates/recomendaciones/ml_insights.html        (Tareas 6, 7)
templates/recomendaciones/_resultado_ml.html      (Tarea 8)
templates/recomendaciones/_resultado_ml_js.html   (Tarea 8)
templates/accounts/*.html                         (btn-full para ancho completo)
templates/base.html                               (versión de CSS)
static/css/sigamos.css                            (Dashboard, botones)
src/stats_tests.py                                (fix dataset, sección 14)
src/ablation.py                                   (sección 14)
P20261039_Historias de Usuarios..._ACTUALIZADO.xlsx    (sección 15)
P20261039_Casos_de_Prueba_ACTUALIZADO_v2.xlsx          (sección 15)
P20261039_Product Backlog v.1.2.xlsx                   (sección 15)
```
