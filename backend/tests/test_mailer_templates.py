import asyncio
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import httpx

from services.mailer import (
    _build_account_created_message,
    _build_account_invitation_message,
    _build_inactive_user_message,
    _build_new_login_message,
    _build_password_changed_message,
    _build_password_reset_message,
    _build_system_heartbeat_message,
)


class BrandedMailerTests(unittest.TestCase):
    def test_reset_email_has_plain_text_and_html_alternative(self):
        message = _build_password_reset_message(
            'student@example.com',
            'https://paperhubur.vercel.app/reset-password?token=test-token',
            datetime.now(timezone.utc),
        )
        self.assertEqual(message['subject'], 'Reset your PaperHub password')
        self.assertIn('test-token', message['text'])
        self.assertIn('Choose a new password', message['html'])
        self.assertIn('Academic Platform', message['html'])
        self.assertIn('UR Academic Resource Hub', message['html'])

    def test_account_created_email_has_plain_text_and_html_alternative(self):
        message = _build_account_created_message(
            'student@example.com',
            'Student',
            'normal',
            'https://paperhubur.vercel.app/login',
        )
        self.assertEqual(message['subject'], 'Welcome to PaperHub')
        self.assertIn('student@example.com', message['text'])
        self.assertIn('Sign in to Paper Hub', message['html'])
        self.assertIn('Past Papers', message['html'])
        self.assertIn('AI Study Companion', message['html'])

    def test_password_changed_email_has_details(self):
        message = _build_password_changed_message(
            'student@example.com',
            'Student',
            datetime(2026, 9, 11, 14, 0, tzinfo=timezone.utc),
        )
        self.assertIn('password was changed', message['subject'])
        self.assertIn('2026-09-11 14:00 UTC', message['text'])
        self.assertIn('Password Changed Successfully', message['html'])
        self.assertIn('Security Alert', message['html'])

    def test_new_login_email_has_details(self):
        message = _build_new_login_message(
            'student@example.com',
            'Student',
            datetime(2026, 9, 11, 14, 0, tzinfo=timezone.utc),
        )
        self.assertIn('sign-in', message['subject'].lower())
        self.assertIn('2026-09-11 14:00 UTC', message['text'])
        self.assertIn('New Sign-in Detected', message['html'])

    def test_inactive_user_email_has_resource_highlights(self):
        message = _build_inactive_user_message(
            'student@example.com',
            'Student',
            'https://paperhubur.vercel.app/login',
        )
        self.assertEqual(message['subject'], 'We miss you at PaperHub — Discover New Academic Resources')
        self.assertIn('Fresh past exam papers', message['text'])
        self.assertIn('We Miss You on PaperHub!', message['html'])
        self.assertIn('Explore Latest Resources', message['html'])
        self.assertIn('Textbooks &amp; Module Handouts', message['html'])

    def test_system_heartbeat_email_has_telemetry_table(self):
        health_data = {
            'status': 'healthy',
            'duration_ms': 12,
            'mode': 'Scheduled Check',
            'total_attempts': 42,
            'total_successes': 42,
            'next_scheduled': '2026-09-12 08:00 UTC',
        }
        message = _build_system_heartbeat_message('admin@example.com', 'Super Admin', health_data)
        self.assertIn('Heartbeat: HEALTHY', message['subject'])
        self.assertIn('12 ms', message['text'])
        self.assertIn('42 / 42', message['html'])
        self.assertIn('Scheduled Check', message['html'])
        self.assertIn('System Health &amp; Database Heartbeat Report', message['html'])

    def test_account_invitation_email_has_branding(self):
        message = _build_account_invitation_message('colleague@example.com', 'Dr. Smith', 'https://paperhubur.vercel.app/invite/123')
        self.assertEqual(message['subject'], 'You are invited to PaperHub')
        self.assertIn('Dr. Smith', message['text'])
        self.assertIn('Accept Invitation &amp; Sign Up', message['html'])

    def test_brevo_success_sends_expected_payload(self):
        class Response:
            status_code = 201

            @staticmethod
            def json():
                return {'messageId': '<brevo-id>'}

        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def post(self, url, headers, json):
                self.payload = (url, headers, json)
                return Response()

        async def run():
            with patch.dict(os.environ, {'BREVO_API_KEY': 'test-key', 'SMTP_FROM_EMAIL': 'sender@example.com', 'SMTP_FROM_NAME': 'PaperHub', 'SUPPORT_EMAIL': 'support@example.com'}), patch('services.mailer.httpx.AsyncClient', return_value=Client()) as client:
                result = await __import__('services.mailer', fromlist=['send_transactional_email']).send_transactional_email('to@example.com', 'Subject', 'Plain', '<p>HTML</p>')
                return result, client.return_value.payload

        result, payload = asyncio.run(run())
        self.assertTrue(result)
        self.assertEqual(payload[0], 'https://api.brevo.com/v3/smtp/email')
        self.assertEqual(payload[1]['api-key'], 'test-key')
        self.assertEqual(payload[2]['sender']['email'], 'sender@example.com')

    def test_brevo_timeout_returns_failure_without_raising(self):
        mailer = __import__('services.mailer', fromlist=['send_transactional_email'])

        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def post(self, *args, **kwargs): raise httpx.ReadTimeout('timed out')

        async def run():
            with patch.dict(os.environ, {'BREVO_API_KEY': 'test-key', 'SMTP_FROM_EMAIL': 'sender@example.com'}), patch('services.mailer.httpx.AsyncClient', return_value=Client()):
                return await mailer.send_transactional_email('to@example.com', 'Subject', 'Plain', '<p>HTML</p>')

        self.assertFalse(asyncio.run(run()))

    def test_brevo_http_and_malformed_responses_return_failure(self):
        mailer = __import__('services.mailer', fromlist=['send_transactional_email'])

        class Response:
            def __init__(self, status_code, payload):
                self.status_code = status_code
                self.payload = payload

            def json(self):
                return self.payload

        class Client:
            def __init__(self, response): self.response = response
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def post(self, *args, **kwargs): return self.response

        async def run(response):
            with patch.dict(os.environ, {'BREVO_API_KEY': 'test-key', 'SMTP_FROM_EMAIL': 'sender@example.com'}), patch('services.mailer.httpx.AsyncClient', return_value=Client(response)):
                return await mailer.send_transactional_email('to@example.com', 'Subject', 'Plain', '<p>HTML</p>')

        self.assertFalse(asyncio.run(run(Response(400, {'message': 'bad request'}))))
        self.assertFalse(asyncio.run(run(Response(500, {'message': 'server error'}))))
        self.assertFalse(asyncio.run(run(Response(201, {'unexpected': 'shape'}))))
