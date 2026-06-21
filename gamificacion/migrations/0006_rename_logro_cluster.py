from django.db import migrations


# El logro CLUSTER_AHORRADOR se mantiene por su CÓDIGO (referenciado en
# gamificacion/services.py), pero su texto visible al usuario ya no debe
# mencionar "Cluster" (K-Means fue eliminado). Ahora se otorga cuando el
# XGBoost Classifier clasifica al usuario como "Ahorra" (clase 1).
NUEVO = {
    'nombre': 'Clasificado Ahorrador',
    'descripcion': 'El modelo te clasificó como "Ahorra". ¡Excelente hábito!',
}
ANTERIOR = {
    'nombre': 'Cluster Ahorrador',
    'descripcion': 'El modelo ML te clasificó como Ahorrador. ¡Excelente hábito!',
}


def rename_forward(apps, schema_editor):
    Logro = apps.get_model('gamificacion', 'Logro')
    Logro.objects.filter(codigo='CLUSTER_AHORRADOR').update(**NUEVO)


def rename_backward(apps, schema_editor):
    Logro = apps.get_model('gamificacion', 'Logro')
    Logro.objects.filter(codigo='CLUSTER_AHORRADOR').update(**ANTERIOR)


class Migration(migrations.Migration):

    dependencies = [
        ('gamificacion', '0005_seed_primera_meta'),
    ]

    operations = [
        migrations.RunPython(rename_forward, reverse_code=rename_backward),
    ]
