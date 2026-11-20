"""Privately configure the Supabase database for local Django development."""

from getpass import getpass
from pathlib import Path

from dotenv import set_key
import psycopg2


def main():
    print('Supabase Dashboard > SmartNest > Connect: use direct or Session pooler.')
    print('Copy the host and username exactly. Enter your database password below.')
    host = input('Database host: ').strip()
    user = input('Database username: ').strip()
    password = getpass('Database password (hidden): ')
    if not host or not user or not password:
        raise SystemExit('Host, username and password are required; nothing saved.')

    try:
        with psycopg2.connect(
            host=host, user=user, password=password, dbname='postgres', port=5432,
            sslmode='require', connect_timeout=10,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                assert cursor.fetchone() == (1,)
                # A private schema keeps Django data out of the public Data API.
                cursor.execute('CREATE SCHEMA IF NOT EXISTS smartnest')
    except psycopg2.Error:
        raise SystemExit(
            'Database connection/schema setup failed; nothing saved. Check the '
            'host, username, password and network. On IPv4 use the Session pooler.'
        ) from None

    path = Path(__file__).resolve().parent / '.env.local'
    for name, value in {
        'DB_HOST': host, 'DB_USER': user, 'DB_PASSWORD': password,
        'DB_NAME': 'postgres', 'DB_PORT': '5432', 'DB_SSLMODE': 'require',
        'DB_SCHEMA': 'smartnest',
    }.items():
        set_key(str(path), name, value)
    print('Connection verified and saved privately in backend/.env.local.')
    print('Run: python manage.py migrate')
    print('Then: python manage.py runserver')


if __name__ == '__main__':
    main()
