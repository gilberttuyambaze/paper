import unittest

from core.auth import google_oidc_configuration_issue
from core.config import settings
from fastapi import HTTPException
from routers.auth import exchange_google_token
from schemas.auth import GoogleTokenExchangeRequest


class GoogleConfigurationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_issuer = settings.oidc_issuer_url
        self.original_client_id = settings.oidc_client_id

    def tearDown(self):
        settings.oidc_issuer_url = self.original_issuer
        settings.oidc_client_id = self.original_client_id

    def test_google_configuration_requires_google_issuer_and_client_id(self):
        settings.oidc_issuer_url = None
        settings.oidc_client_id = None
        issue = google_oidc_configuration_issue()
        self.assertIn("OIDC_CLIENT_ID", issue)
        self.assertIn("OIDC_ISSUER_URL", issue)

    def test_google_configuration_is_complete_without_client_secret(self):
        settings.oidc_issuer_url = "https://accounts.google.com"
        settings.oidc_client_id = "example.apps.googleusercontent.com"
        self.assertIsNone(google_oidc_configuration_issue())

    async def test_google_endpoint_returns_safe_configuration_error_before_database_access(self):
        settings.oidc_issuer_url = None
        settings.oidc_client_id = None
        with self.assertRaises(HTTPException) as raised:
            await exchange_google_token(GoogleTokenExchangeRequest(credential="not-a-real-token"), db=None)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["code"], "google_configuration_incomplete")
        self.assertNotIn("SECRET", raised.exception.detail["message"].upper())
