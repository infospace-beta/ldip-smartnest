"""Create a persistent local signing key without changing existing configuration."""

import os
from pathlib import Path
import secrets

from dotenv import dotenv_values


def main():
    path = Path(__file__).resolve().parent / '.env.local'
    values = dotenv_values(path) if path.exists() else {}
    # Match settings.py: a process variable takes precedence, even if empty.
    existing = os.environ.get('DJANGO_SECRET_KEY', values.get('DJANGO_SECRET_KEY'))
    if existing is not None:
        if len(existing.strip()) < 50 or existing.startswith('django-insecure-'):
            raise SystemExit(
                'Existing DJANGO_SECRET_KEY is invalid. Update it in the process '
                'environment or .env.local; no existing value was changed.'
            )
        print('DJANGO_SECRET_KEY is already configured; kept the existing value.')
        return

    # Append instead of rewriting so database/auth configuration stays intact.
    with path.open('a', encoding='utf-8') as env_file:
        env_file.write('\n# Private persistent signing key. Do not commit this file.\n')
        env_file.write(f'DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\n')
    print('Saved a private signing key in backend/.env.local (value hidden).')
    print('Configure your database and authentication settings before using the app.')


if __name__ == '__main__':
    main()
