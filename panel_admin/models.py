from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    """
    Registro de acciones administrativas (HU0073, HU0079).
    Se crea automáticamente en cada acción del panel de administración.
    """
    ACCIONES = [
        ('LOGIN_ADMIN',        'Inicio de sesión (admin)'),
        ('LOGOUT_ADMIN',       'Cierre de sesión (admin)'),
        ('CREAR_USUARIO',      'Crear usuario'),
        ('VER_USUARIO',        'Ver detalles de usuario'),
        ('ACTIVAR_USUARIO',    'Activar cuenta de usuario'),
        ('DESACTIVAR_USUARIO', 'Desactivar cuenta de usuario'),
        ('CAMBIAR_ROL',        'Cambiar rol de usuario'),
        ('EXPORTAR_DATOS',     'Exportar datos del sistema'),
        ('VER_ESTADISTICAS',   'Ver estadísticas del sistema'),
    ]

    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='acciones_admin',
        verbose_name='Administrador',
    )
    accion = models.CharField(max_length=30, choices=ACCIONES, verbose_name='Acción')
    usuario_objetivo = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='logs_recibidos',
        verbose_name='Usuario afectado',
    )
    detalle    = models.TextField(blank=True, verbose_name='Detalle')
    ip_address = models.CharField(max_length=45, null=True, blank=True, verbose_name='IP')
    fecha      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-fecha']
        verbose_name        = 'Registro de Auditoría'
        verbose_name_plural = 'Registros de Auditoría'

    def __str__(self):
        admin_str = self.admin.nickname if self.admin else 'Sistema'
        return f'[{self.fecha.strftime("%d/%m/%Y %H:%M")}] {admin_str}: {self.get_accion_display()}'

    @classmethod
    def registrar(cls, admin, accion, usuario_objetivo=None, detalle='', request=None):
        """Helper para crear un log desde cualquier view."""
        ip = None
        if request:
            x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')
        return cls.objects.create(
            admin=admin,
            accion=accion,
            usuario_objetivo=usuario_objetivo,
            detalle=detalle,
            ip_address=ip,
        )


class ValidacionPrimerUso(models.Model):
    """
    Caso de prueba con usuarios reales: la PRIMERA clasificación ML de cada usuario,
    contrastada con su ahorro real del mismo mes (identidad ingreso − gasto).

    El modelo se entrena con split 80/20 (train/valid, sin test); estos registros
    hacen las veces de conjunto de prueba. Se captura UNA sola vez por usuario
    (OneToOne) y no se recalcula aunque el usuario edite o repita el análisis.
    Clase positiva = Ahorra (1).
    """
    TP, FP, TN, FN = 'TP', 'FP', 'TN', 'FN'
    TIPOS = [
        (TP, 'Verdadero positivo'),
        (FP, 'Falso positivo'),
        (TN, 'Verdadero negativo'),
        (FN, 'Falso negativo'),
    ]

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='validacion_ml',
        verbose_name='Usuario',
    )
    resultado = models.OneToOneField(
        'recomendaciones.ResultadoML',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='validacion_primer_uso',
        verbose_name='Análisis ML origen',
    )
    periodo        = models.DateField(verbose_name='Período analizado')
    clase_predicha = models.IntegerField(verbose_name='Clase predicha (0=Déficit, 1=Ahorra)')
    prob_ahorra    = models.FloatField(verbose_name='Probabilidad de Ahorrar')
    confianza      = models.CharField(max_length=20, verbose_name='Confianza')
    ing_total      = models.FloatField(verbose_name='Ingreso total (S/)')
    gasto_total    = models.FloatField(verbose_name='Gasto total (S/)')
    ahorro_real    = models.FloatField(verbose_name='Ahorro real (S/)')
    clase_real     = models.IntegerField(verbose_name='Clase real (0=Déficit, 1=Ahorra)')
    tipo           = models.CharField(max_length=2, choices=TIPOS, verbose_name='Resultado')
    creado_en      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-creado_en']
        verbose_name        = 'Validación ML (primer uso)'
        verbose_name_plural = 'Validaciones ML (primer uso)'

    def __str__(self):
        return f'{self.usuario.nickname}: {self.tipo}'

    @property
    def acierto(self) -> bool:
        return self.tipo in (self.TP, self.TN)

    @property
    def label_predicha(self) -> str:
        return 'Ahorra' if self.clase_predicha == 1 else 'Déficit'

    @property
    def label_real(self) -> str:
        return 'Ahorra' if self.clase_real == 1 else 'Déficit'

    @staticmethod
    def clasificar_tipo(clase_predicha: int, clase_real: int) -> str:
        if clase_predicha == 1:
            return 'TP' if clase_real == 1 else 'FP'
        return 'FN' if clase_real == 1 else 'TN'

    @classmethod
    def registrar_si_primero(cls, resultado):
        """Crea el caso de prueba del usuario a partir de `resultado` si aún no tiene
        uno. Devuelve la instancia creada o None si ya existía."""
        from src.preprocessing import ahorro_identidad, gasto_total, ing_total

        if cls.objects.filter(usuario_id=resultado.usuario_id).exists():
            return None
        registro = resultado.mes_referencia or resultado.registro
        d = registro.to_user_dict()
        ahorro = float(ahorro_identidad(d))
        clase_real = int(ahorro >= 0)   # mismo criterio que binary_target() del entrenamiento
        obj, creado = cls.objects.get_or_create(
            usuario_id=resultado.usuario_id,
            defaults={
                'resultado':      resultado,
                'periodo':        registro.periodo,
                'clase_predicha': int(resultado.clase_predicha),
                'prob_ahorra':    float(resultado.prob_ahorra),
                'confianza':      resultado.confianza[:20],
                'ing_total':      float(ing_total(d)),
                'gasto_total':    float(gasto_total(d)),
                'ahorro_real':    ahorro,
                'clase_real':     clase_real,
                'tipo':           cls.clasificar_tipo(int(resultado.clase_predicha), clase_real),
            },
        )
        return obj if creado else None
