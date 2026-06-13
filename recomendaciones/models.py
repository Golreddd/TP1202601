import json

from django.db import models
from django.conf import settings


class MetaMensual(models.Model):
    """
    Meta de ahorro mensual del usuario.
    El campo monto se pasa como meta_ahorro a recommend() en src/predict.py.
    """
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='metas_mensuales',
    )
    periodo = models.DateField(verbose_name='Período')
    monto   = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name='Meta de ahorro (S/)',
    )

    class Meta:
        unique_together     = ['usuario', 'periodo']
        ordering            = ['-periodo']
        verbose_name        = 'Meta Mensual'
        verbose_name_plural = 'Metas Mensuales'

    def __str__(self):
        return f'Meta {self.usuario.nickname} {self.periodo.strftime("%B %Y")}: S/ {self.monto}'


class MetaLargoPlazo(models.Model):
    """
    Objetivos de ahorro a largo plazo del usuario.
    Son UI-only (no se pasan al ML). Ejemplos: viaje, emergencia, laptop, depa.
    """
    ICONO_CHOICES = [
        ('🏠', 'Vivienda'),
        ('✈️', 'Viaje'),
        ('💻', 'Tecnología'),
        ('🛡️', 'Fondo de Emergencia'),
        ('🎓', 'Educación'),
        ('🚗', 'Vehículo'),
        ('🎯', 'Otro'),
    ]

    usuario        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='metas_largo_plazo',
    )
    nombre         = models.CharField(max_length=100, verbose_name='Nombre de la meta')
    icono          = models.CharField(max_length=10, choices=ICONO_CHOICES, default='🎯')
    monto_objetivo = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Monto objetivo (S/)')
    monto_actual   = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Monto ahorrado (S/)')
    fecha_limite   = models.DateField(null=True, blank=True, verbose_name='Fecha límite')
    activa         = models.BooleanField(default=True)

    creado_en      = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table            = 'recomendaciones_metalargoplazo'
        ordering            = ['-creado_en']
        verbose_name        = 'Meta a Largo Plazo'
        verbose_name_plural = 'Metas a Largo Plazo'

    def __str__(self):
        return f'{self.nombre} ({self.usuario.nickname})'

    @property
    def porcentaje(self):
        if self.monto_objetivo > 0:
            return min(100, round(float(self.monto_actual) / float(self.monto_objetivo) * 100, 1))
        return 0.0

    @property
    def faltante(self):
        return max(0.0, float(self.monto_objetivo) - float(self.monto_actual))

    @property
    def completada(self):
        return self.monto_actual >= self.monto_objetivo


class ResultadoML(models.Model):
    """
    Resultado escalares de cada ejecución de recommend() en src/predict.py.

    Se guardan solo los valores escalares:
      ahorro_actual, meta_validada, gap, cluster_id, cluster_label, confianza.

    Los planes de acción (conservador/balanceado/agresivo) y el top 5 SHAP
    se recomputan en tiempo real cuando el usuario los consulta, pasando el
    RegistroMensual original a recommend() de nuevo.
    Esto mantiene la BD ligera y permite actualizar la lógica de predict.py
    sin migrar datos históricos.
    """
    usuario    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='resultados_ml',
    )
    registro   = models.ForeignKey(
        'financiero.RegistroMensual',
        on_delete=models.CASCADE,
        related_name='resultados_ml',
    )
    meta = models.ForeignKey(
        MetaMensual,
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )

    # ── Salidas escalares de recommend() ─────────────────────────────────────
    ahorro_actual  = models.FloatField(verbose_name='Ahorro predicho (S/)')
    meta_validada  = models.FloatField(verbose_name='Meta validada (S/)')
    gap            = models.FloatField(verbose_name='Gap meta - ahorro (S/)')
    cluster_id     = models.IntegerField(verbose_name='ID cluster K-Means')
    cluster_label  = models.CharField(max_length=150, verbose_name='Etiqueta cluster')
    confianza      = models.CharField(max_length=250, verbose_name='Nivel de confianza')

    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-creado_en']
        verbose_name        = 'Resultado ML'
        verbose_name_plural = 'Resultados ML'
        indexes = [
            # Historial / dashboard: filtra por usuario y ordena por fecha.
            models.Index(fields=['usuario', '-creado_en'], name='idx_resml_user_fecha'),
            # Métricas admin: distribución por cluster.
            models.Index(fields=['cluster_label'], name='idx_resml_cluster'),
        ]

    def __str__(self):
        return f'ML {self.usuario.nickname} — {self.creado_en.strftime("%d/%m/%Y %H:%M")}'

    @property
    def alcanza_meta(self):
        return self.gap <= 0

    def recomputar(self):
        """
        Llama a recommend() con los datos originales del registro y devuelve
        el dict completo con planes y SHAP. Usar en la vista de detalle.
        """
        from src.predict import recommend
        user_dict = self.registro.to_user_dict()
        meta_ahorro = float(self.meta.monto) if self.meta else 0.0
        return recommend(user_dict, meta_ahorro)


class PlanSeleccionado(models.Model):
    """
    Plan de optimización elegido por el usuario desde ML Insights.
    Solo puede haber un plan activo por usuario a la vez.
    """
    PLAN_CHOICES = [
        ('Conservador', 'Conservador'),
        ('Balanceado',  'Balanceado'),
        ('Agresivo',    'Agresivo'),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='planes_seleccionados',
    )
    resultado = models.ForeignKey(
        ResultadoML,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='planes_seleccionados',
    )
    nombre_plan       = models.CharField(max_length=20, choices=PLAN_CHOICES)
    ahorro_proyectado = models.FloatField(verbose_name='Ahorro proyectado (S/)')
    meta_ahorro       = models.FloatField(verbose_name='Meta de ahorro (S/)')
    gastos_sugeridos  = models.JSONField(
        help_text='Dict {GASTO_X: valor_optimizado} con los 8 gastos del plan'
    )
    activo           = models.BooleanField(default=True)
    fecha_seleccion  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-fecha_seleccion']
        verbose_name        = 'Plan Seleccionado'
        verbose_name_plural = 'Planes Seleccionados'
        constraints = [
            # Garantiza a nivel de BD un único plan activo por usuario.
            models.UniqueConstraint(
                fields=['usuario'],
                condition=models.Q(activo=True),
                name='unico_plan_activo_por_usuario',
            ),
        ]
        indexes = [
            models.Index(fields=['usuario', 'activo'], name='idx_plansel_user_activo'),
        ]

    def __str__(self):
        return f'{self.usuario.nickname} — {self.nombre_plan} ({self.fecha_seleccion.strftime("%d/%m/%Y")})'

    @property
    def icono(self):
        return {'Conservador': '🌿', 'Balanceado': '⚖️', 'Agresivo': '🚀'}.get(self.nombre_plan, '📋')
