import json
import math
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


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
    # El objetivo debe ser estrictamente positivo (con 0 la meta no tiene sentido y
    # el % de avance sería indefinido) y lo ahorrado no puede ser negativo. Se declara
    # a nivel de MODELO —no solo con `min` en el widget, que es HTML5 y solo actúa en
    # el navegador— para que la regla aplique igual al formulario web y a la API REST.
    monto_objetivo = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name='Monto objetivo (S/)',
        validators=[MinValueValidator(Decimal('0.01'), message='El monto objetivo debe ser mayor a S/ 0.')],
    )
    monto_actual   = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Monto ahorrado (S/)',
        validators=[MinValueValidator(Decimal('0'), message='El monto ahorrado no puede ser negativo.')],
    )
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

    # ── Dinamismo (spec §8.3): se recalcula en cada consulta, nunca queda fijo ────

    @property
    def meses_restantes(self):
        """Meses hasta fecha_limite (>=0). None si no se definió fecha límite."""
        if not self.fecha_limite:
            return None
        hoy = date.today()
        meses = (self.fecha_limite.year - hoy.year) * 12 + (self.fecha_limite.month - hoy.month)
        return max(meses, 0)

    @property
    def cuota_mensual_sugerida(self):
        """Ahorro mensual necesario para cumplir la meta EN EL PLAZO ORIGINAL definido
        (fecha_limite), recalculado con el faltante actual. None sin fecha límite."""
        restantes = self.meses_restantes
        if restantes is None:
            return None
        if restantes == 0:
            return round(self.faltante, 2)
        return round(self.faltante / restantes, 2)

    @property
    def meses_transcurridos(self):
        hoy = date.today()
        inicio = self.creado_en.date() if self.creado_en else hoy
        meses = (hoy.year - inicio.year) * 12 + (hoy.month - inicio.month)
        return max(meses, 1)

    @property
    def ritmo_mensual_actual(self):
        """A qué ritmo (S//mes) ha venido ahorrando el usuario hacia ESTA meta, en
        promedio, desde que la creó."""
        return round(float(self.monto_actual) / self.meses_transcurridos, 2)

    @property
    def plazo_estimado_meses(self):
        """A tu ritmo actual de ahorro, cuántos meses más tomaría completar la meta.
        None si el ritmo actual es 0 (no se puede proyectar)."""
        ritmo = self.ritmo_mensual_actual
        if ritmo <= 0:
            return None
        return math.ceil(self.faltante / ritmo)

    @property
    def desviacion_plazo(self):
        """Compara el plazo estimado (a tu ritmo real) contra el plazo original.
        'adelantado' | 'a_tiempo' | 'atrasado' | None (sin fecha límite o sin ritmo)."""
        restantes, estimado = self.meses_restantes, self.plazo_estimado_meses
        if restantes is None or estimado is None:
            return None
        diff = estimado - restantes
        if diff <= -1:
            return 'adelantado'
        if diff >= 2:
            return 'atrasado'
        return 'a_tiempo'


class ResultadoML(models.Model):
    """
    Resultados escalares de cada ejecución de recommend() en src/predict.py.

    Modelo nuevo: XGBoost Classifier binario (Déficit/Ahorra). Ya NO hay
    K-Means ni montos predichos. Se guardan solo los escalares:
      ahorro_actual (identidad contable real), meta_validada, necesita_recortar,
      clase_predicha, label_predicha, prob_ahorra, confianza, shap_top_features.

    Las opciones de recorte (Suave/Equilibrado/Decidido) y el SHAP completo
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
    # Mes elegido como referencia para clasificar. En el MVP de un solo mes
    # coincide con `registro` (mismo período analizado).
    mes_referencia = models.ForeignKey(
        'financiero.RegistroMensual',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='resultados_referencia',
        verbose_name='Mes de referencia',
    )
    meta = models.ForeignKey(
        MetaMensual,
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )

    # ── Salidas escalares de recommend() ─────────────────────────────────────
    ahorro_actual     = models.FloatField(verbose_name='Ahorro real (S/)')
    meta_validada     = models.FloatField(verbose_name='Meta validada (S/)')
    necesita_recortar = models.FloatField(default=0.0, verbose_name='Falta recortar (S/)')

    # ── Clasificación binaria (XGBoost Classifier) ───────────────────────────
    clase_predicha    = models.IntegerField(default=0, verbose_name='Clase (0=Déficit, 1=Ahorra)')
    label_predicha    = models.CharField(max_length=20, default='', verbose_name='Etiqueta clase')
    prob_ahorra       = models.FloatField(default=0.0, verbose_name='Probabilidad de Ahorrar')
    confianza         = models.CharField(max_length=250, verbose_name='Nivel de confianza')
    shap_top_features = models.JSONField(default=list, verbose_name='Top features SHAP')

    # ── Anti-estatismo (spec §3) ──────────────────────────────────────────────
    # Escenario (tipo de meta) y categoría de gasto que priorizó el counterfactual en
    # ESTE análisis. Se consultan al generar el análisis del mes siguiente para no
    # repetir la misma categoría objetivo / tipo de meta dos meses seguidos si los
    # datos permiten variar (ver recomendaciones.trends.contexto_anti_estatismo).
    escenario           = models.CharField(max_length=40, blank=True, default='',
                                           verbose_name='Escenario del plan')
    categoria_objetivo  = models.CharField(max_length=40, blank=True, default='',
                                           verbose_name='Categoría de gasto priorizada')

    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-creado_en']
        verbose_name        = 'Resultado ML'
        verbose_name_plural = 'Resultados ML'
        indexes = [
            # Historial / dashboard: filtra por usuario y ordena por fecha.
            models.Index(fields=['usuario', '-creado_en'], name='idx_resml_user_fecha'),
            # Métricas admin: distribución por clase (Ahorra/Déficit).
            models.Index(fields=['label_predicha'], name='idx_resml_clase'),
        ]

    def __str__(self):
        return f'ML {self.usuario.nickname} — {self.creado_en.strftime("%d/%m/%Y %H:%M")}'

    @property
    def alcanza_meta(self):
        return self.necesita_recortar <= 0

    def recomputar(self):
        """
        Reproduce el análisis con la separación mes de referencia ≠ mes actual:
          • clasificación + SHAP desde el MES DE REFERENCIA (mes_referencia),
          • opciones (plan counterfactual) desde el MES ACTUAL (registro).
        Devuelve el dict de recommend(mes_actual) con `clase_actual` y
        `diagnostico_shap` sustituidos por los del mes de referencia.

        Reproducción FIEL del escenario (spec §4/§5/§6/§3): si este análisis guardó
        `escenario` (columna nueva), se reusa ese mismo escenario + meta_validada vía
        `forzar_escenario` en vez de reenviar meta_validada como meta explícita — antes
        eso colapsaba SIEMPRE a "meta_usuario" al recomputar (cada vez que el usuario
        reabría su historial perdía el mensaje original: escalamiento, overrides §6,
        etc.). Filas anteriores a esta migración (sin escenario guardado) usan el
        comportamiento previo como fallback.
        """
        from src.predict import classify, recommend, shap_explain
        from recomendaciones.trends import contexto_anti_estatismo, historial_user_dicts
        # historial multi-mes -> el counterfactual prioriza el gasto que más creció.
        historial = historial_user_dicts(self.usuario)
        anti_estatismo = contexto_anti_estatismo(self.usuario, antes_de=self.creado_en)
        if self.escenario:
            plan = recommend(self.registro.to_user_dict(), historial=historial,
                             anti_estatismo=anti_estatismo, forzar_escenario=self.escenario,
                             forzar_objetivo=float(self.meta_validada))
        else:
            # Fallback para análisis previos a esta migración (sin escenario guardado):
            # usar la meta GUARDADA (meta_validada), no self.meta.monto (varios análisis
            # del mismo mes comparten una sola MetaMensual y podría haber sido sobrescrita).
            meta_ahorro = float(self.meta_validada) if self.meta_id else 0.0
            plan = recommend(self.registro.to_user_dict(), meta_ahorro, historial=historial,
                             anti_estatismo=anti_estatismo)
        ref = self.mes_referencia or self.registro
        ref_dict = ref.to_user_dict()
        cls = classify(ref_dict)                                # mes de referencia
        plan['clase_actual'] = cls
        plan['diagnostico_shap'] = shap_explain(ref_dict, top=3)

        # Re-sincronizar la fotografía escalar guardada con este recálculo. Las opciones
        # se recomputan SIEMPRE desde los datos actuales del registro; si el usuario editó
        # ese mes (o el de referencia) tras guardar el análisis, los escalares almacenados
        # quedaban obsoletos y contradecían el plan (p. ej. "falta recortar 460" guardado
        # vs un plan que alcanza la meta recortando 310). Refrescamos para que la vista del
        # historial sea siempre coherente. meta_validada NO se toca para escenarios que el
        # usuario SÍ eligió (es su ancla); para los de déficit (deterministas, sin elección
        # posible) SÍ se resincroniza — ver _sincronizar_escalares.
        self._sincronizar_escalares(plan, cls)
        return plan

    # Escenarios donde el objetivo es 100% determinista (sin elección del usuario) —
    # ver _ESCENARIOS_DETERMINISTAS en src/predict.py, misma lista.
    _ESCENARIOS_DETERMINISTAS = {
        'deficit', 'deficit_bajo', 'deficit_leve_override', 'deficit_significativo_override',
    }

    def _sincronizar_escalares(self, plan, cls):
        """Actualiza (y persiste, solo si cambió) los escalares cacheados del análisis.
        También "autosana" filas anteriores a la migración de anti-estatismo: si no
        tenían escenario/categoria_objetivo guardados, quedan fijados con lo recomputado
        la primera vez que se revisan (para que empiecen a contar en la rotación)."""
        nuevos = {
            'ahorro_actual':     round(float(plan['ahorro_actual']), 2),
            'necesita_recortar': round(float(plan['necesita_recortar']), 2),
            'clase_predicha':    int(cls['clase']),
            'label_predicha':    cls['label'],
            'prob_ahorra':       round(float(cls['probabilidad_ahorra']), 4),
            'confianza':         cls['confianza'],
        }
        if plan.get('escenario') in self._ESCENARIOS_DETERMINISTAS:
            # Sin elección del usuario de por medio: no hay "ancla" que proteger, así
            # que meta_validada también se resincroniza (evita que quede desfasada
            # para siempre, como ocurría con filas heredadas de reglas antiguas).
            nuevos['meta_validada'] = round(float(plan['meta']), 2)
        if not self.escenario and plan.get('escenario'):
            nuevos['escenario'] = plan['escenario']
        if not self.categoria_objetivo and plan.get('categoria_objetivo'):
            nuevos['categoria_objetivo'] = plan['categoria_objetivo']

        def _difiere(actual, nuevo):
            try:
                return abs(float(actual) - float(nuevo)) > 0.01
            except (TypeError, ValueError):
                return str(actual) != str(nuevo)

        if self.pk and any(_difiere(getattr(self, k), v) for k, v in nuevos.items()):
            for k, v in nuevos.items():
                setattr(self, k, v)
            self.save(update_fields=list(nuevos.keys()))


class PlanSeleccionado(models.Model):
    """
    Plan de optimización elegido por el usuario desde ML Insights.
    Solo puede haber un plan activo por usuario a la vez.
    """
    PLAN_CHOICES = [
        ('Suave',       'Suave'),
        ('Equilibrado', 'Equilibrado'),
        ('Decidido',    'Decidido'),
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
    # Spec §8.2: si el usuario no actualiza su plan al iniciar un mes nuevo, se muestra
    # un aviso persistente (no bloqueante) hasta que actualice O lo descarte a propósito.
    aviso_descartado = models.BooleanField(default=False, verbose_name='Aviso de plan desactualizado descartado')

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
        return {'Suave': '🌿', 'Equilibrado': '⚖️', 'Decidido': '🚀'}.get(self.nombre_plan, '📋')
