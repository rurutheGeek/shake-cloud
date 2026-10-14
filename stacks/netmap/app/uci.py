"""Parse the output of `uci show` into sections.

Each section is a dict with `.name` (its uci name, `@rule[3]` for anonymous
ones), `.type` and the options. A list option becomes a Python list.
"""
import re
import shlex

LINE = re.compile(r'^(?P<config>[a-z0-9_]+)\.(?P<section>[^.=]+)(?:\.(?P<option>[^=]+))?=(?P<value>.*)$')


def parse(text):
    configs = {}
    for line in text.splitlines():
        match = LINE.match(line.strip())
        if not match:
            continue
        sections = configs.setdefault(match['config'], {})
        name = match['section']
        if match['option'] is None:
            sections[name] = {'.name': name, '.type': match['value']}
            continue
        try:
            values = shlex.split(match['value'])
        except ValueError:
            values = [match['value']]
        value = values[0] if len(values) == 1 else values
        sections.setdefault(name, {'.name': name, '.type': ''})[match['option']] = value
    return configs


def of_type(config, kind):
    return [section for section in config.values() if section.get('.type') == kind]


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return value.split()
