"""Original, deterministic reference illustration for transport qualification."""
import io

from PIL import Image, ImageDraw


def reference():
    image = Image.new('RGB', (512, 512), 'white')
    draw = ImageDraw.Draw(image)
    draw.polygon([(130, 160), (265, 90), (390, 160), (255, 235)], fill='#ffd18c')
    draw.polygon([(130, 160), (255, 235), (255, 415), (130, 335)], fill='#ba7540')
    draw.polygon([(255, 235), (390, 160), (390, 335), (255, 415)], fill='#f59c50')
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()
