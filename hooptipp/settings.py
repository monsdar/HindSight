import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = 'django-insecure-hooptipp-prototype-key'
DEBUG = True


def _extend_from_env(
    environ: Mapping[str, str], key: str, base_values: Iterable[str] | None = None
) -> list[str]:
    """Return a list of configuration values extended by environment settings."""

    values = list(base_values or [])
    configured_values = environ.get(key)
    if configured_values:
        for value in (entry.strip() for entry in configured_values.split(',')):
            if value and value not in values:
                values.append(value)
    return values


def _build_allowed_hosts(
    environ: Mapping[str, str], base_hosts: Iterable[str] | None = None
) -> list[str]:
    """Return the allowed hosts extended by environment configuration."""

    return _extend_from_env(environ, 'DJANGO_ALLOWED_HOSTS', base_hosts)


def _host_to_origin(host: str) -> Optional[str]:
    """Convert an allowed host entry into an origin string."""

    cleaned_host = host.strip().lstrip('.')
    if not cleaned_host:
        return None
    if '://' in cleaned_host:
        return cleaned_host.rstrip('/')

    lower_host = cleaned_host.lower()
    http_hosts = (
        'localhost',
        '127.0.0.1',
        '0.0.0.0',
    )
    scheme = 'http' if any(lower_host.startswith(candidate) for candidate in http_hosts) else 'https'
    return f"{scheme}://{cleaned_host}"


def _build_csrf_trusted_origins(
    environ: Mapping[str, str], allowed_hosts: Iterable[str]
) -> list[str]:
    """Return the CSRF trusted origins derived from allowed hosts and env settings."""

    base_origins = [
        origin
        for host in allowed_hosts
        for origin in [_host_to_origin(host)]
        if origin is not None
    ]
    return _extend_from_env(environ, 'DJANGO_CSRF_TRUSTED_ORIGINS', base_origins)


ALLOWED_HOSTS = _build_allowed_hosts(os.environ)
CSRF_TRUSTED_ORIGINS = _build_csrf_trusted_origins(os.environ, ALLOWED_HOSTS)

INSTALLED_APPS = [
    'hooptipp.apps.HooptippConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'hooptipp.predictions',
    'hooptipp.nba',
    'hooptipp.dbb',
    'hooptipp.demo',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'hooptipp.middleware.PrivacyGateMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'hooptipp.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'hooptipp.context_processors.page_customization',
            ],
        },
    },
]

WSGI_APPLICATION = 'hooptipp.wsgi.application'


def _get_conn_max_age(environ: Mapping[str, str]) -> Optional[int]:
    """Return the configured connection max age, if any."""

    candidates = (
        environ.get('DATABASE_CONN_MAX_AGE'),
        environ.get('POSTGRES_CONN_MAX_AGE'),
    )
    for value in candidates:
        if value:
            return int(value)
    return None


def _build_sqlite_database(base_dir: Path) -> Dict[str, Any]:
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': base_dir / 'db.sqlite3',
    }


def _build_postgres_from_url(url: str, environ: Mapping[str, str]) -> Dict[str, Any]:
    parsed = urlparse(url)
    engine_map = {
        'postgres': 'django.db.backends.postgresql',
        'postgresql': 'django.db.backends.postgresql',
        'postgresql_psycopg2': 'django.db.backends.postgresql',
    }
    engine = engine_map.get(parsed.scheme)
    if engine is None:
        raise ValueError(f"Unsupported database scheme '{parsed.scheme}' in DATABASE_URL")

    database_name = parsed.path.lstrip('/')
    options: Dict[str, str] = {}
    if parsed.query:
        options = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}

    config: Dict[str, Any] = {
        'ENGINE': engine,
        'NAME': database_name,
        'USER': parsed.username or '',
        'PASSWORD': parsed.password or '',
        'HOST': parsed.hostname or '',
        'PORT': str(parsed.port) if parsed.port else '',
    }

    conn_max_age = _get_conn_max_age(environ)
    if conn_max_age is not None:
        config['CONN_MAX_AGE'] = conn_max_age
    if options:
        config['OPTIONS'] = options

    return config


def _build_postgres_from_env(environ: Mapping[str, str]) -> Optional[Dict[str, Any]]:
    database_name = environ.get('POSTGRES_DB')
    if not database_name:
        return None

    options: Dict[str, str] = {}
    ssl_mode = environ.get('POSTGRES_SSL_MODE')
    if ssl_mode:
        options['sslmode'] = ssl_mode

    config: Dict[str, Any] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': database_name,
        'USER': environ.get('POSTGRES_USER', ''),
        'PASSWORD': environ.get('POSTGRES_PASSWORD', ''),
        'HOST': environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': environ.get('POSTGRES_PORT', '5432'),
    }

    conn_max_age = _get_conn_max_age(environ)
    if conn_max_age is not None:
        config['CONN_MAX_AGE'] = conn_max_age
    if options:
        config['OPTIONS'] = options

    return config


def _build_default_database(base_dir: Path, environ: Mapping[str, str]) -> Dict[str, Any]:
    database_url = environ.get('DATABASE_URL')
    if database_url:
        return _build_postgres_from_url(database_url, environ)

    postgres_config = _build_postgres_from_env(environ)
    if postgres_config:
        return postgres_config

    return _build_sqlite_database(base_dir)


DATABASES = {
    'default': _build_default_database(BASE_DIR, os.environ),
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (user uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

if DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
else:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Privacy Gate Configuration
PRIVACY_GATE_ENABLED = os.environ.get('PRIVACY_GATE_ENABLED', 'True').lower() == 'true'
PRIVACY_GATE_CORRECT_ANSWER = os.environ.get('PRIVACY_GATE_ANSWER', 'ORL,GSW,BOS,OKC').split(',')

# User Selection Configuration
ENABLE_USER_SELECTION = os.environ.get('ENABLE_USER_SELECTION', 'True').lower() == 'true'

# Page Customization
PAGE_TITLE = os.environ.get('PAGE_TITLE', 'HindSight')
PAGE_SLOGAN = os.environ.get('PAGE_SLOGAN', "Find out who's always right!")

# Test Configuration
TESTING = 'test' in sys.argv or 'pytest' in sys.argv[0] if sys.argv else False

# Authentication Configuration
# These settings are used when ENABLE_USER_SELECTION=False (authentication mode)
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Email Configuration (for password reset and email verification)
# In development, emails are printed to console
# In production, configure SMTP or AWS SES settings via environment variables
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'  # Default for development
)

# AWS SES Configuration (when using django-ses)
if EMAIL_BACKEND == 'django_ses.SESBackend':
    AWS_SES_REGION_NAME = os.environ.get('AWS_SES_REGION_NAME', 'us-east-1')
    # Only set AWS_SES_REGION_ENDPOINT if explicitly provided
    # If not set, django-ses will automatically construct the endpoint from the region
    aws_ses_endpoint = os.environ.get('AWS_SES_REGION_ENDPOINT', '').strip()
    if aws_ses_endpoint:
        AWS_SES_REGION_ENDPOINT = aws_ses_endpoint
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', '')
    if not DEFAULT_FROM_EMAIL:
        raise ValueError(
            'DEFAULT_FROM_EMAIL must be set when using AWS SES backend. '
            'Set it via the DEFAULT_FROM_EMAIL environment variable.'
        )
    
    # Python 3.12 compatibility fix for django-ses
    # django-ses calls message.as_bytes(linesep="\n") but Python 3.12's email library
    # no longer accepts the linesep parameter. This patch fixes the issue.
    try:
        from email.message import Message
        import inspect
        
        # Store original as_bytes method
        original_as_bytes = Message.as_bytes
        
        # Check if as_bytes accepts linesep parameter
        sig = inspect.signature(original_as_bytes)
        accepts_linesep = 'linesep' in sig.parameters
        
        if not accepts_linesep:
            # Python 3.12+ doesn't accept linesep, create wrapper that ignores it
            def patched_as_bytes(self, unixfrom=False, linesep=None):
                # Ignore linesep parameter and call original method
                return original_as_bytes(self, unixfrom=unixfrom)
            
            # Apply the patch to the Message class
            Message.as_bytes = patched_as_bytes
    except (ImportError, AttributeError):
        # email library or Message not available, skip patching
        pass
# Optional SMTP settings for production (only needed if using SMTP backend)
elif EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend':
    EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
    email_port_str = os.environ.get('EMAIL_PORT', '587')
    email_port = int(email_port_str)
    EMAIL_PORT = email_port
    
    # TLS vs SSL configuration
    # AWS SES: Port 587 uses STARTTLS (TLS), Port 465 uses SSL
    # Allow explicit override via environment variables
    use_tls_env = os.environ.get('EMAIL_USE_TLS', '').lower()
    use_ssl_env = os.environ.get('EMAIL_USE_SSL', '').lower()
    
    if email_port == 465:
        # Port 465 requires SSL, not TLS
        if use_ssl_env:
            EMAIL_USE_SSL = use_ssl_env == 'true'
        else:
            EMAIL_USE_SSL = True  # Default to True for port 465
        if use_tls_env:
            EMAIL_USE_TLS = use_tls_env == 'true'
        else:
            EMAIL_USE_TLS = False  # Don't use TLS with SSL
    else:
        # Port 587 and other ports use STARTTLS (TLS)
        if use_tls_env:
            EMAIL_USE_TLS = use_tls_env == 'true'
        else:
            EMAIL_USE_TLS = True  # Default to True for port 587
        if use_ssl_env:
            EMAIL_USE_SSL = use_ssl_env == 'true'
        else:
            EMAIL_USE_SSL = False  # Don't use SSL with TLS
    
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
    DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)
    
    # Connection timeout settings (important for AWS SES)
    # Increase timeout for AWS SES which may have rate limiting
    EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '30'))  # 30 seconds default
else:
    # Console backend or other backends - set DEFAULT_FROM_EMAIL if provided
    DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@localhost')

# Cache Configuration (for rate limiting and other features)
# Default to local memory cache - can be overridden via CACHES environment variable
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# Hotness System Configuration
HOTNESS_DECAY_PER_HOUR = float(os.environ.get('HOTNESS_DECAY_PER_HOUR', '0.1'))
