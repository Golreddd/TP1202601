from django.db import models
from django.conf import settings


class RegistroMensual(models.Model):
    """
    Registro financiero mensual de un usuario.
    Contiene los 13 campos de entrada de src/predict.py:
      - Perfil (3): EDAD, NIVEL_EDUC, MIEMBROS_HOGAR  → vienen de usuario directamente
      - Ingresos (2): ING_PLANILLA, ING_INFORMAL
      - Gastos (8):   GASTO_ALIMENTOS … GASTO_OTROS_BIENES
    """
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='registros',
    )
    # Siempre el primer día del mes: YYYY-MM-01
    periodo = models.DateField(verbose_name='Período (mes)')

    # ── Ingresos ──────────────────────────────────────────────────────────────
    ing_planilla = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name='Ingreso en planilla (S/)',
    )
    ing_informal = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name='Ingreso informal (S/)',
    )

    # ── Bonificación / ingreso extraordinario del período ─────────────────────
    # Ingreso extra del mes (CTS, gratificación, otro bono). Se SUMA al ingreso
    # de planilla antes de ejecutar el ML (ver to_user_dict), de modo que la
    # predicción refleje el ingreso real de ese mes.
    bonif_monto = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name='Bonificación (CTS, gratificación, etc.) (S/)',
    )

    # ── Gastos (exactamente los 8 de GASTO_COLS en predict.py) ───────────────
    gasto_alimentos          = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Alimentos (S/)')
    gasto_vestido            = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Vestido (S/)')
    gasto_vivienda_servicios = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Vivienda y servicios (S/)')
    gasto_salud              = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Salud (S/)')
    gasto_transporte         = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Transporte (S/)')
    gasto_comunicaciones     = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Comunicaciones (S/)')
    gasto_educacion          = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Educación (S/)')
    gasto_otros_bienes       = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Otros bienes (S/)')

    creado_en      = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['usuario', 'periodo']
        ordering        = ['-periodo']
        verbose_name        = 'Registro Mensual'
        verbose_name_plural = 'Registros Mensuales'

    def __str__(self):
        return f'{self.usuario.nickname} — {self.periodo.strftime("%B %Y")}'

    # ── Propiedades calculadas (no se almacenan en BD) ────────────────────────

    @property
    def tiene_bonificacion(self):
        """True si el período registró un ingreso extraordinario."""
        return float(self.bonif_monto) > 0

    @property
    def ing_planilla_total(self):
        """Ingreso de planilla incluyendo la bonificación del período."""
        return float(self.ing_planilla) + float(self.bonif_monto)

    @property
    def ing_total(self):
        return self.ing_planilla_total + float(self.ing_informal)

    @property
    def gasto_total(self):
        return sum([
            float(self.gasto_alimentos),
            float(self.gasto_vestido),
            float(self.gasto_vivienda_servicios),
            float(self.gasto_salud),
            float(self.gasto_transporte),
            float(self.gasto_comunicaciones),
            float(self.gasto_educacion),
            float(self.gasto_otros_bienes),
        ])

    @property
    def ahorro_bruto(self):
        return self.ing_total - self.gasto_total

    @property
    def tasa_ahorro(self):
        if self.ing_total > 0:
            return round(self.ahorro_bruto / self.ing_total * 100, 1)
        return 0.0

    def gastos_por_categoria(self):
        """Dict legible para templates y charts."""
        return {
            'Alimentos':       float(self.gasto_alimentos),
            'Vestido':         float(self.gasto_vestido),
            'Vivienda/Serv.':  float(self.gasto_vivienda_servicios),
            'Salud':           float(self.gasto_salud),
            'Transporte':      float(self.gasto_transporte),
            'Comunicaciones':  float(self.gasto_comunicaciones),
            'Educación':       float(self.gasto_educacion),
            'Otros':           float(self.gasto_otros_bienes),
        }

    def to_user_dict(self):
        """
        Construye el user_dict que espera recommend() en src/predict.py.
        Los campos de perfil (EDAD, NIVEL_EDUC, MIEMBROS_HOGAR) vienen
        directamente del objeto usuario — ya no hace falta un JOIN a PerfilFinanciero.
        """
        u = self.usuario
        return {
            'EDAD':                   u.edad or 25,
            'NIVEL_EDUC':             u.nivel_educ or 3,
            'MIEMBROS_HOGAR':         u.miembros_hogar or 1,
            # La bonificación se suma al ingreso de planilla del período para
            # que el ahorro predicho refleje el ingreso real de ese mes.
            'ING_PLANILLA':           self.ing_planilla_total,
            'ING_INFORMAL':           float(self.ing_informal),
            'GASTO_ALIMENTOS':        float(self.gasto_alimentos),
            'GASTO_VESTIDO':          float(self.gasto_vestido),
            'GASTO_VIVIENDA_SERVICIOS': float(self.gasto_vivienda_servicios),
            'GASTO_SALUD':            float(self.gasto_salud),
            'GASTO_TRANSPORTE':       float(self.gasto_transporte),
            'GASTO_COMUNICACIONES':   float(self.gasto_comunicaciones),
            'GASTO_EDUCACION':        float(self.gasto_educacion),
            'GASTO_OTROS_BIENES':     float(self.gasto_otros_bienes),
        }
