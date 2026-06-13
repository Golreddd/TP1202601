from django.db import migrations


LOGROS = [
    {
        'codigo': 'PRIMER_REGISTRO',
        'nombre': 'Primer Registro',
        'descripcion': 'Creaste tu primer registro mensual.',
        'icono': '📋',
        'puntos': 10,
        'orden': 1,
    },
    {
        'codigo': 'CINCO_REGISTROS',
        'nombre': 'Cinco Registros',
        'descripcion': 'Llevas 5 registros mensuales. ¡Sigue así!',
        'icono': '📅',
        'puntos': 20,
        'orden': 2,
    },
    {
        'codigo': 'RACHA_7',
        'nombre': 'Racha de 7 días',
        'descripcion': 'Mantuviste una racha activa de 7 días consecutivos.',
        'icono': '🔥',
        'puntos': 30,
        'orden': 3,
    },
    {
        'codigo': 'RACHA_30',
        'nombre': 'Racha de 30 días',
        'descripcion': 'Increíble: 30 días consecutivos registrando tus finanzas.',
        'icono': '🌟',
        'puntos': 100,
        'orden': 4,
    },
    {
        'codigo': 'AHORRADOR_20',
        'nombre': 'Ahorrador 20%',
        'descripcion': 'Alcanzaste una tasa de ahorro del 20% o más en un mes.',
        'icono': '💰',
        'puntos': 50,
        'orden': 5,
    },
    {
        'codigo': 'TRES_MESES_VERDE',
        'nombre': 'Tres Meses Verde',
        'descripcion': 'Tres meses consecutivos con ahorro positivo.',
        'icono': '📈',
        'puntos': 60,
        'orden': 6,
    },
    {
        'codigo': 'PRIMER_ML',
        'nombre': 'Primer Análisis ML',
        'descripcion': 'Ejecutaste tu primer análisis de Machine Learning.',
        'icono': '🤖',
        'puntos': 20,
        'orden': 7,
    },
    {
        'codigo': 'CLUSTER_AHORRADOR',
        'nombre': 'Cluster Ahorrador',
        'descripcion': 'El modelo ML te clasificó como Ahorrador. ¡Excelente hábito!',
        'icono': '⭐',
        'puntos': 80,
        'orden': 8,
    },
    {
        'codigo': 'PERFIL_COMPLETO',
        'nombre': 'Perfil Completo',
        'descripcion': 'Completaste todos los datos de tu perfil financiero.',
        'icono': '👤',
        'puntos': 15,
        'orden': 9,
    },
    {
        'codigo': 'META_CUMPLIDA',
        'nombre': 'Meta Cumplida',
        'descripcion': 'Alcanzaste el 100% de una meta de ahorro a largo plazo.',
        'icono': '🎯',
        'puntos': 100,
        'orden': 10,
    },
    {
        'codigo': 'MAESTRO_AHORRO',
        'nombre': 'Maestro del Ahorro',
        'descripcion': 'Completaste 5 metas de ahorro a largo plazo.',
        'icono': '🏆',
        'puntos': 200,
        'orden': 11,
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
        ('gamificacion', '0002_create_logroupsuario'),
    ]

    operations = [
        migrations.RunPython(seed_logros, reverse_code=remove_logros),
    ]
