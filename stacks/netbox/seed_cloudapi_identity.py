import json
import os
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from users.models import User, ObjectPermission, Token

# The cloud API writes only what it owns: the VM ledger and IP allocations.
# Terraform's identity also writes dcim and tenancy; this one must not, so a
# bug in the user-facing API cannot rewrite the platform's device records.
# Sites, clusters and tags still have to be readable to resolve foreign keys,
# hence the second, view-only permission.
WRITE_APP_LABELS = ['virtualization', 'ipam']
READ_APP_LABELS = ['dcim', 'extras']
WRITE_ACTIONS = ['view', 'add', 'change', 'delete']
READ_ACTIONS = ['view']

credential = json.loads(os.environ['SEED_CREDENTIAL'])
changed = False
with transaction.atomic():
    user, created = User.objects.get_or_create(username='cloudapi')
    changed = changed or created
    if created:
        user.set_unusable_password()
        user.save()
    # NetBox 4.7 dropped is_staff from its user model; check is_superuser only.
    if user.is_superuser:
        raise RuntimeError('Cloud API identity must not be a superuser')
    for name, actions, labels in (
            ('Cloud API ledger write', WRITE_ACTIONS, WRITE_APP_LABELS),
            ('Cloud API reference read', READ_ACTIONS, READ_APP_LABELS)):
        permission, permission_created = ObjectPermission.objects.get_or_create(
            name=name, defaults={'actions': actions})
        changed = changed or permission_created
        if sorted(permission.actions) != sorted(actions):
            raise RuntimeError(f'{name} has unexpected actions; refusing to widen it')
        permission.object_types.set(ContentType.objects.filter(app_label__in=labels))
        permission.users.add(user)
    token, created = Token.objects.get_or_create(key=credential['key'], defaults={
        'user': user, 'version': 2, 'token': credential['token'],
        'write_enabled': True, 'description': 'Cloud API ledger automation',
    })
    changed = changed or created
    if not created and (token.user_id != user.pk or not token.write_enabled):
        raise RuntimeError('Existing cloud API token does not match expected identity')
# Report accurately so Ansible does not show a change on every run.
print('CHANGED: registered cloud API write identity' if changed
      else 'OK: cloud API write identity already present')
