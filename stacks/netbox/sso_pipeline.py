"""Sync NetBox groups and superuser state from the OIDC `groups` claim.

NetBox's own `REMOTE_AUTH_GROUP_SYNC_ENABLED` / `REMOTE_AUTH_SUPERUSER_GROUPS`
settings are consumed only by the HTTP-header (RemoteUserBackend) login path.
OIDC logins go through python-social-auth, which never calls that code, so this
pipeline step does the same job from the token's `groups` claim.

The step is mounted into the NetBox package as `netbox.sso_pipeline` and named
at the end of `SOCIAL_AUTH_PIPELINE` in `configuration.py`.
"""
from django.conf import settings
from users.models import Group


def _names(response):
    groups = (response or {}).get('groups') or []
    if isinstance(groups, str):
        groups = [groups]
    return {name for name in groups if name}


def sync_groups(backend, user, response, *args, **kwargs):
    """Full sync: the user's NetBox groups become exactly the claim's groups.

    `admins` (REMOTE_AUTH_SUPERUSER_GROUPS) becomes a superuser; everyone else
    keeps only what the group they landed in grants (the `users` group is given
    view-only access by `seed_sso.py`).
    """
    names = _names(response)
    user.groups.set([Group.objects.get_or_create(name=name)[0] for name in sorted(names)])
    superusers = set(getattr(settings, 'REMOTE_AUTH_SUPERUSER_GROUPS', []))
    # NetBox 4.7 dropped is_staff from the user model; is_superuser is the flag.
    user.is_superuser = bool(names & superusers)
    user.save(update_fields=['is_superuser'])
