from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from users.models import CustomUser

from .models import Advertisement


class AdvertisementPhotoUploadTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            email="ads-admin@example.com",
            password="test-password",
            role="admin",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _image(self):
        image = BytesIO()
        Image.new("RGB", (8, 8), color=(255, 200, 0)).save(image, format="JPEG")
        return SimpleUploadedFile(
            "poster.jpg",
            image.getvalue(),
            content_type="image/jpeg",
        )

    def test_advertisement_creation_accepts_photo_field(self):
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    "/api/ads/create/",
                    {"title": "Affiche", "photo": self._image()},
                    format="multipart",
                )

                self.assertEqual(response.status_code, 201, response.data)
                public_id = response.data["id"]
                advertisement = Advertisement.objects.get(uuid=public_id)
                self.assertTrue(advertisement.image.storage.exists(advertisement.image.name))

                patch = self.client.patch(
                    f"/api/ads/{public_id}/",
                    {"title": "Affiche modifiée"},
                    format="json",
                )
                self.assertEqual(patch.status_code, 200, patch.data)
                self.assertEqual(patch.data["title"], "Affiche modifiée")