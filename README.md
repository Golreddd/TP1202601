# SIGAMOS (SmartSave)

Aplicación web de finanzas personales que clasifica la situación de ahorro del
usuario con un modelo de Machine Learning (XGBoost) y genera un plan de recorte
de gastos personalizado (counterfactual) para llevarlo a una meta de ahorro.

Construida con **Django** (vistas web + API REST) y un pipeline de **ML en
Python puro** (`src/`), independiente del framework, entrenado sobre datos
socioeconómicos reales.

> Para el diseño detallado (apps, flujo de datos, decisiones metodológicas del
> modelo) ver [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md). Para el historial
> de cambios del proyecto ver [`CHANGELOG.md`](CHANGELOG.md).

## Mapa de carpetas

```
sigamos/            Configuración del proyecto Django (settings, urls, wsgi)
accounts/           Usuarios, roles (RBAC) y autenticación
financiero/         Registro mensual de ingresos/gastos del usuario
recomendaciones/     Metas de ahorro, orquestación del modelo ML y planes de recorte
gamificacion/        Rachas, logros y seguimiento de progreso
panel_admin/         Panel administrativo: auditoría y validación externa del modelo ML
api/                 API REST (DRF + JWT), versión v1
core/                Utilidades transversales (permisos, excepciones, constantes)

src/                 Pipeline de Machine Learning (independiente de Django)
  src/pipeline/         Código de producción: preprocesamiento, entrenamiento e inferencia
  src/research/         Scripts de validación académica (ablación, pruebas estadísticas,
                         análisis de robustez) — producen los resultados de la tesis/paper

data/                Datasets fuente (CSV) usados para entrenar el modelo
models/              Artefactos de producción (modelo, scaler, métricas) que carga Django
  models/investigacion/ Salidas de los scripts de src/research/ (JSON + figuras)

templates/           Plantillas Django, organizadas por app
static/              CSS/JS del frontend
```

## Requisitos

- Python 3.12
- PostgreSQL (local o remoto)

## Instalación (entorno local)

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

copy .env.example .env         # completar SECRET_KEY, credenciales de BD, etc.

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Las variables de entorno se documentan en [`.env.example`](.env.example).

## Pipeline de Machine Learning

El modelo de producción (`models/*.pkl`, `models/*.json`) ya está entrenado y
versionado; Django lo consume en modo **solo inferencia** vía
`src/pipeline/predict.py`. No es necesario reentrenar para levantar la app.

Para reproducir el entrenamiento o los análisis del paper/tesis (requiere
`data/dataset2.csv`, no versionado por tamaño):

```bash
python -m src.pipeline.train              # reentrena y sobrescribe models/*.pkl y *.json

# Scripts de validación académica (leen el modelo de producción, no lo modifican):
python -m src.research.ablation
python -m src.research.eval_planes
python -m src.research.stats_tests
python -m src.research.analisis_validacion
python -m src.research.umbral_segmento
```

## Despliegue

Configurado para Render vía [`render.yaml`](render.yaml) (Gunicorn + WhiteNoise
para estáticos + PostgreSQL administrado).
