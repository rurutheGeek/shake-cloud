import json
import os
from pathlib import Path
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from dcim.models import Site
from extras.models import Tag
from ipam.models import IPAddress
from users.models import User, ObjectPermission, Token
from virtualization.models import VirtualMachine, VMInterface

# SEED_HOST is optional: Terraform registers hosts in NetBox now, so the
# read-only inventory identity is often all that is needed.
spec = json.loads(os.environ.get('SEED_HOST') or 'null')
credential = json.loads(os.environ['SEED_CREDENTIAL'])
with transaction.atomic():
    if spec:
        site, _ = Site.objects.get_or_create(slug='homelab', defaults={'name': 'Homelab', 'status': 'active'})
        tag, _ = Tag.objects.get_or_create(slug='media-stack', defaults={'name': 'media-stack'})
        vm, _ = VirtualMachine.objects.get_or_create(name=spec['name'], defaults={'site': site, 'status': 'active'})
        interface, _ = VMInterface.objects.get_or_create(virtual_machine=vm, name='primary')
        ip, created = IPAddress.objects.get_or_create(address=spec['address'], defaults={
            'status': 'active', 'assigned_object_type': ContentType.objects.get_for_model(VMInterface),
            'assigned_object_id': interface.pk,
        })
        if not created and ip.assigned_object_id != interface.pk:
            raise RuntimeError('Primary IP already assigned elsewhere; refusing to replace')
        vm.primary_ip4 = ip
        vm.save()
        vm.tags.add(tag)
    user, created = User.objects.get_or_create(username='ansible-inventory')
    if created:
        user.set_unusable_password()
        user.save()
    permission, _ = ObjectPermission.objects.get_or_create(name='Ansible inventory read', defaults={'actions': ['view']})
    permission.object_types.set(ContentType.objects.filter(app_label__in=['dcim', 'virtualization', 'ipam', 'tenancy', 'extras', 'wireless']))
    permission.users.add(user)
    token, created = Token.objects.get_or_create(key=credential['key'], defaults={
        'user': user, 'version': 2, 'token': credential['token'],
        'write_enabled': False, 'description': 'Local Ansible inventory',
    })
    if not created and (token.user_id != user.pk or token.write_enabled):
        raise RuntimeError('Existing inventory token does not match expected identity')
print('CHANGED: registered read-only API identity'
      + (' and inventory host' if spec else ''))
