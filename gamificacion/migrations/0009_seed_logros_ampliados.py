from django.db import migrations


# Catálogo ampliado: constancia de registro/racha más allá de los umbrales originales,
# uso recurrente del análisis ML, adopción/constancia de plan (leídos del historial de
# PlanSeleccionado — ver gamificacion/services.py), metas largo plazo con más avance o
# en paralelo, y aportes a metas (Tarea 2 — el modelo AporteMeta y su condición en
# verificar_y_otorgar_logros llegan en una migración/cambio posterior; el catálogo se
# siembra aquí para no fragmentar el seed de logros en dos migraciones).
LOGROS = [
    {
        'codigo': 'DIEZ_REGISTROS',
        'nombre': 'Diez Registros',
        'descripcion': 'Llevas 10 registros mensuales. La constancia se nota.',
        'icono': '🗂️',
        'puntos': 25,
        'orden': 15,
    },
    {
        'codigo': 'VEINTE_REGISTROS',
        'nombre': 'Veinte Registros',
        'descripcion': 'Llevas 20 registros mensuales. Ya es un hábito consolidado.',
        'icono': '🗃️',
        'puntos': 40,
        'orden': 16,
    },
    {
        'codigo': 'CINCUENTA_REGISTROS',
        'nombre': 'Cincuenta Registros',
        'descripcion': 'Llevas 50 registros mensuales. Constancia de largo aliento.',
        'icono': '🏛️',
        'puntos': 100,
        'orden': 17,
    },
    {
        'codigo': 'RACHA_60',
        'nombre': 'Racha de 60 días',
        'descripcion': 'Mantuviste una racha activa de 60 días consecutivos.',
        'icono': '💪',
        'puntos': 150,
        'orden': 18,
    },
    {
        'codigo': 'RACHA_90',
        'nombre': 'Racha de 90 días',
        'descripcion': 'Mantuviste una racha activa de 90 días consecutivos.',
        'icono': '👑',
        'puntos': 250,
        'orden': 19,
    },
    {
        'codigo': 'CINCO_ML',
        'nombre': 'Analista Financiero',
        'descripcion': 'Ejecutaste 5 análisis de Machine Learning.',
        'icono': '📊',
        'puntos': 40,
        'orden': 20,
    },
    {
        'codigo': 'DIEZ_ML',
        'nombre': 'Analista Experto',
        'descripcion': 'Ejecutaste 10 análisis de Machine Learning.',
        'icono': '🧠',
        'puntos': 70,
        'orden': 21,
    },
    {
        'codigo': 'PRIMER_PLAN',
        'nombre': 'Primer Plan Adoptado',
        'descripcion': 'Elegiste tu primer plan de recorte desde ML Insights.',
        'icono': '📘',
        'puntos': 20,
        'orden': 22,
    },
    {
        'codigo': 'PLAN_3_MESES',
        'nombre': 'Constancia de Plan',
        'descripcion': 'Cumpliste tu plan activo 3 meses consecutivos.',
        'icono': '📗',
        'puntos': 90,
        'orden': 23,
    },
    {
        'codigo': 'META_MITAD',
        'nombre': 'A Mitad de Camino',
        'descripcion': 'Llegaste al 50% de avance en una meta de ahorro a largo plazo.',
        'icono': '🏁',
        'puntos': 30,
        'orden': 24,
    },
    {
        'codigo': 'TRES_METAS_ACTIVAS',
        'nombre': 'Múltiples Objetivos',
        'descripcion': 'Mantienes 3 metas de ahorro a largo plazo activas a la vez.',
        'icono': '🗺️',
        'puntos': 35,
        'orden': 25,
    },
    {
        'codigo': 'APORTE_A_META',
        'nombre': 'Primer Aporte',
        'descripcion': 'Distribuiste el ahorro de un mes hacia una meta de ahorro.',
        'icono': '💵',
        'puntos': 20,
        'orden': 26,
    },
    {
        'codigo': 'APORTES_CONSTANTES',
        'nombre': 'Aportante Constante',
        'descripcion': 'Aportaste a tus metas de ahorro 3 meses distintos consecutivos.',
        'icono': '🔄',
        'puntos': 80,
        'orden': 27,
    },
]


def seed_logros(apps, schema_editor):
    Logro = apps.get_model('gamificacion', 'Logro')
    for data in LOGROS:
        Logro.objects.get_or_create(codigo=data['codigo'], defaults=data)


def remove_logros(apps, schema_editor):
    Logro = apps.get_model('gamificacion', 'Logro')
    Logro.objects.filter(codigo__in=[d['codigo'] for d in LOGROS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('gamificacion', '0008_seed_metas_mensuales'),
    ]

    operations = [
        migrations.RunPython(seed_logros, reverse_code=remove_logros),
    ]
