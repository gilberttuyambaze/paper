import unittest
from datetime import datetime, timezone

from services.mailer import _build_account_created_message, _build_password_reset_message


class BrandedMailerTests(unittest.TestCase):
    def test_reset_email_has_plain_text_and_html_alternative(self):
        message = _build_password_reset_message(
            'student@example.com',
            'https://paperhubur.vercel.app/reset-password?token=test-token',
            datetime.now(timezone.utc),
        )
        self.assertTrue(message.is_multipart())
        self.assertIn('Reset your UR Academic Resource Hub password', message['Subject'])
        self.assertIn('text/plain', [part.get_content_type() for part in message.walk()])
        self.assertIn('text/html', [part.get_content_type() for part in message.walk()])

    def test_account_created_email_has_plain_text_and_html_alternative(self):
        message = _build_account_created_message(
            'student@example.com',
            'Student',
            'normal',
            'https://paperhubur.vercel.app/login',
        )
        self.assertTrue(message.is_multipart())
        self.assertIn('Welcome to UR Academic Resource Hub', message['Subject'])
        self.assertIn('text/html', [part.get_content_type() for part in message.walk()])
