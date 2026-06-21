import json

from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from accounts.models import Usuario
from panel_admin.models import AuditLog


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
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.urls import reverse
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == 'POST' and usuario != request.user:
        usuario.is_active = not usuario.is_active
        usuario.save(update_fields=['is_active'])
        accion = 'ACTIVAR_USUARIO' if usuario.is_active else 'DESACTIVAR_USUARIO'
        AuditLog.registrar(admin=request.user, accion=accion, usuario_objetivo=usuario, request=request)
        estado = 'activado' if usuario.is_active else 'desactivado'
        messages.success(request, f'Usuario {usuario.nickname} {estado} correctamente.')
        return redirect(reverse('panel_admin:user_detail', args=[pk]))
    return render(request, 'panel_admin/user_detail.html', {'usuario': usuario})


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
