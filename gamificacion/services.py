"""
Lógica de desbloqueo de logros (gamificación).

Punto de entrada único: verificar_y_otorgar_logros(usuario, contexto)
Se llama desde las vistas API tras cada acción relevante.
"""
import logging

from django.db.models import F

from gamificacion.models import Logro, LogroUsuario

logger = logging.getLogger(__name__)


def _otorgar(usuario, codigo: str) -> bool:
    """
    Otorga el logro al usuario si aún no lo tiene.
    Retorna True si fue desbloqueado ahora, False si ya lo tenía.
    """
    try:
        logro = Logro.objects.get(codigo=codigo)
    except Logro.DoesNotExist:
        logger.warning('Logro "%s" no existe en la BD.', codigo)
        return False

    _, creado = LogroUsuario.objects.get_or_create(usuario=usuario, logro=logro)
    if creado:
        logger.info('Logro "%s" desbloqueado para %s.', codigo, usuario.nickname)
    return creado


def _mes_anterior(periodo):
    if periodo.month == 1:
        return periodo.replace(year=periodo.year - 1, month=12)
    return periodo.replace(month=periodo.month - 1)


def _racha_metas_mensuales_cumplidas(usuario) -> int:
    """Spec §2 paso 5 (cierre de mes): cuenta cuántos meses consecutivos, empezando por
    el más reciente hacia atrás, el usuario CUMPLIÓ la meta mensual que se le propuso.

    La meta de un mes P es PROSPECTIVA (spec §2: "para este mes te sugerimos...") — se
    evalúa contra el resultado real del mes SIGUIENTE a P, no contra P mismo: P ya se
    usó como diagnóstico/counterfactual para generarla (simplificación "un solo mes
    coherente"), así que comparar la meta de P contra el propio ahorro de P sería
    circular (la meta de escalamiento/incremental siempre es MAYOR al ahorro que la
    originó, por construcción — "cumplida" sería casi imposible).
    Solo cuenta meses CALENDARIO consecutivos (sin huecos de registro); se corta en el
    primer mes sin meta previa definida o que no la cumplió.
    """
    from financiero.models import RegistroMensual
    from recomendaciones.models import MetaMensual

    regs_por_periodo = {
        r.periodo: r
        for r in RegistroMensual.objects.filter(usuario=usuario).order_by('-periodo')[:13]
    }
    if not regs_por_periodo:
        return 0

    racha = 0
    periodo = max(regs_por_periodo)
    while periodo in regs_por_periodo:
        anterior = _mes_anterior(periodo)
        try:
            meta = MetaMensual.objects.get(usuario=usuario, periodo=anterior)
        except MetaMensual.DoesNotExist:
            break
        if float(regs_por_periodo[periodo].ahorro_bruto) >= float(meta.monto):
            racha += 1
            periodo = anterior
        else:
            break
    return racha


def _racha_plan_cumplido(usuario) -> int:
    """Cuenta cuántos meses consecutivos, del más reciente hacia atrás, el usuario
    cumplió el plan de recorte que tiene activo — mismo criterio de 'cumple' (10% de
    tolerancia) que ya usa gamificacion/views.py::progreso, vía la única fuente en
    recomendaciones.trends.comparacion_plan (no se reinventa el umbral aquí)."""
    from recomendaciones.models import PlanSeleccionado
    from recomendaciones.trends import comparacion_plan

    plan_activo = PlanSeleccionado.objects.filter(
        usuario=usuario, activo=True
    ).select_related('resultado__registro').first()
    if not plan_activo:
        return 0

    filas = comparacion_plan(usuario, plan_activo)  # orden ascendente por periodo
    racha = 0
    for fila in reversed(filas):
        if fila['cumple']:
            racha += 1
        else:
            break
    return racha


def _racha_aportes_consecutivos(usuario) -> int:
    """Cuenta cuántos meses CALENDARIO consecutivos, del más reciente hacia atrás, el
    usuario aportó ahorro a alguna meta (APORTES_CONSTANTES). Un mes cuenta si tiene al
    menos un AporteMeta cuyo registro.periodo es ese mes; se corta en el primer hueco."""
    from recomendaciones.models import AporteMeta

    periodos_con_aporte = set(
        AporteMeta.objects.filter(usuario=usuario).values_list('registro__periodo', flat=True)
    )
    if not periodos_con_aporte:
        return 0

    racha = 0
    periodo = max(periodos_con_aporte)
    while periodo in periodos_con_aporte:
        racha += 1
        periodo = _mes_anterior(periodo)
    return racha


def verificar_y_otorgar_logros(usuario, contexto: str = '') -> list:
    """
    Evalúa el estado del usuario y desbloquea los logros que merezca.

    Parámetros
    ----------
    usuario : accounts.models.Usuario
    contexto : str
        'registro'        → después de crear un RegistroMensual
        'ml'              → después de ejecutar un análisis ML
        'perfil'          → después de actualizar datos de perfil
        'meta_completada' → después de que una MetaLargoPlazo alcanza 100%

    Retorna
    -------
    list[str] — códigos de logros recién desbloqueados (para notificar al usuario)
    """
    nuevos = []

    # ── PERFIL_COMPLETO ───────────────────────────────────────────────────────
    if contexto in ('perfil', 'registro', 'ml'):
        if usuario.perfil_completo and _otorgar(usuario, 'PERFIL_COMPLETO'):
            nuevos.append('PERFIL_COMPLETO')

    # ── Logros de REGISTRO ────────────────────────────────────────────────────
    if contexto == 'registro':
        total = usuario.registros.count()

        if total >= 1 and _otorgar(usuario, 'PRIMER_REGISTRO'):
            nuevos.append('PRIMER_REGISTRO')

        if total >= 5 and _otorgar(usuario, 'CINCO_REGISTROS'):
            nuevos.append('CINCO_REGISTROS')
        if total >= 10 and _otorgar(usuario, 'DIEZ_REGISTROS'):
            nuevos.append('DIEZ_REGISTROS')
        if total >= 20 and _otorgar(usuario, 'VEINTE_REGISTROS'):
            nuevos.append('VEINTE_REGISTROS')
        if total >= 50 and _otorgar(usuario, 'CINCUENTA_REGISTROS'):
            nuevos.append('CINCUENTA_REGISTROS')

        # Rachas
        try:
            racha = usuario.racha
            if racha.dias_consecutivos >= 7 and _otorgar(usuario, 'RACHA_7'):
                nuevos.append('RACHA_7')
            if racha.dias_consecutivos >= 30 and _otorgar(usuario, 'RACHA_30'):
                nuevos.append('RACHA_30')
            if racha.dias_consecutivos >= 60 and _otorgar(usuario, 'RACHA_60'):
                nuevos.append('RACHA_60')
            if racha.dias_consecutivos >= 90 and _otorgar(usuario, 'RACHA_90'):
                nuevos.append('RACHA_90')
        except Exception:
            pass

        # Tasa de ahorro >= 20% en el último registro
        ultimo = usuario.registros.order_by('-periodo').first()
        if ultimo and ultimo.tasa_ahorro >= 20 and _otorgar(usuario, 'AHORRADOR_20'):
            nuevos.append('AHORRADOR_20')

        # Tres meses consecutivos con ahorro positivo
        recientes = list(usuario.registros.order_by('-periodo')[:3])
        if (len(recientes) == 3
                and all(r.ahorro_bruto > 0 for r in recientes)
                and _otorgar(usuario, 'TRES_MESES_VERDE')):
            nuevos.append('TRES_MESES_VERDE')

        # Cierre de mes (spec §2 paso 5): cumplió la meta mensual propuesta.
        racha_metas = _racha_metas_mensuales_cumplidas(usuario)
        if racha_metas >= 1 and _otorgar(usuario, 'META_MENSUAL_CUMPLIDA'):
            nuevos.append('META_MENSUAL_CUMPLIDA')
        if racha_metas >= 3 and _otorgar(usuario, 'RACHA_METAS_3'):
            nuevos.append('RACHA_METAS_3')

    # ── Logros de ANÁLISIS ML ─────────────────────────────────────────────────
    if contexto == 'ml':
        total_ml = usuario.resultados_ml.count()

        if total_ml >= 1 and _otorgar(usuario, 'PRIMER_ML'):
            nuevos.append('PRIMER_ML')
        if total_ml >= 5 and _otorgar(usuario, 'CINCO_ML'):
            nuevos.append('CINCO_ML')
        if total_ml >= 10 and _otorgar(usuario, 'DIEZ_ML'):
            nuevos.append('DIEZ_ML')

        # Clasificado como "Ahorra" (clase 1) por el XGBoost Classifier
        ultimo_ml = usuario.resultados_ml.order_by('-creado_en').first()
        if (ultimo_ml
                and ultimo_ml.clase_predicha == 1
                and _otorgar(usuario, 'CLUSTER_AHORRADOR')):
            nuevos.append('CLUSTER_AHORRADOR')

    # ── Logros de PLAN (leídos del historial, sin disparador dedicado) ────────
    # No hay una vista/acción "adoptar plan" que llame a este servicio (PlanSeleccionado
    # se crea desde la API de ML Insights). En vez de agregar un disparador nuevo ahí,
    # se leen aquí de forma pasiva —PlanSeleccionado y comparacion_plan ya son el
    # historial completo— aprovechando que 'registro' y 'ml' son los contextos que más
    # seguido se disparan durante el uso normal de la app.
    if contexto in ('registro', 'ml'):
        from recomendaciones.models import PlanSeleccionado

        if PlanSeleccionado.objects.filter(usuario=usuario).exists() and _otorgar(usuario, 'PRIMER_PLAN'):
            nuevos.append('PRIMER_PLAN')

        if _racha_plan_cumplido(usuario) >= 3 and _otorgar(usuario, 'PLAN_3_MESES'):
            nuevos.append('PLAN_3_MESES')

    # ── Logros de METAS ───────────────────────────────────────────────────────
    # 'meta_completada' lo disparan meta_create / meta_update (web) y la API.
    if contexto == 'meta_completada':
        from recomendaciones.models import MetaLargoPlazo

        metas = MetaLargoPlazo.objects.filter(usuario=usuario, activa=True)

        # PRIMERA_META: por tener al menos una meta de ahorro creada.
        if metas.exists() and _otorgar(usuario, 'PRIMERA_META'):
            nuevos.append('PRIMERA_META')

        completadas = metas.filter(monto_actual__gte=F('monto_objetivo')).count()

        if completadas >= 1 and _otorgar(usuario, 'META_CUMPLIDA'):
            nuevos.append('META_CUMPLIDA')

        if completadas >= 5 and _otorgar(usuario, 'MAESTRO_AHORRO'):
            nuevos.append('MAESTRO_AHORRO')

        # A mitad de camino: al menos una meta activa (no completada) con >=50% avance.
        # Se reutiliza el umbral de porcentaje vía F() en la propia query, sin recalcular
        # la propiedad `porcentaje` del modelo (equivalente: actual >= objetivo * 0.5).
        if metas.filter(
            monto_actual__gte=F('monto_objetivo') * 0.5,
            monto_actual__lt=F('monto_objetivo'),
        ).exists() and _otorgar(usuario, 'META_MITAD'):
            nuevos.append('META_MITAD')

        if metas.count() >= 3 and _otorgar(usuario, 'TRES_METAS_ACTIVAS'):
            nuevos.append('TRES_METAS_ACTIVAS')

        # Aportes a metas (Tarea 2): disparado por financiero.distribuir_ahorro justo
        # después de crear los AporteMeta del mes.
        from recomendaciones.models import AporteMeta

        if AporteMeta.objects.filter(usuario=usuario).exists() and _otorgar(usuario, 'APORTE_A_META'):
            nuevos.append('APORTE_A_META')

        if _racha_aportes_consecutivos(usuario) >= 3 and _otorgar(usuario, 'APORTES_CONSTANTES'):
            nuevos.append('APORTES_CONSTANTES')

    return nuevos
