"""Minimal NetBox 4.7 configuration; secret files are required, no demo passwords."""
from os import environ
from pathlib import Path


def secret(name):
    return (Path('/run/secrets') / name).read_text().strip()


ALLOWED_HOSTS = environ.get('ALLOWED_HOSTS', 'localhost 127.0.0.1').split()
# HTTPS の入口（tls_proxy の Caddy）越しのログインで、Origin の https を CSRF 検査に通すため。
CSRF_TRUSTED_ORIGINS = environ.get('CSRF_TRUSTED_ORIGINS', '').split()
DATABASES = {'default': {
    'NAME': 'netbox', 'USER': 'netbox', 'PASSWORD': secret('db_password'),
    'HOST': 'postgres', 'PORT': 5432, 'CONN_MAX_AGE': 300,
}}
REDIS = {
    'tasks': {'HOST': 'redis', 'PORT': 6379, 'DATABASE': 0, 'SSL': False},
    'caching': {'HOST': 'redis-cache', 'PORT': 6379, 'DATABASE': 1, 'SSL': False},
}
SECRET_KEY = secret('secret_key')
API_TOKEN_PEPPERS = {1: secret('api_token_pepper_1')}
MEDIA_ROOT = '/opt/netbox/netbox/media'
CORS_ORIGIN_ALLOW_ALL = False
CENSUS_REPORTING_ENABLED = False

DEFAULT_USER_PREFERENCES = {'locale': {'language': 'ja'}}

if environ.get('NETBOX_SSO_ENABLED') == 'true':
    REMOTE_AUTH_ENABLED = True
    REMOTE_AUTH_BACKEND = ['social_core.backends.open_id_connect.OpenIdConnectAuth']
    REMOTE_AUTH_AUTO_CREATE_USER = True
    # NetBox's own group sync only runs for the HTTP-header (RemoteUserBackend)
    # path, never for social-auth/OIDC. Our pipeline reads the claim instead and
    # uses this list to decide who is a superuser.
    REMOTE_AUTH_SUPERUSER_GROUPS = ['admins']
    SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = environ['NETBOX_OIDC_ENDPOINT']
    SOCIAL_AUTH_OIDC_KEY = environ.get('NETBOX_OIDC_KEY', 'netbox')
    SOCIAL_AUTH_OIDC_SECRET = secret('oidc_client_secret')
    SOCIAL_AUTH_OIDC_USERNAME_KEY = 'sub'
    SOCIAL_AUTH_OIDC_SCOPE = ['openid', 'email', 'profile']
    SOCIAL_AUTH_PIPELINE = (
        'social_core.pipeline.social_auth.social_details',
        'social_core.pipeline.social_auth.social_uid',
        'social_core.pipeline.social_auth.social_user',
        'social_core.pipeline.user.get_username',
        'social_core.pipeline.user.create_user',
        'social_core.pipeline.social_auth.associate_user',
        'social_core.pipeline.social_auth.load_extra_data',
        'social_core.pipeline.user.user_details',
        'netbox.sso_pipeline.sync_groups',
    )
