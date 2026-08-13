import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from routers.auth import get_configured_frontend_url
from schemas.auth import UserResponse


class PasswordResetCORSAndSecurityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.origin = 'https://paperhubur.vercel.app'

    def test_password_reset_request_preflight_has_production_cors_headers(self):
        response = self.client.options(
            '/api/v1/auth/password-reset/request',
            headers={
                'Origin': self.origin,
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'content-type',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('access-control-allow-origin'), self.origin)
        self.assertIn('POST', response.headers.get('access-control-allow-methods', ''))
        self.assertIn('content-type', response.headers.get('access-control-allow-headers', '').lower())

    def test_password_reset_request_uses_generic_response_even_for_unknown_email(self):
        response = self.client.post(
            '/api/v1/auth/password-reset/request',
            json={'email': 'missing-user@example.com'},
            headers={'Origin': self.origin, 'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('access-control-allow-origin'), self.origin)
        self.assertIn('If an account matches that email', response.json()['message'])

    def test_password_reset_confirm_validation_error_still_has_cors_headers(self):
        response = self.client.post(
            '/api/v1/auth/password-reset/confirm',
            json={'token': 'abc', 'password': 'newpass123'},
            headers={'Origin': self.origin, 'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers.get('access-control-allow-origin'), self.origin)
        self.assertIn('token', response.text.lower())

    def test_password_reset_links_use_configured_frontend_not_request_origin(self):
        with patch.dict('os.environ', {'FRONTEND_URL': 'https://paperhubur.vercel.app', 'LOCAL_PATCH': ''}, clear=False):
            self.assertEqual(get_configured_frontend_url(), 'https://paperhubur.vercel.app')

    def test_user_response_exposes_auth_provider_and_password_state(self):
        payload = UserResponse(
            id='user-123',
            email='google-user@example.com',
            name='Google User',
            role='user',
            auth_provider='google',
            has_password=False,
        )
        self.assertEqual(payload.auth_provider, 'google')
        self.assertFalse(payload.has_password)
