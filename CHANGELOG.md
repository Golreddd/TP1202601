# CHANGELOG — SmartSave / SIGAMOS

Registro explícito de los cambios hechos en las sesiones de trabajo con Claude Code, organizados por tema. Para cada uno: qué cambió, en qué archivos, y por qué. Se actualiza en cada tanda nueva de trabajo — la numeración de secciones es cronológica.

> **Nota de alcance:** este documento cubre lo desarrollado en las conversaciones con Claude Code. Puede haber cambios hechos fuera de esas sesiones (por ejemplo directo en GitHub o en otro entorno) que no queden reflejados aquí si no hubo visibilidad completa de ellos.

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
- Commit `12df98f` — *"feat: dashboard interactivo, correcciones de UI y validacion ML con usuarios reales"* — agrupa el punto 11 (Dashboard), el reentrenamiento del modelo (`src/train.py` y artefactos `.pkl`) y el panel de "Validación ML con usuarios reales" (`panel_admin/models.py::ValidacionPrimerUso`, ver punto 16). Ya está en `origin/main`.

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

## 16. Panel Admin — Evolución de la tasa de ahorro por usuario

**Archivos:** `panel_admin/views.py`, `panel_admin/urls.py`, `templates/panel_admin/evolucion_ahorro.html`, `templates/base.html`

- Nueva pestaña de administración: para cada usuario, calcula el % de ahorro (ahorro / ingreso) desde su **primer** registro mensual, en columnas fijas **Mes 1 a Mes 10** — se completan solas conforme el usuario va registrando más meses (si supera 10, la tabla se extiende en vez de recortar).
- Cálculo propio `_tasa()` con 2 decimales de precisión (distinto de la propiedad `tasa_ahorro` del modelo, que redondea a 1 decimal, para que la evolución mes a mes se note incluso en variaciones chicas).
- Resumen agregado (promedio general, cuántos usuarios mejoraron/empeoraron su tasa) y filtro de búsqueda por nombre o correo.
- Exportación a CSV con BOM y `;` como separador (para que Excel en español lo abra bien de una), auditada vía `AuditLog.registrar(accion='EXPORTAR_DATOS', ...)`.

---

## 17. Validaciones de seguridad y formato en el perfil del usuario

**Archivos nuevos:** `accounts/validators.py`, `accounts/migrations/0003_alter_usuario_edad_alter_usuario_email_and_more.py`
**Archivos modificados:** `accounts/models.py`, `accounts/forms.py`, `api/v1/serializers/accounts.py`

Se creó `accounts/validators.py` como módulo único de validadores, adjuntos al **campo del modelo** (no solo al formulario web): así DRF los hereda automáticamente en los serializers (`ModelSerializer` copia los `validators` del campo al construirse), sin tener que repetir la regla en la web y en la API por separado.

- **Nickname**: antes solo se validaba el charset — dejaba pasar nicknames como `"044444444404040404040409494049"` (puros números) o `"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"` (un solo carácter repetido). Ahora exige entre 3 y 20 caracteres, con al menos una letra, y rechaza el mismo carácter repetido.
- **Edad**: antes no tenía **ningún** validador de servidor — solo el atributo `min`/`max` del HTML del widget, que no protege nada si se edita el POST a mano o se llama la API directo. Permitía registrar usuarios de 1 o 2 años. Ahora exige 18+ a nivel de modelo.
- **Correo**: rechaza dominios evidentemente falsos como `"1@1.com"` o `"asdas.a@a.com"` (segundo nivel de dominio de una sola letra o puramente numérico), sin resolver DNS.
- **Teléfono**: exactamente 9 dígitos numéricos (convención de celular en Perú).
- Al revisar usuarios reales en producción se encontraron varias cuentas que coincidían exactamente con estos patrones de basura (nicknames como los de arriba, edades de 1-2 años, correos `1@1.com`, teléfonos como `"sexooooooo"`) — **no se modificaron ni eliminaron**, solo se reportaron. El punto de entrada más probable era la API: `UsuarioUpdateSerializer.validate_edad` aceptaba desde 15 años (más débil que el formulario web) y el registro por API casi no validaba formato de nickname. Con el validador a nivel de modelo, la API queda pareja con la web automáticamente, sin tocar los serializers.
- Migración `0003_...`: 4 `AlterField` (edad, email, nickname, teléfono), confirmada con `sqlmigrate` como **no-op** — los validadores no tocan la estructura de la tabla.

---

## 18. Renombre de categorías de gasto (solo la etiqueta visible)

**Archivos:** `financiero/models.py`, `financiero/views.py`, `financiero/forms.py`, `gamificacion/views.py`, `api/v1/views/financiero.py`, `src/predict.py`

"Vestido" → "Ropa" y "Otros Bienes" → "Otros Gastos", **solo en lo que ve el usuario**. Los nombres internos de campo (`gasto_vestido`, `gasto_otros_bienes`) y las constantes del motor ML (`GASTO_VESTIDO`, `GASTO_OTROS_BIENES`) no se tocaron — cero riesgo sobre cálculos, migraciones o el modelo entrenado.

El mismo texto se arma en varios lugares independientes que no comparten una sola fuente (el diccionario de `gastos_por_categoria()`, el mapa de presupuesto por categoría en gamificación, los `labels` del formulario de registro, la lista de categorías de la API, y un `etiqueta_categoria()` nuevo en `src/predict.py` para las recomendaciones) — se sincronizaron todos a mano, cada uno con un comentario de advertencia para que no se desalineen si se vuelve a tocar en el futuro.

---

## 19. Meta de largo plazo: no se puede fijar una fecha límite ya vencida

**Archivos:** `recomendaciones/forms.py`, `api/v1/serializers/recomendaciones.py`

- `MetaLargoPlazoForm.clean_fecha_limite` y `MetaLargoPlazoSerializer.validate_fecha_limite` rechazan un mes ya pasado, tanto al **crear** una meta nueva como al **mover** la fecha de una existente hacia atrás.
- Con "cláusula de abuelo": si la meta ya tenía guardada esa misma fecha (no se tocó al editar otro campo), se deja pasar aunque haya quedado en el pasado desde entonces — solo se bloquea crear o mover una meta hacia el pasado, nunca se rompe la edición de una meta vieja que ya estaba vencida.

---

## 20. Mostrar/ocultar contraseña y bloqueo de letras en campos numéricos

**Archivos:** `static/js/sigamos.js`

- Ícono de ojo (👁️ / 🙈) agregado dinámicamente a **todo** `input[type=password]` del sistema (login, registro, restablecimiento, cambio de contraseña) desde un único script global — no requirió tocar ningún template, ya que todos ya cargan `sigamos.js`.
- Los `input[type=number]` (como Edad) dejaban escribir `e`, `E`, `+`, `-` y quedaban con eso visible en el campo, porque son caracteres válidos de notación exponencial en HTML5. Ahora se bloquean esas teclas (y el punto decimal en campos que son enteros, como edad o miembros del hogar) tanto al teclear como al pegar texto, en todos los campos numéricos del sistema.

---

## 21. Corrección de responsive / vista móvil

**Archivos:** `static/css/sigamos.css`, `static/js/sigamos.js`, `templates/base.html`, `templates/base_auth.html`, `templates/gamificacion/logros.html`, `templates/gamificacion/progreso.html`, `templates/financiero/analisis.html`, `templates/recomendaciones/ml_insights.html`, `templates/recomendaciones/_resultado_ml.html`, `templates/recomendaciones/_resultado_ml_js.html`

Reportado en varias pantallas (Registros, ML Insights, Análisis de Gastos, Progreso, panel de administración) que el contenido se veía cortado en celular. Se resolvió en tres pasadas:

**1. Arreglos puntuales** (necesarios, pero no resolvían el problema de fondo):
- 6 tarjetas tenían `grid-template-columns` puesto como estilo **inline** (Logros, resumen de mes en ML Insights, métricas de resultado ML) — un estilo inline le gana a cualquier media query, así que esas grillas quedaban forzadas a 2-4 columnas sin importar el ancho de pantalla. Se movieron a clases CSS (`.grid-racha`, `.stats-grid-3`, `.achv-grid`, `.resumen-ml-grid`) que sí colapsan en móvil.
- La leyenda del gráfico de dona (Análisis de Gastos, Dashboard) estaba fija "a la derecha"; pasa a "abajo" en pantallas ≤600px.
- 6 tarjetas usaban `.card-header` (pensado para "título + botón corto al lado") para un título + una oración larga de subtítulo debajo, y quedaban apretadas en vez de apiladas. Nueva variante `.card-header.stack`.
- El `<select>` de "Mes a analizar" en ML Insights tenía `min-width:420px` fijo, más ancho que cualquier celular.

**2. Causa raíz real**, encontrada recorriendo el DOM con `document.querySelectorAll('*')` + comparando `scrollWidth`/`clientWidth` en la consola del navegador (la pasada anterior no la resolvía porque no era el problema): `.main` es un elemento flex dentro de `.app`, y por defecto un elemento flex **no se encoge más allá del ancho mínimo de su propio contenido** (`min-width:auto` implícito de la especificación). Como algo dentro de `.main` tenía un ancho mínimo natural mayor a la pantalla real, **toda** la app (topbar, contenido, tarjetas) se ensanchaba para acomodarlo en vez de encogerse al viewport — por eso se veía igual de cortada en absolutamente todas las páginas por igual. Se corrigió con `min-width:0` en `.main`, `.content` y `.topbar` (el arreglo estándar de este problema conocido de flexbox), más recorte con elipsis en el título de la topbar si no entra.
  - En el camino se probó y **revirtió** un `overflow-wrap:anywhere` global en `<body>` (pensado para que correos largos no desbordaran en el panel de admin) que tuvo un efecto secundario severo: al combinarse con `table{width:100%}`, el navegador partía cada palabra de las tablas letra por letra en vertical en vez de dejarlas anchas con scroll. Detectado por captura de pantalla del usuario y revertido en la misma sesión.

**3. Descubribilidad del scroll en tablas anchas** (Registros, tablas de admin): las tablas con muchas columnas no entran en una pantalla de celular y eso es esperado — se pueden deslizar de lado —, pero no había ninguna señal visual de que hubiera más contenido a la derecha. Se agregó una sombra en el borde derecho (con degradados en dos capas, 100% CSS, sin JS) más el texto "⟷ Desliza para ver más" en móvil.

---

## 22. Validación: miembros del hogar y ciudad

**Archivos:** `accounts/validators.py`, `accounts/models.py`, `accounts/migrations/0004_alter_usuario_ciudad_alter_usuario_miembros_hogar.py`

- `miembros_hogar` (`PositiveSmallIntegerField`) permitía 0 pese al nombre del tipo (en Django, "positive" solo exige `>= 0`, no `>= 1`) — ahora exige mínimo 1 (el propio usuario cuenta) y máximo 20 (tope que ya exigía la API mediante un chequeo aparte en el serializer; ahora queda parejo en modelo/formulario/API en vez de duplicado en un solo lado).
- `ciudad`: nuevo validador de formato — solo letras (con tildes/ñ), espacios, apóstrofes y guiones, para permitir nombres compuestos ("Villa El Salvador", "San Martín de Porres") pero rechazar números y símbolos sueltos.
- Migración confirmada como no-op con `sqlmigrate`.

---

## Despliegue (puntos 16 a 22)

Todo lo de esta tanda ya está en `origin/main` y desplegado en Render vía auto-deploy:

| Commit | Contenido |
|---|---|
| `abcbcaf`, `f3cd9da` | Punto 16 — Evolución de Ahorro |
| `b9141f5` | Puntos 17, 18, 19 — validaciones de nickname/edad/email/teléfono, renombre de categorías, fecha límite de metas |
| `57d5e71` | Punto 20 + primera pasada del punto 21 |
| `b9be77e` | Causa raíz y arreglo real del punto 21 (bug de flexbox) |
| `835e6f2` | Punto 22 — miembros del hogar y ciudad |

---

## 23. Reentrenamiento del modelo (correcciones de revisores del paper)

**Rama:** `reentrenamiento-validacion` (al fusionar a `main`, Render despliega el modelo nuevo).

Estructura de datos que se mantiene: 80 % entrenamiento, 20 % validación, y prueba con los usuarios reales del sistema (`ValidacionPrimerUso`).

- **`src/train.py`**: Optuna (TPE, 40 trials, CV 3-fold, macro-F1), la CV de 5 particiones y el early stopping se hacen **solo dentro del 80 %** de entrenamiento. El early stopping usa un 10 % interno (estratificado) del 80 % para fijar el número de árboles, y luego el modelo se reajusta sobre todo el 80 % con ese número. El 20 % de validación ya no interviene en ninguna decisión del entrenamiento: solo mide el desempeño final. Antes el 20 % se usaba para el early stopping y Optuna usaba todas las filas. En `metrics.json`, la CV pasa a llamarse `cv_5fold_train` (se mantienen `valid` y `n_valid`).
- **`src/preprocessing.py`**: se quitó `ESTRATO_SOC` (18 variables en vez de 19) porque la app no lo captura y en producción llegaba siempre como 0. `build_feature_row` ahora deriva `TIPO_INGRESO` de los ingresos (FORMAL = solo planilla, INFORMAL = solo informal, MIXTO = ambos); antes las tres `TIPO_*` llegaban en 0 en producción. Verificado: la regla coincide al 100 % con el `TIPO_INGRESO` real de las 9,527 filas de entrenamiento.
- **`models/`**: nuevos `xgb_clf_model.pkl`, `scaler.pkl`, `shap_explainer.pkl`, `features.json`, `xgb_best_params.json`, `metrics.json`, más `ablation.json`, `stats_tests.json`, `analisis_validacion.json`, `planes_eval.json` y figuras en `models/figuras/` (matriz de confusión, ROC y SHAP sobre la validación).
- **Análisis**: `src/stats_tests.py` compara LR, RF y XGBoost sobre la validación, con LR y RF ajustados con el mismo Optuna. `src/ablation.py` evalúa sobre la validación. Nuevos: `src/analisis_validacion.py` (matriz, ROC, SHAP, subgrupos, multi-semilla, sensibilidad a la limpieza) y `src/eval_planes.py` (evaluación de los planes de ajuste presupuestario).
- **Panel admin**: `panel_admin/views.py` lee `cv_5fold_train` (con respaldo a `cv_5fold`); docstring de `ValidacionPrimerUso` actualizado.
- **Nuevo comando `recalcular_validacion_ml`**: reclasifica con el modelo actual el primer análisis de cada usuario y muestra matriz de confusión y métricas con IC de Wilson; solo escribe en la BD con `--aplicar`. **No se ejecutó**: por decisión del equipo, los casos de validación ya registrados se conservan tal como se calcularon, y el modelo nuevo aplica solo a los análisis que se hagan desde ahora.

**Verificación (sin reentrenar):** con el dataset limpio y los artefactos guardados, la partición de validación (semilla 42, 1,906 registros) reproduce exactamente `metrics.json`: accuracy 0.8137, precision 0.8089, recall 0.8063, F1 0.8076, AUC-ROC 0.9006, 288 árboles. `build_feature_row` devuelve exactamente las 18 columnas de `features.json`; `classify` y `recommend` funcionan (3 planes + SHAP). `manage.py check` sin problemas.

---

## Resumen de archivos tocados (puntos 1 a 15)

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

## Resumen de archivos tocados (puntos 16 a 22)

```
accounts/validators.py                            (nuevo — puntos 17, 22)
accounts/models.py                                (puntos 17, 22)
accounts/forms.py                                 (punto 17)
accounts/migrations/0003_alter_usuario_edad_alter_usuario_email_and_more.py  (nueva — punto 17)
accounts/migrations/0004_alter_usuario_ciudad_alter_usuario_miembros_hogar.py (nueva — punto 22)
api/v1/serializers/accounts.py                    (punto 17)
api/v1/serializers/recomendaciones.py             (punto 19)
api/v1/views/financiero.py                        (punto 18)
financiero/models.py                              (punto 18)
financiero/views.py                               (punto 18)
financiero/forms.py                               (punto 18)
gamificacion/views.py                             (punto 18)
recomendaciones/forms.py                          (punto 19)
src/predict.py                                    (punto 18)
panel_admin/views.py                              (punto 16)
panel_admin/urls.py                               (punto 16)
templates/panel_admin/evolucion_ahorro.html       (nueva — punto 16)
static/js/sigamos.js                              (puntos 20, 21)
static/css/sigamos.css                            (punto 21)
templates/base.html                               (punto 21 — versión de CSS/JS)
templates/base_auth.html                          (punto 21 — versión de CSS/JS)
templates/gamificacion/logros.html                (punto 21)
templates/gamificacion/progreso.html              (punto 21)
templates/financiero/analisis.html                (punto 21)
templates/recomendaciones/ml_insights.html        (punto 21)
templates/recomendaciones/_resultado_ml.html      (punto 21)
templates/recomendaciones/_resultado_ml_js.html   (punto 21)
```

---

## 24. Reorganización de la estructura del proyecto (sin cambios de funcionalidad)

Reordenamiento puro de carpetas/archivos y documentación nueva, pensado para
que el código sea legible en un ámbito académico (tesis) y profesional. No se
modificó ninguna lógica interna, solo ubicaciones, nombres e imports.

**Movimientos de archivos:**
- `dataset2.csv` y `dataset_final_limpio.csv` → `data/` (antes en la raíz).
- `src/` dividido en `src/pipeline/` (código de producción que usa Django:
  `preprocessing.py`, `train.py`, `predict.py`) y `src/research/` (scripts de
  validación académica: `ablation.py`, `eval_planes.py`, `stats_tests.py`,
  `analisis_validacion.py`, `umbral_segmento.py`).
- `models/` dividido: la raíz conserva los artefactos de producción sin
  cambios (`*.pkl`, `features.json`, `metrics.json`, `xgb_best_params.json`);
  las salidas exclusivas de `src/research/` (JSONs de ablación, pruebas
  estadísticas, análisis de validación, umbral por segmento, y la carpeta
  `figuras/`) se movieron a `models/investigacion/`.
- `recomendaciones/trends.py` → `recomendaciones/analitica.py` (único archivo
  del proyecto con nombre en inglés; se alinea con la convención en español
  del resto de módulos).
- `templates/recomendaciones/_resultado_ml.html` y `_resultado_ml_js.html` →
  `templates/recomendaciones/partials/`, para distinguir los fragmentos
  reutilizables de las plantillas completas.
- `core/permissions.py`: se eliminaron `EsUsuarioNormal`, `EsDueño` y
  `EsAdminODueño` (confirmadas sin ningún uso en el resto del proyecto).

**Archivos actualizados por los movimientos anteriores** (imports y
referencias de ruta, sin cambios de lógica): `sigamos/settings.py`,
`panel_admin/models.py`, `panel_admin/management/commands/recalcular_validacion_ml.py`,
`api/v1/views/recomendaciones.py`, `financiero/management/commands/seed_demo_users.py`,
`financiero/views.py`, `recomendaciones/models.py`, `recomendaciones/views.py`,
`gamificacion/views.py`, `gamificacion/services.py`,
`templates/recomendaciones/historial_detalle.html`,
`templates/recomendaciones/ml_insights.html`.

**Documentación nueva:**
- `README.md` (no existía): descripción del proyecto, mapa de carpetas,
  instalación y cómo ejecutar el pipeline ML.
- `docs/ARQUITECTURA.md` (nuevo): diseño del sistema, flujo de un análisis
  ML de punta a punta, y las limitaciones de diseño conocidas (imports
  diferidos entre apps, lógica de negocio en algunas vistas).
- Se agregó un docstring de módulo (1–3 líneas) a los archivos `.py` que no
  lo tenían, en todas las apps.

**Verificación realizada:** `python manage.py check`, importación directa de
cada módulo movido/renombrado (`src.pipeline.*`, `src.research.*`,
`recomendaciones.analitica`, y todos los módulos Django que los consumen), y
`python -m py_compile` sobre todos los archivos tocados.

---

## 25. Asistente de voz ("🎤 Habla con SmartSave")

Registrar ingresos/gastos y preguntar por el estado financiero por voz (o
texto) desde el dashboard, sin depender de ningún servicio de pago: la
transcripción la hace el navegador (Web Speech API, `es-PE`) y la
interpretación es un parser de reglas en Python puro (sin LLM), con jerga
peruana. Ver `docs/ARQUITECTURA.md` §7 para el diagrama de flujo completo.

**Backend nuevo:**
- `financiero/voz_vocabulario.py` — jerga/sinónimos por categoría de gasto,
  tipo de ingreso, verbos, periodo y preguntas (datos, sin lógica).
- `financiero/voz.py::interpretar(texto, contexto_previo)` — parser puro:
  normaliza el texto, extrae montos (dígitos y números en palabras, con
  decenas/centenas/"mil"/decimales por "con"), detecta categoría de gasto o
  tipo de ingreso, y distingue registrar / consultar / mixta (gasto +
  pregunta a la vez, ej. "gasto 50 soles ¿cuánto me queda?") / simulación
  ("si gasto 50 en ropa…") / desconocida. Todo gasto exige una categoría de
  las 8 de `RegistroMensual` — nunca se guarda un monto suelto; si falta un
  dato, el turno siguiente se interpreta concatenado (`contexto_previo`), sin
  guardar estado de conversación en el servidor.
- `financiero/voz_servicios.py` — conecta el parser con la BD:
  `previsualizar()` (antes/después de cada ítem e impacto en el presupuesto
  por categoría del plan activo, sin guardar), `aplicar()` (suma al
  `RegistroMensual` del mes actual —lo crea si no existe—, actualiza racha y
  logros, y devuelve un token firmado para deshacer), `deshacer()` (revierte
  por token, válido 10 minutos; borra el registro si quedó en 0 y lo creó esa
  acción) y `responder()` (gasto/ingreso/ahorro total, por categoría, "en qué
  gasto más", presupuesto restante, cumplimiento del plan, comparación con el
  mes pasado). Nunca se guarda el audio ni el texto dictado.
- `recomendaciones/analitica.py::presupuesto_por_categoria()` — se extrajo de
  `gamificacion/views.py::progreso` (antes duplicaba el cálculo) para que
  Progreso y el asistente de voz usen la misma fuente.
- `accounts.Usuario.registros_voz` (nuevo campo) y logros `MANOS_LIBRES`
  (1er registro por voz) / `ASISTENTE_FIEL` (10 registros), sembrados en
  `gamificacion/migrations/0010_seed_logros_voz.py`.
- API v1: `POST /api/v1/voz/interpretar|confirmar|deshacer/`
  (`api/v1/views/voz.py`, `api/v1/serializers/voz.py`) — revalida categoría/
  tipo/monto en el servidor aunque el cliente ya los haya recibido de
  `/interpretar/`.

**Frontend nuevo:**
- Botón "🎤 Habla con SmartSave" en el dashboard, a la izquierda de
  "+ Nuevo Registro" (`templates/financiero/dashboard.html`,
  `templates/financiero/partials/_modal_voz.html`).
- `static/js/voz.js` — `SpeechRecognition`, máquina de estados del modal
  (escuchando / confirmar con impacto en el plan / éxito con logros y
  "Deshacer" / respuesta con lectura en voz (`speechSynthesis`) / falta un
  dato (chips de categoría o tipo de ingreso) / no entendido con ejemplos
  dinámicos / texto como respaldo si el navegador no soporta voz o se negó
  el micrófono).
- `static/css/sigamos.css` (`?v=13`): clases nuevas y acotadas para el
  asistente (`.page-header-actions`, `.voz-*`); reutiliza `.budget-card`/
  `.budget-bar` (ya usadas en Progreso) para el impacto en el plan, y el
  patrón `.page-header` con dos botones ya es responsive (se apilan en
  móvil sin CSS adicional).

**Tests nuevos** (el proyecto no tenía ninguno): `financiero/tests/test_voz.py`
(parser puro + servicios contra la BD de test) y `api/v1/tests/test_voz.py`
(flujo completo interpretar → confirmar → deshacer vía API, autenticación,
validación de payload).

**Verificación realizada:** batería manual de ~40 frases del parser
(jerga, números en palabras, varios montos por frase, ingresos por tipo,
preguntas de cada tipo, mixta/simulación, moneda extranjera rechazada);
`python manage.py test financiero.tests.test_voz api.v1.tests.test_voz`;
flujo end-to-end con el test client de Django (interpretar → confirmar →
deshacer) sobre un usuario descartable, creado y eliminado en la misma
prueba; render real del dashboard (`GET /financiero/`) confirmando que el
botón, el modal y los archivos estáticos nuevos cargan con 200; funciones
de renderizado de `voz.js` ejercitadas con un DOM simulado en Node.

---

## 26. Asistente de voz — ajustes tras la primera prueba de uso

- **La grabación ya no se cortaba tras la primera pausa.** `static/js/voz.js`
  usaba `SpeechRecognition` en modo de una sola frase; ahora es
  `continuous:true` y el usuario dice todo lo que necesite hasta pulsar el
  nuevo botón **"⏹ Terminé de hablar"** (`vozDetenerEscucha()`), que se ve
  claramente más grande que el resto (clase `.btn-voz-detener`, ancho
  completo, texto más grande) porque es la acción que más se usa.
- **Tope de 1 minuto** por grabación (`VOZ_MAX_MS`): si nadie pulsa el botón,
  se corta sola, avisa con un toast y procesa igual lo que se alcanzó a decir.
- **Vocabulario de marcas conocidas** (Perú) en `financiero/voz_vocabulario.py`,
  para cuando el usuario menciona dónde gastó y no solo la categoría genérica:
  restaurantes/supermercados (KFC, Bembos, Plaza Vea, Tottus…), ropa (Zara,
  Nike, Ripley…), servicios del hogar (Sedapal, Calidda, Sodimac…), salud
  (Rímac, Inkafarma, clínicas…), transporte (Uber, Primax, Repsol…),
  streaming (Netflix, HBO Max…), universidades (PUCP, UPC, UTP…) y
  entretenimiento (Cineplanet, PlayStation…) — sin colisiones entre
  categorías (verificado programáticamente).

**Verificación:** simulación de los eventos reales de `SpeechRecognition`
(varias frases seguidas → un solo envío al soltar "Terminé de hablar";
cierre a medias → no procesa nada; permiso denegado → cae a texto; nadie
habla → "no entendido"); `python manage.py test financiero.tests.test_voz
api.v1.tests.test_voz` (43 tests); frases sueltas con las marcas nuevas
para confirmar que resuelven a la categoría correcta.

---

## 27. Asistente de voz — corrección de bugs reales tras la segunda prueba de uso

El usuario reportó que el asistente "se quedaba en bucle" al no entender
frases con jerga de dinero, y que los ingresos casi nunca se detectaban.
Investigando cada caso salieron **cuatro bugs reales** (no solo vocabulario
faltante):

- **El bug del "bucle" era real, en el frontend.** Al llegar a "No entendí
  eso" y elegir "✍️ Escribir", `vozState.contextoPrevio` (el texto fallido
  anterior) **no se limpiaba** — el botón "🎤 Intentar de nuevo" sí lo hacía,
  pero "Escribir" no. El usuario escribía algo nuevo y quedaba pegado al
  intento fallido de antes, arrastrando el error indefinidamente. Corregido
  en `static/js/voz.js`; además se agregó un enlace "¿Se quedó atascado?
  Empezar de nuevo" en la vista de dato faltante, como salvavidas visible.
- **Jerga de billetes con valor propio, no solo "jerga de soles".** Antes
  "lucas" solo se trataba como sinónimo de "soles" (necesitaba un número
  adelante). Ahora `financiero/voz_vocabulario.py` tiene un diccionario
  `DENOMINACIONES` (luca/luquita=1, cheque/cheke=10, ferro/ferrito=100) que
  funciona como "mil": la palabra POR SÍ SOLA vale ese monto ("un cheque"=10,
  "gasté un ferro"=100) y con un número adelante lo multiplica ("20
  cheques"=200). Esto obligó a reescribir `_extraer_todos_los_numeros` en
  `financiero/voz.py` en un solo paso (antes dígitos y palabras se procesaban
  por separado, lo que no permitía combinar "20" + "cheques").
- **Categorías no reconocían su propio plural.** "comida" no encontraba
  "comidas" (coincidencia de palabra completa). Nuevo helper
  `_contiene_o_plural` (acepta 's' final) usado solo en categorías/tipos de
  ingreso, no en verbos ni preguntas. De paso se encontró que dos categorías
  ni siquiera tenían su propio nombre formal en la lista ("educación",
  "comunicaciones") — agregado.
- **Ingresos con verbo en singular no se detectaban.** El vocabulario solo
  tenía formas plurales/impersonales ("me dieron", "me pagaron"); "mi tío me
  dio 30 soles de propina" no matcheaba porque faltaba "me dio" (singular).
  Se agregaron las contrapartes singulares de todos los verbos de ingreso, se
  amplió la lista de familiares en `bonif_monto` (tío/tía, no solo
  mamá/papá/abuelos) y se agregó "propina"/"propinas" como palabra clave
  directa.
- **Al agregar los verbos en singular apareció un choque nuevo**: "pago" es
  verbo de GASTO ("pago 50 de luz") pero también aparece dentro de la frase
  de INGRESO "me pago" (de "me pagó" — sin tilde por la normalización, "mi
  jefe me pagó 200" y "me pago 200" quedan igual de texto). Con el orden
  anterior, el gasto ganaba siempre porque se evaluaba primero. Se reordenó
  la prioridad en `_procesar_segmento`: una palabra clave concreta
  (`campo_ingreso`/`campo_gasto`) pesa más que un verbo suelto, y entre
  verbos sueltos ingreso pesa más que gasto — así "me pago 200 de sueldo" se
  reconoce como ingreso y "pago 50 de luz" (sin "me") sigue siendo gasto.

**Verificación:** las 3 frases reales que reportó el usuario ahora se
interpretan correctamente (probado directamente con `interpretar()`);
17 tests nuevos en `financiero/tests/test_voz.py` cubriendo denominaciones,
plurales, verbos de ingreso en singular y el choque "pago"/"me pago";
`python manage.py test financiero.tests.test_voz api.v1.tests.test_voz`
(55 tests); sin colisiones nuevas entre categorías (verificado
programáticamente).

---

## 28. Asistente de voz — transcripción en el aviso de exceso de plan

En la pantalla de confirmación ("Esto entendí:"), cuando el gasto dictado
hacía que una categoría se pasara del plan, aparecía un aviso ⚠️ "Con esto te
pasarías de tu plan. Puedes compensar con: ..." — sonaba a error del sistema
más que a información útil. Se reemplazó ese aviso puntual por la
transcripción tal cual se entendió ("🎤 Escuché: '...'"), así el usuario
puede revisar de una si el exceso viene de algo mal reconocido antes de
confirmar. Las tarjetas de presupuesto de abajo (categoría, gastado/sugerido,
excedido) siguen igual, así que no se pierde esa información, solo la frase
de alarma. El mensaje de respuesta a una pregunta de paso (ej. "no tienes
ningún registro de este mes"), que en una iteración anterior se había
reemplazado por error por esta misma transcripción, volvió a su lugar y
comportamiento original. Cambio solo en `static/js/voz.js`
(`vozVistaConfirmar`), sin tocar el parser ni el backend.
