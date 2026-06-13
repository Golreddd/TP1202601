import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from core.constants import MESES_ES
from financiero.models import RegistroMensual
from recomendaciones.forms import MetaLargoPlazoForm
from recomendaciones.models import MetaLargoPlazo, PlanSeleccionado, ResultadoML


@login_required
def ml_insights(request):
    """GET /recomendaciones/ — Página ML Insights con último resultado."""
    resultados = ResultadoML.objects.filter(
        usuario=request.user
    ).select_related('registro').order_by('-creado_en')[:10]

    ultimo = resultados.first()
    detalle = None
    planes_convergen = False
    meta_inalcanzable = False
    ml_js = None  # JSON string for safe JS injection (avoids locale float issues)

    if ultimo:
        try:
            detalle = ultimo.recomputar()
        except Exception:
            detalle = None

        if detalle and detalle.get('planes'):
            planes = detalle['planes']
            if len(planes) >= 2:
                primer_ahorro = planes[0].get('ahorro_predicho', 0)
                planes_convergen = all(
                    abs(p.get('ahorro_predicho', 0) - primer_ahorro) < 1.0
                    for p in planes[1:]
                    if p['nombre'].lower() != 'meta ya alcanzada'
                )
            if planes_convergen and planes:
                max_ahorro = planes[0].get('ahorro_predicho', 0)
                meta_inalcanzable = ultimo.meta_validada > max_ahorro

        if detalle and ultimo.registro:
            try:
                ml_js = json.dumps({
                    'ahorro':     round(float(ultimo.ahorro_actual), 2),
                    'meta':       round(float(ultimo.meta_validada), 2),
                    'ingTotal':   round(float(ultimo.registro.ing_total), 2),
                    'gastoTotal': round(float(ultimo.registro.gasto_total), 2),
                    'planes':     detalle.get('planes', []),
                    'shap':       detalle.get('explicacion_shap', []),
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

    return render(request, 'recomendaciones/ml_insights.html', {
        'ultimo':            ultimo,
        'detalle':           detalle,
        'resultados':        resultados,
        'planes_convergen':  planes_convergen,
        'meta_inalcanzable': meta_inalcanzable,
        'ml_js':             ml_js,
        'plan_activo_nombre': plan_activo.nombre_plan if plan_activo else '',
        'tiene_registros':   registros_qs.exists(),
        'registros_js':      registros_js,
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

    if detalle and detalle.get('planes'):
        planes = detalle['planes']
        if len(planes) >= 2:
            primer_ahorro = planes[0].get('ahorro_predicho', 0)
            planes_convergen = all(
                abs(p.get('ahorro_predicho', 0) - primer_ahorro) < 1.0
                for p in planes[1:]
                if p['nombre'].lower() != 'meta ya alcanzada'
            )

    if detalle and resultado.registro:
        try:
            ml_js = json.dumps({
                'ahorro':     round(float(resultado.ahorro_actual), 2),
                'meta':       round(float(resultado.meta_validada), 2),
                'ingTotal':   round(float(resultado.registro.ing_total), 2),
                'gastoTotal': round(float(resultado.registro.gasto_total), 2),
                'planes':     detalle.get('planes', []),
                'shap':       detalle.get('explicacion_shap', []),
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
