from django.db import migrations


# Logro referenciado en el código (recomendaciones: al crear la primera meta)
# pero ausente del seed original 0003. Se añade para que pueda otorgarse.
LOGRO = {
    'codigo': 'PRIMERA_META',
    'nombre': 'Soñador Financiero',
    'descripcion': 'Creaste tu primera meta de ahorro a largo plazo.',
    'icono': '🎯',
    'puntos': 20,
    'orden': 12,
}


def seed_primera_meta(apps, schema_editor):
    Logro = apps.get_model('gamificacion', 'Logro')
    Logro.objects.get_or_create(codigo=LOGRO['codigo'], defaults=LOGRO)


def remove_primera_meta(apps, schema_editor):
    Logro = apps.get_model('gamificacion', 'Logro')
    Logro.objects.filter(codigo=LOGRO['codigo']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('gamificacion', '0004_alter_logrousuario_table'),
    ]

    operations = [
        migrations.RunPython(seed_primera_meta, reverse_code=remove_primera_meta),
    ]
