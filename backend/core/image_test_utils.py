from io import BytesIO
from PIL import Image


def png_bytes():
    output = BytesIO()
    Image.new('RGBA', (4, 4), (10, 100, 200, 255)).save(output, 'PNG')
    return output.getvalue()
