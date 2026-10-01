"""Closed image settings shared by the controller and installed providers."""
SIZES = {'square': (1024, 1024), 'landscape': (1024, 768), 'portrait': (768, 1024),
         'widescreen': (1024, 576), 'tall': (576, 1024)}
MAX_IMAGE_BYTES = 67108864


def dimensions(shape, resolution='native'):
    width, height = SIZES[shape]
    if resolution == 'native':
        return width, height
    scale = 2 if resolution == '2k' else 4
    if shape in {'widescreen', 'tall'}:
        return (1920 * scale // 2, 1080 * scale // 2) if shape == 'widescreen' else (1080 * scale // 2, 1920 * scale // 2)
    return width * scale, height * scale


def validate_settings(data, profile):
    if data.edit is not None and profile.get('editing') != 'fooocus-vary-v1':
        raise ValueError('This provider does not support uploaded image editing. Update and verify Fooocus in Administration.')
    if data.shape not in profile.get('shapes', []) or data.steps not in profile.get('steps', []):
        raise ValueError('These image dimensions or detail passes are not supported by this provider. Refresh its settings.')
    options = profile.get('options') or {}
    if data.options.resolution not in options.get('resolutions', ['native']):
        raise ValueError('This provider does not support that output resolution.')
    if data.options.styles is not None and (not options or any(style not in options.get('styles', []) for style in data.options.styles)):
        raise ValueError('Choose styles offered by this provider.')
    for name in ('guidance_scale', 'sharpness'):
        if getattr(data.options, name) is not None and options.get(name) is None:
            raise ValueError('This provider does not support that advanced image setting.')
