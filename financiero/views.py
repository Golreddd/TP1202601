import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from core.constants import MESES_ES_ABREV
from financiero.forms import RegistroMensualForm
from financiero.models import RegistroMensual

# (campo, etiqueta, emoji) — mismo orden/labels que registro_form.html, usado tanto
# por el formulario de creación/edición como por el de "agregar montos extra".
CAMPOS_EXTRA = [
    ('ing_planilla',              'Ingreso en planilla',    '💰'),
    ('ing_informal',              'Ingreso informal',       '💰'),
    ('bonif_monto',               'Bonificación',           '🎁'),
    ('gasto_alimentos',           'Alimentos',              '🍔'),
    ('gasto_vestido',             'Vestido',                '👗'),
    ('gasto_vivienda_servicios',  'Vivienda y servicios',   '🏠'),
    ('gasto_salud',               'Salud',                  '💊'),
    ('gasto_transporte',          'Transporte',             '🚌'),
    ('gasto_comunicaciones',      'Comunicaciones',         '📱'),
    ('gasto_educacion',           'Educación',              '🎓'),
    ('gasto_otros_bienes',        'Otros bienes',           '🛒'),
]


def _avisar_si_tiene_aportes(request, registro):
    """Spec Tarea 2.4: aviso NO bloqueante si el registro ya repartió ahorro hacia
    metas — no se recalcula/edita nada automáticamente, solo se informa con links para
    que el usuario ajuste a mano si el ahorro del mes cambió. Se usa tanto al editar el
    registro como al agregarle montos extra (ambos cambian sus totales por igual)."""
    aportes = registro.aportes_meta.select_related('meta')
    metas_con_aporte = {a.meta for a in aportes}
    if not metas_con_aporte:
        return
    total_aportado = sum(a.monto for a in aportes)
    links = format_html_join(
        ', ', '<a href="{}" style="color:inherit;font-weight:700;text-decoration:underline;">{}</a>',
        ((reverse('recomendaciones:meta_update', args=[m.pk]), m.nombre) for m in metas_con_aporte),
    )
    messages.warning(request, format_html(
        'Este registro ya tenía S/ {} asignados a: {}. Si tu ahorro de este mes '
        'cambió, revisa y ajusta esos montos manualmente.',
        f'{total_aportado:.0f}', links,
    ))


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
    """GET /financiero/registros/ — Lista de registros mensuales (paginada)."""
    registros_qs = RegistroMensual.objects.filter(
        usuario=request.user
    ).order_by('-periodo')
    paginator = Paginator(registros_qs, 8)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'financiero/registro_list.html', {
        'page_obj':        page_obj,
        'total_registros': paginator.count,
    })


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

                # Spec Tarea 2.2: si el mes cerró en positivo y hay metas activas,
                # ofrecer repartir ese ahorro entre ellas antes de ir a la lista.
                from recomendaciones.models import MetaLargoPlazo
                if registro.ahorro_bruto > 0 and MetaLargoPlazo.objects.filter(
                    usuario=request.user, activa=True
                ).exists():
                    return redirect('financiero:distribuir_ahorro', registro_id=registro.id)
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
                _avisar_si_tiene_aportes(request, registro)
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
        # Spec Tarea 2.3: revertir (descontar) lo aportado desde este registro en cada
        # meta afectada ANTES de borrar — mismo patrón defensivo max(0, ...) que ya usan
        # `faltante`/`disponible` en el modelo. Los AporteMeta se borran solos por el
        # on_delete=CASCADE del FK a registro.
        aportes = list(registro.aportes_meta.select_related('meta'))
        if aportes:
            total_revertido = sum(a.monto for a in aportes)
            for aporte in aportes:
                meta = aporte.meta
                meta.monto_actual = max(Decimal('0'), meta.monto_actual - aporte.monto)
                meta.save(update_fields=['monto_actual'])
            messages.info(
                request,
                f'ℹ️ Se revirtieron S/ {total_revertido:.0f} aportados a tus metas desde este registro.',
            )
        registro.delete()
        messages.success(request, '🗑️ Registro eliminado.')
        return redirect('financiero:registro_list')
    return render(request, 'financiero/registro_confirm_delete.html', {'registro': registro})


@login_required
def registro_agregar(request, pk):
    """GET/POST /financiero/registros/<pk>/agregar/ — Suma montos EXTRA (ingresos o
    gastos) a un registro ya existente, sin reemplazar sus totales actuales. Cambia los
    totales del mes igual que una edición, así que si el registro ya tiene aportes
    repartidos a metas se avisa igual que en registro_update (mismo helper)."""
    registro = get_object_or_404(RegistroMensual, pk=pk, usuario=request.user)

    if request.method == 'POST':
        deltas, error = {}, None
        for campo, _, _ in CAMPOS_EXTRA:
            crudo = request.POST.get(campo, '').strip()
            if not crudo:
                continue
            try:
                monto = Decimal(crudo)
            except InvalidOperation:
                error = 'Ingresa montos numéricos válidos.'
                break
            if monto < 0:
                error = 'Los montos extra no pueden ser negativos (usa "Editar" para corregir un valor).'
                break
            if monto > 0:
                deltas[campo] = monto

        if error:
            messages.error(request, f'⚠️ {error}')
        elif not deltas:
            messages.info(request, 'No se agregó ningún monto extra.')
            return redirect('financiero:registro_list')
        else:
            for campo, monto in deltas.items():
                setattr(registro, campo, getattr(registro, campo) + monto)
            registro.save()
            _avisar_si_tiene_aportes(request, registro)
            messages.success(request, '✅ Montos extra agregados al registro correctamente.')
            return redirect('financiero:registro_list')

    return render(request, 'financiero/registro_agregar.html', {
        'registro':         registro,
        'campos_ingreso':   [c for c in CAMPOS_EXTRA if not c[0].startswith('gasto_')],
        'campos_gasto':     [c for c in CAMPOS_EXTRA if c[0].startswith('gasto_')],
    })


@login_required
def distribuir_ahorro(request, registro_id):
    """GET/POST /financiero/registros/<registro_id>/distribuir/ — Spec Tarea 2.2:
    pantalla intermedia (opcional) tras crear un registro con ahorro positivo, para
    repartirlo entre las metas activas del usuario. Si no hay metas activas o el
    ahorro no es positivo, no tiene sentido llegar aquí — se manda a la lista."""
    registro = get_object_or_404(RegistroMensual, pk=registro_id, usuario=request.user)

    from recomendaciones.models import AporteMeta, MetaLargoPlazo
    metas_activas = list(
        MetaLargoPlazo.objects.filter(usuario=request.user, activa=True).order_by('-creado_en')
    )
    ahorro_bruto = registro.ahorro_bruto

    if ahorro_bruto <= 0 or not metas_activas:
        return redirect('financiero:registro_list')

    if request.method == 'POST':
        if 'omitir' in request.POST:
            return redirect('financiero:registro_list')

        aportes, total, error = {}, 0.0, None
        for meta in metas_activas:
            crudo = request.POST.get(f'monto_{meta.id}', '').strip()
            if not crudo:
                continue
            try:
                monto = float(crudo)
            except ValueError:
                error = 'Ingresa montos numéricos válidos.'
                break
            if monto < 0:
                error = 'Los montos no pueden ser negativos.'
                break
            if monto > 0:
                aportes[meta] = monto
                total += monto

        if error is None and total > ahorro_bruto + 0.01:
            error = (
                f'La suma de los aportes (S/ {total:.2f}) supera el ahorro '
                f'disponible este mes (S/ {ahorro_bruto:.2f}).'
            )

        if error:
            messages.error(request, f'⚠️ {error}')
        else:
            if aportes:
                for meta, monto in aportes.items():
                    AporteMeta.objects.create(usuario=request.user, meta=meta, registro=registro, monto=monto)
                    meta.monto_actual = meta.monto_actual + Decimal(str(monto))
                    meta.save(update_fields=['monto_actual'])
                from gamificacion.services import verificar_y_otorgar_logros
                verificar_y_otorgar_logros(request.user, contexto='meta_completada')
                messages.success(request, '✅ Ahorro distribuido entre tus metas correctamente.')
            return redirect('financiero:registro_list')

    return render(request, 'financiero/distribuir_ahorro.html', {
        'registro':      registro,
        'metas_activas': metas_activas,
        'ahorro_bruto':  ahorro_bruto,
    })


MESES_PERMITIDOS = (6, 12)


@login_required
def analisis(request):
    """GET /financiero/analisis/ — Análisis de gastos con gráficos."""
    # El rango llega por querystring y es manipulable por el usuario: se valida en
    # lugar de convertirlo a int a ciegas (antes, `?meses=abc` lanzaba ValueError y
    # devolvía un error 500). Si es inválido se avisa y se cae al rango por defecto.
    meses_raw = request.GET.get('meses')
    n_meses = MESES_PERMITIDOS[0]
    if meses_raw is not None:
        try:
            solicitado = int(meses_raw)
        except (TypeError, ValueError):
            solicitado = None
        if solicitado in MESES_PERMITIDOS:
            n_meses = solicitado
        else:
            messages.error(
                request,
                f'El rango "{meses_raw}" no es válido. Elige 6 o 12 meses; '
                f'mostrando los últimos {n_meses} meses.',
            )

    base_qs = RegistroMensual.objects.filter(usuario=request.user).order_by('-periodo')

    # Ventana de los últimos n_meses para los GRÁFICOS y el acumulado por categoría.
    registros_ventana = list(base_qs[:n_meses])
    registros_chart = list(reversed(registros_ventana))

    meses_labels  = json.dumps([MESES_ES_ABREV.get(r.periodo.month, '') for r in registros_chart])
    gastos_data   = json.dumps([float(r.gasto_total)   for r in registros_chart])
    ingresos_data = json.dumps([float(r.ing_total)     for r in registros_chart])
    ahorro_data   = json.dumps([float(r.ahorro_bruto)  for r in registros_chart])

    # Acumulado por categoría (suma de los meses de la ventana)
    categorias = {
        'Alimentos': 0, 'Vestido': 0, 'Vivienda/Serv.': 0, 'Salud': 0,
        'Transporte': 0, 'Comunicaciones': 0, 'Educación': 0, 'Otros': 0,
    }
    for r in registros_ventana:
        for k, v in r.gastos_por_categoria().items():
            categorias[k] = categorias.get(k, 0) + v

    cat_labels = json.dumps(list(categorias.keys()))
    cat_data   = json.dumps(list(categorias.values()))

    # Serie mensual POR CATEGORÍA (no solo el acumulado de arriba): permite que el
    # selector de "Tendencia Mensual de Gastos" muestre, mes a mes, cómo evolucionó
    # una categoría puntual en vez de (o además de) el gasto total.
    gastos_categoria_series = json.dumps({
        nombre: [float(r.gastos_por_categoria().get(nombre, 0.0)) for r in registros_chart]
        for nombre in categorias
    })

    # Distribución PORCENTUAL por categoría: el gráfico de dona muestra la proporción
    # de forma visual, pero el porcentaje numérico se calcula aquí para mostrarlo
    # explícitamente (una dona no permite leer "Alimentos = 34,2%" con precisión).
    total_cat = sum(categorias.values())
    distribucion = [
        {
            'categoria': nombre,
            'monto': round(monto, 2),
            'pct': round(monto / total_cat * 100, 1) if total_cat > 0 else 0.0,
        }
        for nombre, monto in categorias.items() if monto > 0
    ]
    distribucion.sort(key=lambda c: c['pct'], reverse=True)

    # Categoría con mayor crecimiento del historial (capa multi-mes ya existente).
    # Permite reportar tanto el caso crítico como el equilibrado (sin crecimiento).
    from recomendaciones.trends import analizar_tendencia
    tendencia = analizar_tendencia(request.user)

    # Tabla "Detalle por Período": TODOS los períodos, paginados (8 por página).
    paginator = Paginator(base_qs, 8)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'financiero/analisis.html', {
        'n_meses':                 n_meses,
        'page_obj':                page_obj,
        'total_registros':         paginator.count,
        'meses_labels':            meses_labels,
        'gastos_data':             gastos_data,
        'ingresos_data':           ingresos_data,
        'ahorro_data':             ahorro_data,
        'cat_labels':              cat_labels,
        'cat_labels_list':         list(categorias.keys()),
        'cat_data':                cat_data,
        'gastos_categoria_series': gastos_categoria_series,
        'distribucion':            distribucion,
        'tendencia':               tendencia,
        'total_gastado':           round(total_cat, 2),
        'tiene_datos':             base_qs.exists(),
    })
