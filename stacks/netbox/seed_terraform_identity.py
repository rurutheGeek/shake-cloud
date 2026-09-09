import json
import os
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from users.models import User, ObjectPermission, Token

# Terraform writes the ledger; the Ansible inventory identity stays read-only.
# Keep the two separate so a mistake in one cannot rewrite the other's scope.
APP_LABELS = ['dcim', 'virtualization', 'ipam', 'tenancy', 'extras']
ACTIONS = ['view', 'add', 'change', 'delete']

credential = json.loads(os.environ['SEED_CREDENTIAL'])
changed = False
with transaction.atomic():
    user, created = User.objects.get_or_create(username='terraform')
    changed = changed or created
    if created:
        user.set_unusable_password()
        user.save()
    # NetBox 4.7 dropped is_staff from its user model; check is_superuser only.
    if user.is_superuser:
        raise RuntimeError('Terraform identity must not be a superuser')
    permission, permission_created = ObjectPermission.objects.get_or_create(
        name='Terraform platform write', defaults={'actions': ACTIONS})
    changed = changed or permission_created
    if sorted(permission.actions) != sorted(ACTIONS):
        raise RuntimeError('Existing permission has unexpected actions; refusing to widen it')
    permission.object_types.set(ContentType.objects.filter(app_label__in=APP_LABELS))
    permission.users.add(user)
    token, created = Token.objects.get_or_create(key=credential['key'], defaults={
        'user': user, 'version': 2, 'token': credential['token'],
        'write_enabled': True, 'description': 'Terraform platform automation',
    })
    changed = changed or created
    if not created and (token.user_id != user.pk or not token.write_enabled):
        raise RuntimeError('Existing Terraform token does not match expected identity')
# Report accurately so Ansible does not show a change on every run.
print('CHANGED: registered Terraform write identity' if changed
      else 'OK: Terraform write identity already present')
