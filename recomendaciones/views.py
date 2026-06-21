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
    registros_qs = RegistroMensual.objects.filter(
        usuario=request.user
    ).order_by('-periodo')
    registros_js = json.dumps([
        {
            'id':          r.id,
            'mes':         MESES_ES.get(r.periodo.month, ''),
            'anio':        r.periodo.year,
            'ingTotal':    round(r.ing_total, 2),
            'gastoTotal':  round(r.gasto_total, 2),
            'ingPlanilla': round(float(r.ing_planilla), 2),
            'ingInformal': round(float(r.ing_informal), 2),
            'bonif':       round(float(r.bonif_monto), 2),
            'ahorroBruto': round(r.ahorro_bruto, 2),
            'gastos':      r.gastos_por_categoria(),
        }
        for r in registros_qs
    ], ensure_ascii=False)

    # Mes de referencia del último análisis: se pre-selecciona en el formulario
    # para que, tras ejecutar, el selector recuerde el mes elegido (no resetee).
    ultima_ref_id = None
    if ultimo:
        ultima_ref_id = ultimo.mes_referencia_id or ultimo.registro_id

    # Paginación del historial (8 por página) para que no crezca indefinidamente.
    paginator = Paginator(historial_qs, 8)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'recomendaciones/ml_insights.html', {
        'ultimo':            ultimo,
        'detalle':           detalle,
        'page_obj':          page_obj,
        'total_analisis':    paginator.count,
        'planes_convergen':  planes_convergen,
        'meta_inalcanzable': meta_inalcanzable,
        'ml_js':             ml_js,
        'plan_activo_nombre': plan_activo.nombre_plan if plan_activo else '',
        'tiene_registros':   registros_qs.exists(),
        'registros_js':      registros_js,
        'ultima_ref_id':     ultima_ref_id,
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
        form = MetaLargoPlazoForm(instance=meta)

    return render(request, 'recomendaciones/meta_form.html', {
        'form':        form,
        'meta':        meta,
        'es_creacion': False,
        'titulo':      f'Editar Meta — {meta.nombre}',
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
