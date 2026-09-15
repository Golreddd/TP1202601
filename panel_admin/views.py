import csv
import json
import logging
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from panel_admin.models import AuditLog, ValidacionPrimerUso

logger = logging.getLogger(__name__)


@staff_member_required
def user_list(request):
    search = request.GET.get('search', '').strip()
    activo = request.GET.get('activo', '')

    usuarios_qs = Usuario.objects.select_related('rol').order_by('-date_joined')
    if search:
        usuarios_qs = usuarios_qs.filter(
            Q(nickname__icontains=search) | Q(email__icontains=search)
        )
    if activo in ('true', 'false'):
        usuarios_qs = usuarios_qs.filter(is_active=(activo == 'true'))

    paginator = Paginator(usuarios_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Querystring de filtros (sin 'page') para preservarlos en la paginación.
    filtros = request.GET.copy()
    filtros.pop('page', None)

    return render(request, 'panel_admin/user_list.html', {
        'page_obj':     page_obj,
        'total_users':  paginator.count,
        'search':       search,
        'querystring':  filtros.urlencode(),
    })


@staff_member_required
def user_detail(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    AuditLog.registrar(
        admin=request.user,
        accion='VER_USUARIO',
        usuario_objetivo=usuario,
        request=request,
    )
    return render(request, 'panel_admin/user_detail.html', {'usuario': usuario})


@staff_member_required
def user_toggle_active(request, pk):
    """POST /panel-admin/usuarios/<pk>/estado/ — activa o desactiva una cuenta.

    Siempre redirige al detalle con un mensaje explicando el resultado: antes, los
    casos que no cumplían la condición (GET, o el admin sobre su propia cuenta)
    caían a un render mudo y el administrador no recibía ninguna explicación.
    """
    usuario = get_object_or_404(Usuario, pk=pk)
    destino = redirect(reverse('panel_admin:user_detail', args=[pk]))

    if request.method != 'POST':
        return destino

    # Un admin no puede desactivarse a sí mismo (se dejaría fuera del panel).
    if usuario == request.user:
        messages.error(request, 'No puedes cambiar el estado de tu propia cuenta.')
        return destino

    nuevo_estado = not usuario.is_active
    accion = 'ACTIVAR_USUARIO' if nuevo_estado else 'DESACTIVAR_USUARIO'
    try:
        # El cambio de estado y su registro de auditoría van juntos: si falla el
        # log, se revierte el estado para no dejar un cambio sin trazabilidad.
        with transaction.atomic():
            usuario.is_active = nuevo_estado
            usuario.save(update_fields=['is_active'])
            AuditLog.registrar(
                admin=request.user, accion=accion,
                usuario_objetivo=usuario, request=request,
            )
    except DatabaseError:
        logger.exception('Error al cambiar el estado del usuario #%s', pk)
        messages.error(
            request,
            f'No se pudo actualizar el estado de {usuario.nickname}. '
            'Inténtalo nuevamente o contacta al soporte técnico.',
        )
        return destino

    estado = 'activado' if nuevo_estado else 'desactivado'
    messages.success(request, f'Usuario {usuario.nickname} {estado} correctamente.')
    return destino


@staff_member_required
def activity_log(request):
    logs_qs = AuditLog.objects.select_related(
        'admin', 'usuario_objetivo'
    ).order_by('-fecha')
    AuditLog.registrar(admin=request.user, accion='VER_ESTADISTICAS', request=request)

    paginator = Paginator(logs_qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'panel_admin/activity.html', {
        'page_obj':  page_obj,
        'total_logs': paginator.count,
    })


@staff_member_required
def metrics_view(request):
    from financiero.models import RegistroMensual
    from recomendaciones.models import ResultadoML

    total_usuarios  = Usuario.objects.count()
    usuarios_activos = Usuario.objects.filter(is_active=True).count()
    total_registros = RegistroMensual.objects.count()
    total_ml        = ResultadoML.objects.count()

    clase_dist = (
        ResultadoML.objects
        .values('label_predicha')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    clase_labels = json.dumps([c['label_predicha'] or '—' for c in clase_dist])
    clase_data   = json.dumps([c['total']                 for c in clase_dist])

    return render(request, 'panel_admin/metrics.html', {
        'total_usuarios':   total_usuarios,
        'usuarios_activos': usuarios_activos,
        'total_registros':  total_registros,
        'total_ml':         total_ml,
        'clase_dist':       clase_dist,
        'clase_labels':     clase_labels,
        'clase_data':       clase_data,
        'validacion':       _resumen_validacion(ValidacionPrimerUso.objects.all()),
    })


# ── Validación ML con usuarios reales (primer uso = conjunto de prueba) ─────────

def _pct(valor):
    return None if valor is None else round(valor * 100, 1)


def _resumen_validacion(qs) -> dict:
    """Matriz de confusión y métricas (clase positiva = Ahorra) sobre `qs`."""
    c = qs.aggregate(
        n=Count('id'),
        tp=Count('id', filter=Q(tipo='TP')), fp=Count('id', filter=Q(tipo='FP')),
        tn=Count('id', filter=Q(tipo='TN')), fn=Count('id', filter=Q(tipo='FN')),
    )
    n, tp, fp, tn, fn = c['n'], c['tp'], c['fp'], c['tn'], c['fn']
    accuracy  = (tp + tn) / n if n else None
    precision = tp / (tp + fp) if (tp + fp) else None
    recall    = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None and (precision + recall) else None)
    return {
        'n': n, 'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn,
        'aciertos': tp + tn, 'errores': fp + fn,
        'accuracy': _pct(accuracy), 'precision': _pct(precision),
        'recall': _pct(recall), 'f1': _pct(f1),
    }


def _metricas_publicadas() -> dict | None:
    ruta = Path(settings.BASE_DIR) / 'models' / 'metrics.json'
    if not ruta.exists():
        return None
    with open(ruta, encoding='utf-8') as f:
        return json.load(f)


@staff_member_required
def validacion_ml(request):
    tipo   = request.GET.get('tipo', '').upper()
    search = request.GET.get('search', '').strip()

    casos_qs = ValidacionPrimerUso.objects.select_related('usuario').order_by('-creado_en')
    if tipo in dict(ValidacionPrimerUso.TIPOS):
        casos_qs = casos_qs.filter(tipo=tipo)
    if search:
        casos_qs = casos_qs.filter(
            Q(usuario__nickname__icontains=search) | Q(usuario__email__icontains=search)
        )

    paginator = Paginator(casos_qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))
    filtros   = request.GET.copy()
    filtros.pop('page', None)

    resumen   = _resumen_validacion(ValidacionPrimerUso.objects.all())
    publicado = _metricas_publicadas() or {}
    valid, cv = publicado.get('valid', {}), publicado.get('cv_5fold', {})
    comparativa = [
        {'metrica': etiqueta, 'real': resumen[clave],
         'valid': _pct(valid.get(clave)), 'cv': _pct(cv.get(clave))}
        for clave, etiqueta in (('accuracy', 'Accuracy'), ('precision', 'Precision'),
                                ('recall', 'Recall'), ('f1', 'F1'))
    ]

    return render(request, 'panel_admin/validacion_ml.html', {
        'page_obj':     page_obj,
        'total_casos':  paginator.count,
        'tipo':         tipo,
        'search':       search,
        'querystring':  filtros.urlencode(),
        'tipos':        ValidacionPrimerUso.TIPOS,
        'resumen':      resumen,
        'comparativa':  comparativa,
        'n_valid':      publicado.get('n_valid'),
        'n_train':      publicado.get('n_train'),
        'conf_labels':  json.dumps(['Verdadero positivo', 'Verdadero negativo',
                                    'Falso positivo', 'Falso negativo']),
        'conf_data':    json.dumps([resumen['tp'], resumen['tn'], resumen['fp'], resumen['fn']]),
    })


@staff_member_required
def validacion_ml_export(request):
    casos = ValidacionPrimerUso.objects.select_related('usuario').order_by('creado_en')
    AuditLog.registrar(
        admin=request.user, accion='EXPORTAR_DATOS', request=request,
        detalle=f'Exportación de validación ML (primer uso): {casos.count()} casos',
    )
    fecha = timezone.localdate().strftime('%Y%m%d')
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="validacion_ml_{fecha}.csv"'
    response.write('﻿')   # BOM: Excel abre el UTF-8 con tildes correctas
    w = csv.writer(response, delimiter=';')
    w.writerow(['ID', 'Usuario', 'Correo', 'Período', 'Ingreso total', 'Gasto total',
                'Ahorro real', 'Clase real', 'Clase predicha', 'Prob. ahorra',
                'Confianza', 'Resultado', 'Acierto', 'Fecha captura'])
    for c in casos:
        w.writerow([
            c.id, c.usuario.nickname, c.usuario.email, c.periodo.strftime('%Y-%m'),
            f'{c.ing_total:.2f}', f'{c.gasto_total:.2f}', f'{c.ahorro_real:.2f}',
            c.label_real, c.label_predicha, f'{c.prob_ahorra:.4f}', c.confianza,
            c.tipo, 'Sí' if c.acierto else 'No',
            timezone.localtime(c.creado_en).strftime('%d/%m/%Y %H:%M'),
        ])
    return response


# ── Evolución de la tasa de ahorro por usuario ─────────────────────────────────

def _evolucion_ahorro(usuarios):
    """Tasa de ahorro (ahorro ÷ ingreso total) de cada usuario mes a mes.

    Por cada usuario devuelve la tasa de su PRIMER registro —la línea base, antes de
    que el sistema influyera en su comportamiento— y la de cada mes posterior en orden
    cronológico. Se calcula en vivo desde RegistroMensual en lugar de guardar una
    copia, para que la tabla siga siendo correcta si el usuario corrige un mes.

    Devuelve (filas, max_meses_posteriores) — `max_meses` define cuántas columnas
    P1..Pn necesita la tabla para que todas las filas queden alineadas.
    """
    from financiero.models import RegistroMensual

    def _tasa(registro):
        # Se calcula aqui con 2 decimales en vez de usar la propiedad `tasa_ahorro`
        # del modelo, que redondea a 1 decimal: en una tabla de validacion esa
        # decima extra distingue mejoras pequenas entre un mes y otro.
        ingreso = registro.ing_total
        if ingreso <= 0:
            return 0.0
        return round(registro.ahorro_bruto / ingreso * 100, 2)

    por_usuario = {}
    for r in (RegistroMensual.objects
              .filter(usuario__in=usuarios)
              .order_by('usuario_id', 'periodo')):
        por_usuario.setdefault(r.usuario_id, []).append(r)

    filas, max_meses = [], 0
    for usuario in usuarios:
        regs = por_usuario.get(usuario.id, [])
        tasas = [_tasa(r) for r in regs]
        posteriores = tasas[1:]
        max_meses = max(max_meses, len(posteriores))
        filas.append({
            'usuario':      usuario,
            'base':         tasas[0] if tasas else None,
            'periodo_base': regs[0].periodo if regs else None,
            'posteriores':  posteriores,
            'ultima':       tasas[-1] if tasas else None,
            # Mejora en PUNTOS porcentuales entre el primer mes y el último: es la
            # cifra que responde si el usuario ahorra más desde que usa el sistema.
            'variacion':    round(tasas[-1] - tasas[0], 2) if len(tasas) >= 2 else None,
            'n_meses':      len(tasas),
        })

    # Se rellenan con None las filas más cortas para que todas tengan max_meses celdas
    for fila in filas:
        fila['posteriores'] += [None] * (max_meses - len(fila['posteriores']))
    return filas, max_meses


def _resumen_evolucion(filas):
    """Promedios sobre los usuarios que ya tienen al menos un registro."""
    con_datos = [f for f in filas if f['base'] is not None]
    con_variacion = [f for f in con_datos if f['variacion'] is not None]

    def _prom(valores):
        return round(sum(valores) / len(valores), 2) if valores else None

    return {
        'n_usuarios':   len(filas),
        'n_con_datos':  len(con_datos),
        'n_con_var':    len(con_variacion),
        'base_prom':    _prom([f['base'] for f in con_datos]),
        'ultima_prom':  _prom([f['ultima'] for f in con_datos]),
        'variacion':    _prom([f['variacion'] for f in con_variacion]),
        'mejoraron':    sum(1 for f in con_variacion if f['variacion'] > 0),
        'empeoraron':   sum(1 for f in con_variacion if f['variacion'] < 0),
    }


def _usuarios_evolucion(request):
    """Usuarios de la tabla, aplicando la búsqueda y el filtro de la pantalla."""
    usuarios = Usuario.objects.order_by('date_joined')
    search = request.GET.get('search', '').strip()
    if search:
        usuarios = usuarios.filter(
            Q(nickname__icontains=search) | Q(email__icontains=search)
        )
    # Por defecto solo se listan los usuarios que ya registraron algún mes: los demás
    # no aportan nada a la tabla. Con ?todos=1 se muestran todos.
    if request.GET.get('todos') != '1':
        usuarios = usuarios.filter(registros__isnull=False).distinct()
    return list(usuarios), search


@staff_member_required
def evolucion_ahorro(request):
    usuarios, search = _usuarios_evolucion(request)
    filas, max_meses = _evolucion_ahorro(usuarios)
    return render(request, 'panel_admin/evolucion_ahorro.html', {
        'filas':       filas,
        'columnas':    range(1, max_meses + 1),
        'max_meses':   max_meses,
        'resumen':     _resumen_evolucion(filas),
        'search':      search,
        'todos':       request.GET.get('todos') == '1',
    })


@staff_member_required
def evolucion_ahorro_export(request):
    usuarios, _search = _usuarios_evolucion(request)
    filas, max_meses = _evolucion_ahorro(usuarios)

    AuditLog.registrar(
        admin=request.user, accion='EXPORTAR_DATOS', request=request,
        detalle=f'Exportación de evolución de ahorro: {len(filas)} usuarios',
    )

    fecha = timezone.localdate().strftime('%Y%m%d')
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="evolucion_ahorro_{fecha}.csv"'
    response.write('\ufeff')   # BOM: Excel abre el UTF-8 con tildes correctas
    w = csv.writer(response, delimiter=';')
    w.writerow(['N°', 'NOMBRE', 'CORREO', 'PORCENTAJE ACTUAL']
               + [f'P{i}' for i in range(1, max_meses + 1)]
               + ['VARIACIÓN (puntos)', 'MESES REGISTRADOS', 'MES INICIAL'])

    def _pc(valor):
        # Coma decimal: es lo que espera Excel en configuración regional es-PE
        return '' if valor is None else f'{valor:.2f}'.replace('.', ',')

    for i, fila in enumerate(filas, start=1):
        w.writerow([
            i, fila['usuario'].nickname, fila['usuario'].email, _pc(fila['base']),
            *[_pc(v) for v in fila['posteriores']],
            _pc(fila['variacion']), fila['n_meses'],
            fila['periodo_base'].strftime('%Y-%m') if fila['periodo_base'] else '',
        ])
    return response
