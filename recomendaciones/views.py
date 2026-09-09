import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from core.constants import MESES_ES
from financiero.models import RegistroMensual
from recomendaciones.forms import MetaLargoPlazoForm
from recomendaciones.models import MetaLargoPlazo, PlanSeleccionado, ResultadoML


@login_required
def ml_insights(request):
    """GET /recomendaciones/ — Página ML Insights con último resultado."""
    historial_qs = ResultadoML.objects.filter(
        usuario=request.user
    ).select_related('registro', 'mes_referencia').order_by('-creado_en')

    ultimo = historial_qs.first()
    detalle = None
    planes_convergen = False
    meta_inalcanzable = False
    ml_js = None  # JSON string for safe JS injection (avoids locale float issues)

    if ultimo:
        try:
            detalle = ultimo.recomputar()
        except Exception:
            detalle = None

        if detalle and detalle.get('opciones'):
            opciones = detalle['opciones']
            if len(opciones) >= 2:
                primer_ahorro = opciones[0].get('ahorro_resultante', 0)
                planes_convergen = all(
                    abs(o.get('ahorro_resultante', 0) - primer_ahorro) < 1.0
                    for o in opciones[1:]
                )
            # Meta inalcanzable: ninguna estrategia de recorte alcanza el objetivo.
            meta_inalcanzable = not any(o.get('alcanza_meta') for o in opciones)

        if detalle and ultimo.registro:
            try:
                ml_js = json.dumps({
                    'ahorro':     round(float(ultimo.ahorro_actual), 2),
                    'meta':       round(float(ultimo.meta_validada), 2),
                    'clase':      int(ultimo.clase_predicha),
                    'label':      ultimo.label_predicha,
                    'probAhorra': round(float(ultimo.prob_ahorra), 4),
                    'ingTotal':   round(float(ultimo.registro.ing_total), 2),
                    'gastoTotal': round(float(ultimo.registro.gasto_total), 2),
                    'opciones':   detalle.get('opciones', []),
                    'shap':       detalle.get('diagnostico_shap', []),
                }, ensure_ascii=False)
            except Exception:
                ml_js = None

    plan_activo = PlanSeleccionado.objects.filter(
        usuario=request.user, activo=True
    ).first()

    # Registros disponibles para elegir con cuál ejecutar el análisis.
    # Se serializan con json.dumps para evitar el problema de formato de
    # decimales por el locale es-PE al inyectarlos en JS.
    from recomendaciones.trends import es_mes_atipico
    from src.predict import classify, objetivo_suave_deficitario

    def _perfil_y_meta_suave(r):
        """Perfil (0=deficitario) y meta suave por registro, para que el menú de metas
        ofrezca la tarjeta "Ahorro suave" con el MISMO monto que resolverá el servidor."""
        d = r.to_user_dict()
        try:
            deficitario = classify(d)['clase'] == 0
        except Exception:
            deficitario = False
        return deficitario, objetivo_suave_deficitario(d)

    registros_qs = RegistroMensual.objects.filter(
        usuario=request.user
    ).order_by('-periodo')
    registros_js = json.dumps([
        {
            'id':          r.id,
            'perfilDeficitario': perfil_suave[0],
            'suave10':     perfil_suave[1],
            'mes':         MESES_ES.get(r.periodo.month, ''),
            'anio':        r.periodo.year,
            'ingTotal':    round(r.ing_total, 2),
            'gastoTotal':  round(r.gasto_total, 2),
            'ingPlanilla': round(float(r.ing_planilla), 2),
            'ingInformal': round(float(r.ing_informal), 2),
            'bonif':       round(float(r.bonif_monto), 2),
            'ahorroBruto': round(r.ahorro_bruto, 2),
            'gastos':      r.gastos_por_categoria(),
            'esAtipico':   es_mes_atipico(r),
        }
        for r in registros_qs
        for perfil_suave in [_perfil_y_meta_suave(r)]   # una sola clasificación por registro
    ], ensure_ascii=False)

    # Mes de referencia del último análisis: se pre-selecciona en el formulario
    # para que, tras ejecutar, el selector recuerde el mes elegido (no resetee).
    ultima_ref_id = None
    if ultimo:
        ultima_ref_id = ultimo.mes_referencia_id or ultimo.registro_id

    # Paginación del historial (8 por página) para que no crezca indefinidamente.
    paginator = Paginator(historial_qs, 8)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Análisis de tendencia multi-mes (para la tarjeta de contexto).
    from recomendaciones.trends import analizar_tendencia, candidatos_meta
    tendencia = analizar_tendencia(request.user)

    # El plan ya se recomputó CON historial: predict.py marcó cada recorte que ataca
    # una categoría en aumento (por_tendencia). Solo verificamos si aparece, para la nota.
    if tendencia and detalle:
        tendencia['en_plan'] = any(
            r.get('por_tendencia')
            for op in detalle.get('opciones', [])
            for r in op.get('reducciones', [])
        )

    # Candidatos del menú de metas (spec §4, Opción A) — se muestran ANTES de ejecutar
    # el análisis, para que el usuario elija con qué meta correr el plan. `ideal_20`
    # (20% del ingreso) se calcula en el cliente por mes elegido (depende del ingreso
    # de ESE mes, no del perfil general) — ver poblarSelectorRegistros() en el JS.
    candidatos_js = json.dumps(candidatos_meta(request.user, tendencia=tendencia), ensure_ascii=False)

    return render(request, 'recomendaciones/ml_insights.html', {
        'ultimo':            ultimo,
        'detalle':           detalle,
        'page_obj':          page_obj,
        'total_analisis':    paginator.count,
        'tendencia':         tendencia,
        'planes_convergen':  planes_convergen,
        'meta_inalcanzable': meta_inalcanzable,
        'ml_js':             ml_js,
        'plan_activo_nombre': plan_activo.nombre_plan if plan_activo else '',
        'tiene_registros':   registros_qs.exists(),
        'registros_js':      registros_js,
        'ultima_ref_id':     ultima_ref_id,
        'candidatos_js':     candidatos_js,
    })


@login_required
def historial_detalle(request, pk):
    """
    GET /recomendaciones/historial/<pk>/ — Detalle de un análisis ML pasado.

    Muestra las recomendaciones (planes + SHAP + métricas) de un ResultadoML
    ya guardado, recomputadas desde su registro original. NO ejecuta un
    análisis nuevo ni guarda nada.
    """
    resultado = get_object_or_404(
        ResultadoML.objects.select_related('registro', 'meta'),
        pk=pk, usuario=request.user,
    )

    detalle = None
    planes_convergen = False
    ml_js = None

    try:
        detalle = resultado.recomputar()
    except Exception:
        detalle = None

    if detalle and detalle.get('opciones'):
        opciones = detalle['opciones']
        if len(opciones) >= 2:
            primer_ahorro = opciones[0].get('ahorro_resultante', 0)
            planes_convergen = all(
                abs(o.get('ahorro_resultante', 0) - primer_ahorro) < 1.0
                for o in opciones[1:]
            )

    if detalle and resultado.registro:
        try:
            ml_js = json.dumps({
                'ahorro':     round(float(resultado.ahorro_actual), 2),
                'meta':       round(float(resultado.meta_validada), 2),
                'clase':      int(resultado.clase_predicha),
                'label':      resultado.label_predicha,
                'probAhorra': round(float(resultado.prob_ahorra), 4),
                'ingTotal':   round(float(resultado.registro.ing_total), 2),
                'gastoTotal': round(float(resultado.registro.gasto_total), 2),
                'opciones':   detalle.get('opciones', []),
                'shap':       detalle.get('diagnostico_shap', []),
            }, ensure_ascii=False)
        except Exception:
            ml_js = None

    plan_activo = PlanSeleccionado.objects.filter(
        usuario=request.user, activo=True
    ).first()

    return render(request, 'recomendaciones/historial_detalle.html', {
        'ultimo':             resultado,   # el partial usa el nombre `ultimo`
        'detalle':            detalle,
        'planes_convergen':   planes_convergen,
        'ml_js':              ml_js,
        'plan_activo_nombre': plan_activo.nombre_plan if plan_activo else '',
    })


@login_required
def descartar_aviso_plan(request):
    """POST /recomendaciones/descartar-aviso-plan/ — spec §8.2: el usuario descarta
    conscientemente el aviso de "plan desactualizado" sin necesidad de actualizar el
    plan todavía. No bloquea el uso de la app; solo deja de mostrarse hasta que el
    usuario elija un nuevo plan (lo que crea un PlanSeleccionado nuevo de todos modos)."""
    if request.method == 'POST':
        PlanSeleccionado.objects.filter(usuario=request.user, activo=True).update(aviso_descartado=True)
    return redirect(request.META.get('HTTP_REFERER') or 'financiero:dashboard')


@login_required
def metas(request):
    """GET /recomendaciones/metas/ — Lista de metas de ahorro a largo plazo."""
    metas_qs = MetaLargoPlazo.objects.filter(
        usuario=request.user, activa=True
    ).order_by('-creado_en')
    return render(request, 'recomendaciones/metas.html', {'metas': metas_qs})


@login_required
def meta_create(request):
    """GET/POST /recomendaciones/metas/nueva/"""
    if request.method == 'POST':
        form = MetaLargoPlazoForm(request.POST)
        if form.is_valid():
            meta = form.save(commit=False)
            meta.usuario = request.user
            meta.save()
            from gamificacion.services import verificar_y_otorgar_logros
            verificar_y_otorgar_logros(request.user, contexto='meta_completada')
            messages.success(request, '✅ Meta de ahorro creada correctamente.')
            return redirect('recomendaciones:metas')
    else:
        form = MetaLargoPlazoForm()

    return render(request, 'recomendaciones/meta_form.html', {
        'form':        form,
        'es_creacion': True,
        'titulo':      'Nueva Meta de Ahorro',
    })


@login_required
def meta_update(request, pk):
    """GET/POST /recomendaciones/metas/<pk>/editar/"""
    meta = get_object_or_404(MetaLargoPlazo, pk=pk, usuario=request.user)

    if request.method == 'POST':
        form = MetaLargoPlazoForm(request.POST, instance=meta)
        if form.is_valid():
            form.save()
            from gamificacion.services import verificar_y_otorgar_logros
            verificar_y_otorgar_logros(request.user, contexto='meta_completada')
            messages.success(request, '✅ Meta actualizada correctamente.')
            return redirect('recomendaciones:metas')
    else:
        form = MetaLargoPlazoForm(
            instance=meta,
            initial={'fecha_limite': meta.fecha_limite.strftime('%Y-%m') if meta.fecha_limite else ''},
        )

    return render(request, 'recomendaciones/meta_form.html', {
        'form':        form,
        'meta':        meta,
        'es_creacion': False,
        'titulo':      f'Editar Meta — {meta.nombre}',
    })


@login_required
def meta_detalle(request, pk):
    """GET /recomendaciones/metas/<pk>/ — Spec Tarea 2.5: datos de la meta + historial
    de aportes recibidos (mes de origen y monto), más reciente primero."""
    meta = get_object_or_404(MetaLargoPlazo, pk=pk, usuario=request.user)
    aportes = meta.aportes.select_related('registro').order_by('-registro__periodo')
    return render(request, 'recomendaciones/meta_detalle.html', {
        'meta':    meta,
        'aportes': aportes,
    })


@login_required
def meta_delete(request, pk):
    """POST /recomendaciones/metas/<pk>/eliminar/ — Soft delete."""
    meta = get_object_or_404(MetaLargoPlazo, pk=pk, usuario=request.user)
    if request.method == 'POST':
        meta.activa = False
        meta.save(update_fields=['activa'])
        messages.success(request, '🗑️ Meta eliminada.')
        return redirect('recomendaciones:metas')
    return render(request, 'recomendaciones/meta_confirm_delete.html', {'meta': meta})
