from django.db import models
from django.conf import settings


class Racha(models.Model):
    """Racha de días consecutivos con registro activo (HU0060–HU0062)."""
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='racha',
    )
    dias_consecutivos = models.PositiveIntegerField(default=0)
    racha_maxima = models.PositiveIntegerField(default=0)
    ultimo_registro = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Racha'
        verbose_name_plural = 'Rachas'

    def __str__(self):
        return f'{self.usuario.nickname}: {self.dias_consecutivos} días'

    @property
    def dias_vigentes(self):
        """Días de racha REALMENTE vigentes hoy.

        `dias_consecutivos` solo se recalcula cuando el usuario vuelve a registrar,
        así que por sí solo seguiría mostrando "🔥 5 días" meses después de que el
        usuario dejó de registrar. Esta propiedad caduca la racha al consultarla:
        sigue vigente solo si el último registro fue hoy o ayer.
        """
        from datetime import date, timedelta
        if not self.ultimo_registro:
            return 0
        if date.today() - self.ultimo_registro > timedelta(days=1):
            return 0
        return self.dias_consecutivos

    def actualizar(self, fecha_hoy):
        """
        Actualiza la racha según la fecha del nuevo registro.
        Llama este método desde la view que guarda un RegistroMensual.
        """
        from datetime import timedelta
        if self.ultimo_registro is None:
            self.dias_consecutivos = 1
        elif fecha_hoy == self.ultimo_registro + timedelta(days=1):
            self.dias_consecutivos += 1
        elif fecha_hoy > self.ultimo_registro + timedelta(days=1):
            self.dias_consecutivos = 1  # racha rota
        # Si fecha_hoy == ultimo_registro → mismo día, no cambia

        if self.dias_consecutivos > self.racha_maxima:
            self.racha_maxima = self.dias_consecutivos
        self.ultimo_registro = fecha_hoy
        self.save()


class Logro(models.Model):
    """Definición de un logro desbloqueable (HU0058–HU0062)."""
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField()
    icono = models.CharField(max_length=10, help_text='Emoji del logro')
    puntos = models.PositiveSmallIntegerField(default=10)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden']
        verbose_name = 'Logro'
        verbose_name_plural = 'Logros'

    def __str__(self):
        return self.nombre


class LogroUsuario(models.Model):
    """Logro desbloqueado por un usuario específico."""
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='logros_obtenidos',
    )
    logro = models.ForeignKey(
        Logro,
        on_delete=models.CASCADE,
        related_name='usuarios',
    )
    obtenido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = 'gamificacion_logrousuario'
        unique_together = ['usuario', 'logro']
        verbose_name    = 'Logro de Usuario'
        verbose_name_plural = 'Logros de Usuarios'

    def __str__(self):
        return f'{self.usuario.nickname} — {self.logro.nombre}'
