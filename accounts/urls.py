from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from accounts import views

app_name = 'accounts'

urlpatterns = [
    path('login/',    views.login_view,    name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/',   views.logout_view,   name='logout'),
    path('perfil/',   views.profile_view,  name='profile'),

    # ── Restablecimiento de contraseña (RF003, HU09, HU10) ──────────────────
    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             template_name='accounts/password_reset_form.html',
             email_template_name='accounts/password_reset_email.html',
             subject_template_name='accounts/password_reset_subject.txt',
             success_url=reverse_lazy('accounts:password_reset_done'),
         ), name='password_reset'),
    path('password-reset/enviado/',
         auth_views.PasswordResetDoneView.as_view(
             template_name='accounts/password_reset_done.html',
         ), name='password_reset_done'),
    path('password-reset/confirmar/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='accounts/password_reset_confirm.html',
             success_url=reverse_lazy('accounts:password_reset_complete'),
         ), name='password_reset_confirm'),
    path('password-reset/completado/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='accounts/password_reset_complete.html',
         ), name='password_reset_complete'),
]
