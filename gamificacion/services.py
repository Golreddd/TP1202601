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

        # Rachas
        try:
            racha = usuario.racha
            if racha.dias_consecutivos >= 7 and _otorgar(usuario, 'RACHA_7'):
                nuevos.append('RACHA_7')
            if racha.dias_consecutivos >= 30 and _otorgar(usuario, 'RACHA_30'):
                nuevos.append('RACHA_30')
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

    # ── Logros de ANÁLISIS ML ─────────────────────────────────────────────────
    if contexto == 'ml':
        total_ml = usuario.resultados_ml.count()

        if total_ml >= 1 and _otorgar(usuario, 'PRIMER_ML'):
            nuevos.append('PRIMER_ML')

        # Clasificado como "Ahorra" (clase 1) por el XGBoost Classifier
        ultimo_ml = usuario.resultados_ml.order_by('-creado_en').first()
        if (ultimo_ml
                and ultimo_ml.clase_predicha == 1
                and _otorgar(usuario, 'CLUSTER_AHORRADOR')):
            nuevos.append('CLUSTER_AHORRADOR')

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

    return nuevos
