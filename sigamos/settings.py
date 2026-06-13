"""
SIGAMOS — Configuración principal del proyecto Django.
Lee variables sensibles desde .env usando python-decouple.

JWT:        SIMPLE_JWT  →  clave: SEBASTIANRODRIGO (configurable en .env)
PostgreSQL: DATABASES   →  DATABASE_URL en producción (Render) o vars individuales en local
"""
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from decouple import Csv, config

# Constantes de mensajes Django (no dependen del app registry)
from django.contrib.messages import constants as MESSAGE_CONSTANTS

# ──────────────────────────────────────────────────────────────────────────────
# RUTAS BASE
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# Permite hacer: from src.predict import recommend  en cualquier vista
sys.path.insert(0, str(BASE_DIR))

# ──────────────────────────────────────────────────────────────────────────────
# SEGURIDAD
# ──────────────────────────────────────────────────────────────────────────────
SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-cambiar-en-produccion')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# CSRF: en producción (HTTPS) Django exige el origen completo (esquema+host)
# para aceptar formularios POST como el login. Sin esto → 403 en Render.
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://*.onrender.com',
    cast=Csv(),
)

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ──────────────────────────────────────────────────────────────────────────────
# APLICACIONES INSTALADAS
# ──────────────────────────────────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',  # necesario para logout (blacklist)
    'corsheaders',
]

LOCAL_APPS = [
    'accounts',
    'financiero',
    'recomendaciones',
    'gamificacion',
    'panel_admin',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ──────────────────────────────────────────────────────────────────────────────
# MIDDLEWARE
# corsheaders.middleware.CorsMiddleware DEBE ir antes de CommonMiddleware
# ──────────────────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'sigamos.urls'

# ──────────────────────────────────────────────────────────────────────────────
# TEMPLATES
# ──────────────────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'sigamos.wsgi.application'

# ──────────────────────────────────────────────────────────────────────────────
# BASE DE DATOS — PostgreSQL
# Credenciales en .env:  DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
# ──────────────────────────────────────────────────────────────────────────────
_DATABASE_URL = config('DATABASE_URL', default=None)
if _DATABASE_URL:
    DATABASES = {'default': dj_database_url.parse(_DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='sigamos_db'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
            'OPTIONS': {'client_encoding': 'UTF8'},
        }
    }

# ──────────────────────────────────────────────────────────────────────────────
# AUTENTICACIÓN DE USUARIO
# ──────────────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.Usuario'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# URLs para el flujo de autenticación vía Django sessions (páginas web)
LOGIN_URL = '/auth/login/'
LOGIN_REDIRECT_URL = '/financiero/'
LOGOUT_REDIRECT_URL = '/auth/login/'

# ──────────────────────────────────────────────────────────────────────────────
# DJANGO REST FRAMEWORK (DRF)
# ──────────────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    # JWT para clientes externos (Postman, móvil) + SessionAuth para los templates Django
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    # Todos los endpoints requieren autenticación salvo los marcados con AllowAny
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    # Manejador global de errores — normaliza todas las respuestas de error
    'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
}

# ──────────────────────────────────────────────────────────────────────────────
# JWT — djangorestframework-simplejwt
#
# CLAVE DE FIRMA: SEBASTIANRODRIGO  (configurable via JWT_SIGNING_KEY en .env)
# ALGORITMO:      HS256
# ACCESS TOKEN:   1 hora  (configurable via JWT_ACCESS_HOURS en .env)
# REFRESH TOKEN:  7 días  (configurable via JWT_REFRESH_DAYS en .env)
#
# El refresh token se invalida tras cada uso (BLACKLIST_AFTER_ROTATION=True)
# y se registra en la tabla OutstandingToken / BlacklistedToken de simplejwt.
# ──────────────────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(
        hours=config('JWT_ACCESS_HOURS', default=1, cast=int)
    ),
    'REFRESH_TOKEN_LIFETIME': timedelta(
        days=config('JWT_REFRESH_DAYS', default=7, cast=int)
    ),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,

    # ← Clave de firma del proyecto SIGAMOS
    'SIGNING_KEY': config('JWT_SIGNING_KEY', default='SEBASTIANRODRIGO'),
    'ALGORITHM': 'HS256',

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',
}

# ──────────────────────────────────────────────────────────────────────────────
# CORS — Cross-Origin Resource Sharing
# Permite que el frontend JS llame a /api/v1/ desde el mismo dominio
# ──────────────────────────────────────────────────────────────────────────────
_cors_raw = config('CORS_ALLOWED_ORIGINS', default='http://localhost:8000,http://127.0.0.1:8000')
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_raw.split(',') if o.strip()]
CORS_ALLOW_CREDENTIALS = True

# ──────────────────────────────────────────────────────────────────────────────
# INTERNACIONALIZACIÓN Y ZONA HORARIA
# ──────────────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'es-pe'
TIME_ZONE = 'America/Lima'
USE_I18N = True
USE_TZ = True

# ──────────────────────────────────────────────────────────────────────────────
# ARCHIVOS ESTÁTICOS Y MEDIA
# ──────────────────────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ──────────────────────────────────────────────────────────────────────────────
# CORREO ELECTRÓNICO
# En desarrollo: imprime en consola. En producción: cambiar a SMTP.
# ──────────────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.console.EmailBackend',
)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@sigamos.pe')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

# ──────────────────────────────────────────────────────────────────────────────
# MENSAJES DJANGO (flash messages — para templates)
# ──────────────────────────────────────────────────────────────────────────────
MESSAGE_TAGS = {
    MESSAGE_CONSTANTS.DEBUG:   'debug',
    MESSAGE_CONSTANTS.INFO:    'info',
    MESSAGE_CONSTANTS.SUCCESS: 'success',
    MESSAGE_CONSTANTS.WARNING: 'warning',
    MESSAGE_CONSTANTS.ERROR:   'error',
}
