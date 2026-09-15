"""Bounded JSON schemas and function-call assembly shared by both harnesses."""
import json
import re

from jsonschema import Draft202012Validator

from hearth.inference import ProviderError

NAME = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


def valid_schema(schema):
    schema = resolve_local_schema(schema)
    if not isinstance(schema, dict) or schema.get('type') != 'object':
        raise ValueError('A tool input schema must describe an object.')
    if len(json.dumps(schema, allow_nan=False).encode()) > 32768:
        raise ValueError('The tool schema exceeds 32 KiB.')
    pending = [(schema, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 24:
            raise ValueError('The tool schema is too deeply nested.')
        if isinstance(value, dict):
            # No external retrieval, recursion or unbounded regex evaluation.
            if any(key in value for key in ('$ref', '$dynamicRef', '$recursiveRef', 'pattern', 'patternProperties')):
                raise ValueError('References and regular expressions are not supported in tool schemas yet.')
            pending.extend((item, depth+1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth+1) for item in value)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception:
        raise ValueError('The tool schema is not valid JSON Schema.') from None
    return schema


def resolve_local_schema(schema):
    """Inline acyclic local references before validation or model dispatch."""
    if not isinstance(schema, dict) or len(json.dumps(schema, allow_nan=False).encode()) > 32768:
        raise ValueError('The schema must be a bounded JSON object.')
    visits = 0
    def resolve(value, references=(), depth=0):
        nonlocal visits
        visits += 1
        if depth > 24 or visits > 4096:
            raise ValueError('The tool schema is too deeply nested or complex.')
        if isinstance(value, list):
            return [resolve(item, references, depth+1) for item in value]
        if not isinstance(value, dict):
            return value
        if '$ref' in value:
            pointer = value['$ref']
            if not isinstance(pointer, str) or not pointer.startswith('#/') or pointer in references:
                raise ValueError('Only acyclic references within the tool schema are supported.')
            target = schema
            try:
                for key in pointer[2:].split('/'):
                    target = target[key.replace('~1', '/').replace('~0', '~')]
            except (KeyError, TypeError):
                raise ValueError('The local schema reference is invalid.') from None
            resolved = resolve(target, (*references, pointer), depth+1)
            siblings = {key: resolve(item, references, depth+1) for key, item in value.items() if key not in {'$ref', '$defs', 'definitions', '$id'}}
            if not isinstance(resolved, dict):
                raise ValueError('The local reference must describe a schema object.')
            if set(resolved) & set(siblings) - {'title', 'description', 'default'}:
                return {'allOf': [resolved, siblings]}
            return resolved | siblings
        return {key: resolve(item, references, depth+1) for key, item in value.items() if key not in {'$defs', 'definitions', '$id'}}
    return resolve(schema)


def validate_arguments(arguments, schema):
    if not isinstance(arguments, dict) or len(json.dumps(arguments, allow_nan=False).encode()) > 65536:
        raise ValueError('Tool arguments must be an object of at most 64 KiB.')
    if not Draft202012Validator(resolve_local_schema(schema)).is_valid(arguments):
        raise ValueError('The arguments do not match the described tool schema.')


class ToolCalls:
    def __init__(self, tools):
        self.definitions = {item['function']['name']: item['function']['parameters'] for item in tools or []}
        self.items = {}
        self.size = 0

    def feed(self, deltas):
        if not isinstance(deltas, list):
            raise ValueError()
        for delta in deltas:
            index = delta['index']
            if type(index) is not int or not 0 <= index < 16:
                raise ValueError()
            item = self.items.setdefault(index, {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
            if delta.get('type', 'function') != 'function':
                raise ValueError()
            for key in ('id',):
                if key in delta:
                    if not isinstance(delta[key], str):
                        raise ValueError()
                    item[key] += delta[key]
                    self.size += len(delta[key])
            for key in ('name', 'arguments'):
                part = delta.get('function', {}).get(key)
                if part is not None:
                    if not isinstance(part, str):
                        raise ValueError()
                    item['function'][key] += part
                    self.size += len(part.encode())
            if self.size > 65536:
                raise ProviderError('The model tool request exceeded 64 KiB.', uncertain=True)

    def complete(self):
        items = [self.items[key] for key in sorted(self.items)]
        if not items or sorted(self.items) != list(range(len(items))) or len({item['id'] for item in items}) != len(items):
            raise ValueError()
        for item in items:
            function = item['function']
            if not NAME.fullmatch(item['id']) or function['name'] not in self.definitions:
                raise ValueError()
            arguments = json.loads(function['arguments'])
            validate_arguments(arguments, self.definitions[function['name']])
        return items
