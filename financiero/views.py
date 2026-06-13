import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from core.constants import MESES_ES_ABREV
from financiero.forms import RegistroMensualForm
from financiero.models import RegistroMensual


@login_required
def dashboard(request):
    """GET /financiero/ — Dashboard principal con datos reales."""
    registros_qs = list(
        RegistroMensual.objects.filter(usuario=request.user).order_by('-periodo')[:6]
    )
    registros_chart = list(reversed(registros_qs))
    ultimo = registros_qs[0] if registros_qs else None

    # Datos para gráfico de barras (ingresos vs gastos)
    meses_labels   = json.dumps([MESES_ES_ABREV.get(r.periodo.month, '') for r in registros_chart])
    ingresos_data  = json.dumps([float(r.ing_total)   for r in registros_chart])
    gastos_data    = json.dumps([float(r.gasto_total) for r in registros_chart])

    # Distribución de gastos (último registro)
    gastos_cat = ultimo.gastos_por_categoria() if ultimo else {}
    gastos_labels  = json.dumps(list(gastos_cat.keys()))
    gastos_valores = json.dumps(list(gastos_cat.values()))

    # Metas activas y último resultado ML
    from recomendaciones.models import MetaLargoPlazo, ResultadoML
    metas    = MetaLargoPlazo.objects.filter(usuario=request.user, activa=True).order_by('-creado_en')[:3]
    ultimo_ml = ResultadoML.objects.filter(usuario=request.user).order_by('-creado_en').first()

    return render(request, 'financiero/dashboard.html', {
        'ultimo':          ultimo,
        'registros':       registros_qs,
        'metas':           metas,
        'ultimo_ml':       ultimo_ml,
        'meses_labels':    meses_labels,
        'ingresos_data':   ingresos_data,
        'gastos_data':     gastos_data,
        'gastos_labels':   gastos_labels,
        'gastos_valores':  gastos_valores,
        'tiene_datos':     bool(registros_qs),
    })


@login_required
def registro_list(request):
    """GET /financiero/registros/ — Lista de registros mensuales."""
    registros = RegistroMensual.objects.filter(
        usuario=request.user
    ).order_by('-periodo')
    return render(request, 'financiero/registro_list.html', {'registros': registros})


@login_required
def registro_create(request):
    """GET/POST /financiero/registros/nuevo/"""
    if request.method == 'POST':
        form = RegistroMensualForm(request.POST)
        if form.is_valid():
            try:
                registro = form.save(commit=False)
                registro.usuario = request.user
                registro.save()

                # Racha + logros
                from gamificacion.models import Racha
                from gamificacion.services import verificar_y_otorgar_logros
                racha, _ = Racha.objects.get_or_create(usuario=request.user)
                racha.actualizar(date.today())
                verificar_y_otorgar_logros(request.user, contexto='registro')

                messages.success(request, '✅ Registro mensual guardado correctamente.')
                return redirect('financiero:registro_list')
            except IntegrityError:
                messages.error(request, '⚠️ Ya existe un registro para ese período. Edita el existente.')
    else:
        form = RegistroMensualForm()
        form.fields['periodo'].initial = date.today().strftime('%Y-%m')

    return render(request, 'financiero/registro_form.html', {
        'form':        form,
        'es_creacion': True,
        'titulo':      'Nuevo Registro Mensual',
    })


@login_required
def registro_update(request, pk):
    """GET/POST /financiero/registros/<pk>/editar/"""
    registro = get_object_or_404(RegistroMensual, pk=pk, usuario=request.user)

    if request.method == 'POST':
        form = RegistroMensualForm(request.POST, instance=registro)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, '✅ Registro actualizado correctamente.')
                return redirect('financiero:registro_list')
            except IntegrityError:
                messages.error(request, '⚠️ Ya existe otro registro para ese período.')
    else:
        form = RegistroMensualForm(
            instance=registro,
            initial={'periodo': registro.periodo.strftime('%Y-%m')},
        )

    return render(request, 'financiero/registro_form.html', {
        'form':        form,
        'registro':    registro,
        'es_creacion': False,
        'titulo':      f'Editar Registro — {MESES_ES_ABREV.get(registro.periodo.month, "")} {registro.periodo.year}',
    })


@login_required
def registro_delete(request, pk):
    """POST /financiero/registros/<pk>/eliminar/"""
    registro = get_object_or_404(RegistroMensual, pk=pk, usuario=request.user)
    if request.method == 'POST':
        registro.delete()
        messages.success(request, '🗑️ Registro eliminado.')
        return redirect('financiero:registro_list')
    return render(request, 'financiero/registro_confirm_delete.html', {'registro': registro})


@login_required
def analisis(request):
    """GET /financiero/analisis/ — Análisis de gastos con gráficos."""
    n_meses = int(request.GET.get('meses', 6))
    if n_meses not in (6, 12):
        n_meses = 6

    registros = list(
        RegistroMensual.objects.filter(usuario=request.user).order_by('-periodo')[:n_meses]
    )
    registros_chart = list(reversed(registros))

    meses_labels  = json.dumps([MESES_ES_ABREV.get(r.periodo.month, '') for r in registros_chart])
    gastos_data   = json.dumps([float(r.gasto_total)   for r in registros_chart])
    ingresos_data = json.dumps([float(r.ing_total)     for r in registros_chart])
    ahorro_data   = json.dumps([float(r.ahorro_bruto)  for r in registros_chart])

    # Acumulado por categoría (suma de todos los períodos)
    categorias = {
        'Alimentos': 0, 'Vestido': 0, 'Vivienda/Serv.': 0, 'Salud': 0,
        'Transporte': 0, 'Comunicaciones': 0, 'Educación': 0, 'Otros': 0,
    }
    for r in registros:
        for k, v in r.gastos_por_categoria().items():
            categorias[k] = categorias.get(k, 0) + v

    cat_labels = json.dumps(list(categorias.keys()))
    cat_data   = json.dumps(list(categorias.values()))

    return render(request, 'financiero/analisis.html', {
        'n_meses':      n_meses,
        'registros':    registros,
        'meses_labels': meses_labels,
        'gastos_data':  gastos_data,
        'ingresos_data':ingresos_data,
        'ahorro_data':  ahorro_data,
        'cat_labels':   cat_labels,
        'cat_data':     cat_data,
        'tiene_datos':  bool(registros),
    })
