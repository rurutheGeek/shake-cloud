"""Preserve verified ownership only while the email address stays unchanged."""


def attributes_for(entry, user):
    attributes = dict((user or {}).get('attributes', {}))
    verified = attributes.get('email_verified', False) is True
    if not user or entry['email'] != user.get('email'):
        verified = False
    if 'email_verified' in entry:
        verified = entry['email_verified'] is True
    attributes.update(email_verified=verified,
                      settings={**attributes.get('settings', {}), 'locale': 'ja'})
    return attributes
