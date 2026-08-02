import json
import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.models import Usuario
from panel_admin.models import AuditLog

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
    })
