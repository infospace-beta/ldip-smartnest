"""Decode and re-encode images instead of trusting MIME headers or filenames."""
from io import BytesIO
import warnings
from uuid import uuid4
from PIL import Image, UnidentifiedImageError
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers


def clean_image(upload, label='Photos'):
    if upload.size > 5 * 1024 * 1024:
        raise serializers.ValidationError(f'{label} must be 5 MB or smaller.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(upload) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 16_000_000:
                    raise ValueError('Unsupported image')
                image.load()
                # Fix orientation before discarding camera EXIF (including location).
                from PIL.ImageOps import exif_transpose
                image = exif_transpose(image)
                alpha = image.mode in ('RGBA', 'LA') or 'transparency' in image.info
                clean = Image.new('RGBA' if alpha else 'RGB', image.size)
                clean.paste(image.convert(clean.mode))
                result = BytesIO()
                format_name = 'PNG' if alpha else 'JPEG'
                clean.save(result, format=format_name)
        if result.tell() > 5 * 1024 * 1024:
            raise ValueError('Re-encoded image too large')
        extension = 'png' if alpha else 'jpg'
        return SimpleUploadedFile(f'{uuid4().hex}.{extension}', result.getvalue(), content_type=f'image/{"png" if alpha else "jpeg"}')
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise serializers.ValidationError(f'Upload a valid JPEG, PNG or WebP image up to 16 megapixels for {label.lower()}.') from None
    finally:
        upload.seek(0)
