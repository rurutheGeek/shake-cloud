"""Give the group OIDC users land in read-only access to the ledger.

The `sso_pipeline.sync_groups` step puts a user into the NetBox groups named by
the OIDC `groups` claim. `admins` becomes a superuser there; everyone else
lands in `users`, which this script gives one view-only permission so an
invited person can look at the ledger without being able to change it.
"""
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from users.models import Group, ObjectPermission

READ_APP_LABELS = ['dcim', 'ipam', 'virtualization', 'tenancy', 'extras']

changed = False
with transaction.atomic():
    group, created = Group.objects.get_or_create(name='users')
    changed = changed or created
    permission, permission_created = ObjectPermission.objects.get_or_create(
        name='SSO users (read only)', defaults={'actions': ['view']})
    changed = changed or permission_created
    if sorted(permission.actions) != ['view']:
        raise RuntimeError('SSO users permission has unexpected actions; refusing to widen it')
    permission.object_types.set(ContentType.objects.filter(app_label__in=READ_APP_LABELS))
    permission.groups.add(group)
# Report accurately so Ansible does not show a change on every run.
print('CHANGED: registered the read-only SSO group' if changed
      else 'OK: read-only SSO group already present')
