from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from accounts.models import Usuario
from accounts.validators import validar_dominio_email, validar_formato_nickname


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
        max_length=20,
        label='Nickname',
        validators=[validar_formato_nickname],
        widget=forms.TextInput(attrs={
            'class': 'form-input', 'placeholder': 'Tu nombre de usuario', 'maxlength': 20,
        }),
    )
    email = forms.EmailField(
        label='Correo electrónico',
        validators=[validar_dominio_email],
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
        min_value=18, max_value=80,
        required=False,
        label='Edad',
        widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ej: 25', 'min': 18, 'max': 80}),
    )
    nivel_educ = forms.ChoiceField(
        choices=[('', 'Selecciona tu nivel…')] + list(Usuario.NIVEL_EDUC_CHOICES),
        required=False,
        label='Nivel educativo',
        widget=forms.Select(attrs={'class': 'form-input'}),
    )

    def clean_email(self):
        # El formato (incluido el dominio) ya lo valida validar_dominio_email en el
        # propio campo; aquí solo queda la unicidad, que no puede expresarse como
        # validator porque depende de una consulta.
        email = self.cleaned_data['email'].lower()
        if Usuario.objects.filter(email=email).exists():
            raise forms.ValidationError('Este correo ya está registrado.')
        return email

    def clean_nickname(self):
        # El formato (charset, letra obligatoria, no repetido) ya lo valida
        # validar_formato_nickname en el propio campo.
        nickname = self.cleaned_data['nickname'].strip()
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
    """Información personal del usuario (nickname, email, teléfono, ciudad).

    El formato de nickname/email/teléfono ya lo validan validar_formato_nickname /
    validar_dominio_email / validar_telefono_peru, declarados en el propio campo del
    modelo (Usuario): al ser un ModelForm, Django los ejecuta solo con instance.full_clean()
    en el _post_clean(), sin que este formulario tenga que repetirlos.
    """
    class Meta:
        model = Usuario
        fields = ['nickname', 'email', 'telefono', 'ciudad']
        widgets = {
            'nickname': forms.TextInput(attrs={'class': 'form-input', 'maxlength': 20}),
            'email':    forms.EmailInput(attrs={'class': 'form-input'}),
            'telefono': forms.TextInput(attrs={
                'class': 'form-input', 'placeholder': '987654321', 'maxlength': 9,
                'inputmode': 'numeric', 'pattern': '[0-9]{9}',
            }),
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
            'edad':           forms.NumberInput(attrs={'class': 'form-input', 'min': 18, 'max': 80}),
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
