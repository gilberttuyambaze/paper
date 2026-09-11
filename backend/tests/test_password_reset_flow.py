import unittest
from unittest.mock import patch
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from main import app
from routers.auth import get_configured_frontend_url
from schemas.auth import UserResponse
from services.auth import _hash_reset_token
from services.communications import dispatch_communication


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

    def test_password_reset_request_never_returns_debug_reset_url(self):
        fake_user = SimpleNamespace(id="user-1", email="person@example.com")
        fake_expiry = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        with patch("routers.auth.AuthService.create_password_reset_token", return_value=(fake_user, "raw-secret-token", fake_expiry)), \
             patch("routers.auth.queue_password_reset_event", return_value=None):
            response = self.client.post(
                "/api/v1/auth/password-reset/request",
                json={"email": "person@example.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"message": "If an account matches that email address, we have sent instructions to reset your password. Please check your inbox and spam folder."},
        )
        self.assertNotIn("raw-secret-token", response.text)
        self.assertNotIn("debug_reset_url", response.text)

    def test_password_reset_request_queues_delivery_at_api_boundary(self):
        fake_user = SimpleNamespace(id="user-1", email="person@example.com")
        fake_expiry = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        with patch("routers.auth.AuthService.create_password_reset_token", return_value=(fake_user, "raw-secret-token", fake_expiry)), \
             patch("routers.auth.queue_password_reset_event", new=__import__("unittest").mock.AsyncMock()) as queue:
            response = self.client.post("/api/v1/auth/password-reset/request", json={"email": "person@example.com"})

        self.assertEqual(response.status_code, 200)
        queue.assert_awaited_once()
        self.assertNotIn("raw-secret-token", response.text)

    def test_reset_token_hash_is_not_raw_token(self):
        raw_token = "secure-random-reset-token"
        self.assertNotEqual(_hash_reset_token(raw_token), raw_token)
        self.assertEqual(len(_hash_reset_token(raw_token)), 64)

    def test_communication_provider_failure_is_recorded_without_raising(self):
        class FakeDb:
            def __init__(self):
                self.events = []
                self.committed = False

            def add(self, event):
                self.events.append(event)

            async def commit(self):
                self.committed = True

        async def fail(*args, **kwargs):
            raise RuntimeError("provider unavailable")

        async def run():
            db = FakeDb()
            with patch("services.communications.send_transactional_email", side_effect=fail):
                sent = await dispatch_communication(
                    db,
                    event_type="PASSWORD_CHANGED",
                    user_id="user-1",
                    recipient="person@example.com",
                    subject="Password changed",
                    text="Your password changed.",
                    html="<p>Your password changed.</p>",
                )
            return sent, db

        sent, db = __import__("asyncio").run(run())
        self.assertFalse(sent)
        self.assertTrue(db.committed)
        self.assertEqual(db.events[0].status, "failed")
        self.assertEqual(db.events[0].error_category, "provider_failure")
