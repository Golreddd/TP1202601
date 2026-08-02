import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.forms import CambiarPasswordWebForm, PerfilForm, PerfilMLForm, RegistroForm
from accounts.models import Rol, Usuario

logger = logging.getLogger(__name__)


def _auditar_acceso_admin(usuario, accion, request):
    """Registra en AuditLog el acceso/salida de una cuenta ADMINISTRATIVA.

    Las acciones LOGIN_ADMIN / LOGOUT_ADMIN estaban declaradas en AuditLog.ACCIONES
    pero ningún punto del código las creaba, así que la traza de auditoría del panel
    quedaba incompleta. Solo se auditan cuentas admin: el login de un usuario común
    no es una acción administrativa. Nunca debe romper el flujo de autenticación, por
    eso cualquier fallo se registra en el log de la app y se sigue adelante.
    """
    try:
        if not usuario or not usuario.es_admin:
            return
        from panel_admin.models import AuditLog
        AuditLog.registrar(admin=usuario, accion=accion, request=request)
    except Exception:
        logger.exception('No se pudo auditar %s de %s', accion, getattr(usuario, 'email', '?'))


def login_view(request):
    """GET/POST /auth/login/"""
    if request.user.is_authenticated:
        return redirect('financiero:dashboard')

    if request.method == 'POST':
        email_raw = request.POST.get('username', '').strip().lower()
        password  = request.POST.get('password', '')
        next_url  = request.GET.get('next') or 'financiero:dashboard'

        # USERNAME_FIELD = 'email' → el backend espera email=, no username=
        user = authenticate(request, email=email_raw, password=password)
        if user is not None:
            login(request, user)
            _auditar_acceso_admin(user, 'LOGIN_ADMIN', request)
            return redirect(next_url)
        messages.error(request, 'Correo o contraseña incorrectos.')

    return render(request, 'accounts/login.html')


def register_view(request):
    """GET/POST /auth/register/"""
    if request.user.is_authenticated:
        return redirect('financiero:dashboard')

    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            try:
                rol_usuario = Rol.objects.get(nombre=Rol.USUARIO)
            except Rol.DoesNotExist:
                rol_usuario = None

            nivel = form.cleaned_data.get('nivel_educ')
            user = Usuario.objects.create_user(
                email=form.cleaned_data['email'],
                nickname=form.cleaned_data['nickname'],
                username=form.cleaned_data['nickname'],
                password=form.cleaned_data['password'],
                edad=form.cleaned_data.get('edad'),
                nivel_educ=int(nivel) if nivel else None,
                rol=rol_usuario,
            )
            # No iniciar sesión automáticamente: derivar al login.
            messages.success(
                request,
                f'¡Cuenta creada, {user.nickname}! Inicia sesión para continuar.',
            )
            return redirect('accounts:login')
    else:
        form = RegistroForm()

    return render(request, 'accounts/register.html', {'form': form})


@require_POST
def logout_view(request):
    """POST /auth/logout/"""
    # Se audita ANTES de cerrar la sesión: después, request.user ya es anónimo.
    _auditar_acceso_admin(request.user if request.user.is_authenticated else None,
                          'LOGOUT_ADMIN', request)
    logout(request)
    messages.success(request, 'Sesión cerrada correctamente.')
    return redirect('accounts:login')


@login_required
def profile_view(request):
    """GET/POST /auth/perfil/"""
    perfil_form    = PerfilForm(instance=request.user)
    perfil_ml_form = PerfilMLForm(instance=request.user)
    pw_form        = CambiarPasswordWebForm(request.user)

    if request.method == 'POST':
        form_type = request.POST.get('form_type', '')

        if form_type == 'perfil':
            perfil_form = PerfilForm(request.POST, instance=request.user)
            if perfil_form.is_valid():
                perfil_form.save()
                from gamificacion.services import verificar_y_otorgar_logros
                verificar_y_otorgar_logros(request.user, contexto='perfil')
                messages.success(request, 'Información personal actualizada.')
                return redirect('accounts:profile')

        elif form_type == 'perfil_ml':
            perfil_ml_form = PerfilMLForm(request.POST, instance=request.user)
            if perfil_ml_form.is_valid():
                perfil_ml_form.save()
                from gamificacion.services import verificar_y_otorgar_logros
                verificar_y_otorgar_logros(request.user, contexto='perfil')
                messages.success(request, 'Perfil ML actualizado correctamente.')
                return redirect('accounts:profile')

        elif form_type == 'password':
            pw_form = CambiarPasswordWebForm(request.user, request.POST)
            if pw_form.is_valid():
                pw_form.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Contraseña actualizada correctamente.')
                return redirect('accounts:profile')

    return render(request, 'accounts/profile.html', {
        'perfil_form':    perfil_form,
        'perfil_ml_form': perfil_ml_form,
        'pw_form':        pw_form,
    })
