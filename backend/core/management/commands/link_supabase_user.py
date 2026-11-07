from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from django.utils import timezone
from core.models import User


class Command(BaseCommand):
    help = 'Link an existing Django user to a verified Supabase Auth UUID. Confirm the identity in the Supabase dashboard first.'

    def add_arguments(self, parser):
        parser.add_argument('email')
        parser.add_argument('supabase_user_id', type=UUID)

    def handle(self, *args, **options):
        try:
            user = User.objects.get(email__iexact=options['email'])
        except User.DoesNotExist as error:
            raise CommandError('No matching SmartNest account.') from error
        subject = options['supabase_user_id']
        if user.supabase_user_id and user.supabase_user_id != subject:
            raise CommandError('This account is already linked to another identity.')
        user.supabase_user_id = subject
        user.identity_verified_at = timezone.now()
        user.set_unusable_password()
        try:
            user.save(update_fields=['supabase_user_id', 'identity_verified_at', 'password'])
        except IntegrityError as error:
            raise CommandError('This Supabase identity is already linked to another account.') from error
        self.stdout.write(self.style.SUCCESS('Supabase identity linked; existing permissions retained.'))
