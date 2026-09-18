"""A deliberately narrow, self-contained GLB profile for generated assets."""
import io
import json
import math
import struct

from PIL import Image

MAX_GLB = 64 * 1024 * 1024


def validate_glb(raw):
    if not 28 <= len(raw) <= MAX_GLB:
        raise ValueError('GLB size is outside the supported limits.')
    magic, version, length = struct.unpack_from('<4sII', raw)
    if magic != b'glTF' or version != 2 or length != len(raw):
        raise ValueError('Invalid GLB header.')
    size, kind = struct.unpack_from('<II', raw, 12)
    if kind != 0x4E4F534A or size > 1024 * 1024 or size % 4 or 28 + size > len(raw):
        raise ValueError('Invalid GLB JSON chunk.')
    doc = json.loads(raw[20:20 + size])
    offset = 20 + size
    binary_size, kind = struct.unpack_from('<II', raw, offset)
    binary = raw[offset + 8:]
    if kind != 0x004E4942 or binary_size != len(binary) or binary_size % 4:
        raise ValueError('GLB must contain exactly one embedded binary chunk.')
    if doc.get('asset', {}).get('version') != '2.0' or len(doc.get('buffers', [])) != 1:
        raise ValueError('Unsupported GLB version or buffers.')
    if not 0 <= doc['buffers'][0].get('byteLength', -1) <= len(binary):
        raise ValueError('Invalid GLB buffer bounds.')
    def safe(value, depth=0):
        if depth > 32:
            raise ValueError('GLB nesting limit exceeded.')
        if isinstance(value, dict):
            if any(key in value for key in ('uri', 'extensions', 'extensionsRequired', 'extensionsUsed')):
                raise ValueError('External resources and GLB extensions are unsupported.')
            for item in value.values():
                safe(item, depth + 1)
        elif isinstance(value, list):
            if len(value) > 100_000:
                raise ValueError('GLB collection limit exceeded.')
            for item in value:
                safe(item, depth + 1)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Non-finite GLB value.')
    safe(doc)
    if doc.get('animations') or doc.get('skins') or len(doc.get('nodes', [])) > 256:
        raise ValueError('Only bounded static meshes are supported.')
    views = doc.get('bufferViews', [])
    if not 1 <= len(views) <= 256:
        raise ValueError('Invalid buffer view count.')
    for view in views:
        start, count = view.get('byteOffset', 0), view.get('byteLength', -1)
        if view.get('buffer') != 0 or start < 0 or count < 0 or start + count > len(binary):
            raise ValueError('Invalid buffer view bounds.')
    accessors = doc.get('accessors', [])
    if not 1 <= len(accessors) <= 256:
        raise ValueError('Invalid accessor count.')
    components = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
    vectors = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
    for accessor in accessors:
        if 'sparse' in accessor or not 0 <= accessor.get('bufferView', -1) < len(views):
            raise ValueError('Unsupported accessor.')
        view = views[accessor['bufferView']]
        width = components[accessor['componentType']] * vectors[accessor['type']]
        count, start = accessor['count'], accessor.get('byteOffset', 0)
        stride = view.get('byteStride', width)
        if not 0 < count <= 3_000_000 or not width <= stride <= 252 or start < 0 or start + (count - 1) * stride + width > view['byteLength']:
            raise ValueError('Invalid accessor bounds.')
        if accessor['componentType'] == 5126:
            base = view.get('byteOffset', 0) + start
            for index in range(count):
                if any(not math.isfinite(value) for value in struct.unpack_from('<' + 'f' * vectors[accessor['type']], binary, base + index * stride)):
                    raise ValueError('Non-finite vertex attribute.')
    triangles = 0
    meshes = doc.get('meshes', [])
    if not 1 <= len(meshes) <= 64:
        raise ValueError('Invalid mesh count.')
    for mesh in meshes:
        for primitive in mesh['primitives']:
            if primitive.get('mode', 4) != 4 or primitive.get('targets'):
                raise ValueError('Only static triangle meshes are supported.')
            position = accessors[primitive['attributes']['POSITION']]
            if position['type'] != 'VEC3' or position['componentType'] != 5126:
                raise ValueError('Invalid vertex positions.')
            count = accessors[primitive['indices']]['count'] if 'indices' in primitive else position['count']
            if 'indices' in primitive:
                indices = accessors[primitive['indices']]
                if indices['type'] != 'SCALAR' or indices['componentType'] not in {5121, 5123, 5125}:
                    raise ValueError('Invalid triangle indices.')
                view = views[indices['bufferView']]
                base = view.get('byteOffset', 0) + indices.get('byteOffset', 0)
                width = components[indices['componentType']]
                for index in range(count):
                    value = struct.unpack_from('<' + {5121: 'B', 5123: 'H', 5125: 'I'}[indices['componentType']], binary, base + index * view.get('byteStride', width))[0]
                    if value >= position['count']:
                        raise ValueError('Triangle index exceeds vertex bounds.')
            if count % 3:
                raise ValueError('Incomplete triangles.')
            triangles += count // 3
    if not 1 <= triangles <= 1_000_000:
        raise ValueError('Mesh triangle limit exceeded.')
    nodes = doc.get('nodes', [])
    def walk(index, ancestors):
        if index in ancestors or not 0 <= index < len(nodes) or len(ancestors) > 32:
            raise ValueError('Invalid scene hierarchy.')
        for child in nodes[index].get('children', []):
            walk(child, ancestors | {index})
    for index in range(len(nodes)):
        walk(index, set())
    textures = doc.get('images', [])
    if len(textures) > 8:
        raise ValueError('Too many textures.')
    for texture in textures:
        view = views[texture['bufferView']]
        start = view.get('byteOffset', 0)
        with Image.open(io.BytesIO(binary[start:start + view['byteLength']])) as image:
            if image.format != 'PNG' or max(image.size) > 4096 or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Unsupported texture.')
            image.verify()
    return {'triangles': triangles, 'textures': len(textures), 'bytes': len(raw), 'format': 'glb'}
