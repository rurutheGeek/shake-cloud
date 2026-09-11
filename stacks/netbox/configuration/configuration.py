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
    SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = 'https://login.localhost:9443/application/o/netbox'
    SOCIAL_AUTH_OIDC_KEY = 'netbox'
    SOCIAL_AUTH_OIDC_SECRET = environ['NETBOX_OIDC_CLIENT_SECRET']
    SOCIAL_AUTH_OIDC_USERNAME_KEY = 'sub'
    SOCIAL_AUTH_OIDC_SCOPE = ['openid', 'email', 'profile']
