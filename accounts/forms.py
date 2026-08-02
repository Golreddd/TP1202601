import re

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from accounts.models import Usuario

# Formato admitido para el nickname: 3-30 caracteres, letras (con acentos y ñ),
# números, espacio, punto, guion y guion bajo. Sin esto se aceptaba cualquier
# cadena —incluida "!!!@@@###"— como nombre de usuario visible.
NICKNAME_RE = re.compile(r'[\w.\- ]{3,30}', re.UNICODE)


def _aplicar_validadores_password(form, campo: str, password: str, usuario=None):
    """Aplica los AUTH_PASSWORD_VALIDATORS de settings.py a `password` y vuelca los
    errores en `campo` del formulario.

    Sin esto, el registro y el cambio de contraseña solo exigían `min_length=8`, así
    que aceptaban claves como "12345678" o "password" — mientras que el flujo de
    restablecimiento por correo (SetPasswordForm de Django) SÍ las rechazaba. Esta
    función unifica el criterio en los tres flujos.
    """
    if not password:
        return
    try:
        validate_password(password, user=usuario)
    except DjangoValidationError as exc:
        form.add_error(campo, list(exc.messages))


class RegistroForm(forms.Form):
    nickname = forms.CharField(
        max_length=30,
        label='Nickname',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Tu nombre de usuario'}),
    )
    email = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'tu@correo.com'}),
    )
    password = forms.CharField(
        min_length=8,
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': '••••••••'}),
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': '••••••••'}),
    )
    edad = forms.IntegerField(
        min_value=16, max_value=80,
        required=False,
        label='Edad',
        widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ej: 25'}),
    )
    nivel_educ = forms.ChoiceField(
        choices=[('', 'Selecciona tu nivel…')] + list(Usuario.NIVEL_EDUC_CHOICES),
        required=False,
        label='Nivel educativo',
        widget=forms.Select(attrs={'class': 'form-input'}),
    )

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if Usuario.objects.filter(email=email).exists():
            raise forms.ValidationError('Este correo ya está registrado.')
        return email

    def clean_nickname(self):
        nickname = self.cleaned_data['nickname'].strip()
        if not NICKNAME_RE.fullmatch(nickname):
            raise forms.ValidationError(
                'El nickname solo puede contener letras, números, espacios, punto, '
                'guion y guion bajo (mínimo 3 caracteres).'
            )
        if Usuario.objects.filter(nickname__iexact=nickname).exists():
            raise forms.ValidationError('Este nickname ya está en uso.')
        return nickname

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Las contraseñas no coinciden.')

        # Requisitos de seguridad (AUTH_PASSWORD_VALIDATORS). Se pasa un usuario
        # tentativo NO guardado para que UserAttributeSimilarityValidator pueda
        # comparar la clave contra el nickname y el correo recién ingresados.
        if p1:
            tentativo = Usuario(
                nickname=cleaned.get('nickname') or '',
                username=cleaned.get('nickname') or '',
                email=cleaned.get('email') or '',
            )
            _aplicar_validadores_password(self, 'password', p1, usuario=tentativo)
        return cleaned


class PerfilForm(forms.ModelForm):
    """Información personal del usuario (nickname, email, teléfono, ciudad)."""
    class Meta:
        model = Usuario
        fields = ['nickname', 'email', 'telefono', 'ciudad']
        widgets = {
            'nickname': forms.TextInput(attrs={'class': 'form-input'}),
            'email':    forms.EmailInput(attrs={'class': 'form-input'}),
            'telefono': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '+51 999 000 000'}),
            'ciudad':   forms.TextInput(attrs={'class': 'form-input'}),
        }

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        qs = Usuario.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Este correo ya está en uso por otra cuenta.')
        return email

    def clean_nickname(self):
        nickname = self.cleaned_data['nickname'].strip()
        if not NICKNAME_RE.fullmatch(nickname):
            raise forms.ValidationError(
                'El nickname solo puede contener letras, números, espacios, punto, '
                'guion y guion bajo (mínimo 3 caracteres).'
            )
        qs = Usuario.objects.filter(nickname__iexact=nickname).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Este nickname ya está en uso.')
        return nickname


class PerfilMLForm(forms.ModelForm):
    """Campos de perfil financiero requeridos por el análisis ML."""
    class Meta:
        model = Usuario
        fields = ['edad', 'nivel_educ', 'miembros_hogar']
        widgets = {
            'edad':           forms.NumberInput(attrs={'class': 'form-input', 'min': 16, 'max': 80}),
            'nivel_educ':     forms.Select(attrs={'class': 'form-input'}),
            'miembros_hogar': forms.NumberInput(attrs={'class': 'form-input', 'min': 1, 'max': 20}),
        }


class CambiarPasswordWebForm(forms.Form):
    password_actual = forms.CharField(
        label='Contraseña actual',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': '••••••••'}),
    )
    password_nuevo = forms.CharField(
        min_length=8,
        label='Nueva contraseña',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': '••••••••'}),
    )
    password_nuevo2 = forms.CharField(
        label='Confirmar nueva contraseña',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': '••••••••'}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password_actual(self):
        pw = self.cleaned_data.get('password_actual')
        if pw and not self.user.check_password(pw):
            raise forms.ValidationError('La contraseña actual es incorrecta.')
        return pw

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password_nuevo')
        p2 = cleaned.get('password_nuevo2')
        if p1 and p2 and p1 != p2:
            self.add_error('password_nuevo2', 'Las contraseñas no coinciden.')
        # Mismos requisitos de seguridad que el registro y el restablecimiento.
        _aplicar_validadores_password(self, 'password_nuevo', p1, usuario=self.user)
        return cleaned

    def save(self):
        self.user.set_password(self.cleaned_data['password_nuevo'])
        self.user.save(update_fields=['password'])
        return self.user
