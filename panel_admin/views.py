import json

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from accounts.models import Usuario
from panel_admin.models import AuditLog


@staff_member_required
def user_list(request):
    search = request.GET.get('search', '').strip()
    activo = request.GET.get('activo', '')

    usuarios = Usuario.objects.select_related('rol').order_by('-date_joined')
    if search:
        usuarios = usuarios.filter(
            Q(nickname__icontains=search) | Q(email__icontains=search)
        )
    if activo in ('true', 'false'):
        usuarios = usuarios.filter(is_active=(activo == 'true'))

    return render(request, 'panel_admin/user_list.html', {
        'usuarios': usuarios,
        'search':   search,
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
    logs = AuditLog.objects.select_related(
        'admin', 'usuario_objetivo'
    ).order_by('-fecha')[:200]
    AuditLog.registrar(admin=request.user, accion='VER_ESTADISTICAS', request=request)
    return render(request, 'panel_admin/activity.html', {'logs': logs})


@staff_member_required
def metrics_view(request):
    from financiero.models import RegistroMensual
    from recomendaciones.models import ResultadoML

    total_usuarios  = Usuario.objects.count()
    usuarios_activos = Usuario.objects.filter(is_active=True).count()
    total_registros = RegistroMensual.objects.count()
    total_ml        = ResultadoML.objects.count()

    cluster_dist = (
        ResultadoML.objects
        .values('cluster_label')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    cluster_labels = json.dumps([c['cluster_label'] for c in cluster_dist])
    cluster_data   = json.dumps([c['total']         for c in cluster_dist])

    return render(request, 'panel_admin/metrics.html', {
        'total_usuarios':   total_usuarios,
        'usuarios_activos': usuarios_activos,
        'total_registros':  total_registros,
        'total_ml':         total_ml,
        'cluster_dist':     cluster_dist,
        'cluster_labels':   cluster_labels,
        'cluster_data':     cluster_data,
    })
