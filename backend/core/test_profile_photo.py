from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import User


class ProfilePhotoTests(TestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.user = User.objects.create_user(
            username='photo-user', email='photo@example.com',
            password='Photo-password-1', role='manager', phone='0712345678',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def photo(self):
        return SimpleUploadedFile('profile.png', b'\x89PNG\r\n\x1a\n' + b'\x00' * 8, content_type='image/png')

    def test_upload_and_remove_photo_preserves_account_and_deletes_file(self):
        upload = self.client.patch('/api/auth/me/', {'avatar_image': self.photo()}, format='multipart')
        self.assertEqual(upload.status_code, 200, upload.data)
        self.assertTrue(upload.data['has_avatar'])
        self.user.refresh_from_db()
        photo_name = self.user.avatar_image.name
        storage = self.user.avatar_image.storage
        self.assertTrue(storage.exists(photo_name))
        removed = self.client.patch('/api/auth/me/', {'remove_avatar': True}, format='json')
        self.assertEqual(removed.status_code, 200, removed.data)
        self.assertFalse(removed.data['has_avatar'])
        self.assertEqual(removed.data['username'], 'photo-user')
        self.assertEqual(removed.data['phone'], '0712345678')
        self.assertFalse(storage.exists(photo_name))
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar_image)
        self.assertEqual(self.client.get(f'/api/users/{self.user.pk}/avatar/').status_code, 404)
        again = self.client.patch('/api/auth/me/', {'remove_avatar': True}, format='json')
        self.assertEqual(again.status_code, 200)
        reupload = self.client.patch('/api/auth/me/', {'avatar_image': self.photo()}, format='multipart')
        self.assertEqual(reupload.status_code, 200, reupload.data)
        self.assertTrue(reupload.data['has_avatar'])

    def test_upload_and_remove_together_is_rejected(self):
        response = self.client.patch('/api/auth/me/', {'avatar_image': self.photo(), 'remove_avatar': True}, format='multipart')
        self.assertEqual(response.status_code, 400)
