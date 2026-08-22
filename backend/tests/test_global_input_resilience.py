import unittest

from core.input_normalization import (
    build_storage_key,
    normalize_array_ids,
    normalize_email,
    normalize_filename,
    normalize_isbn,
    normalize_text,
)


class GlobalInputResilienceTests(unittest.TestCase):
    def test_isbn_is_normalized_and_validated(self):
        self.assertEqual(normalize_isbn('978-0133813395 (10-digit: 0133813397)'), '9780133813395')

    def test_long_unicode_filename_is_safe_for_storage(self):
        original = " Anna’s Archive — Electromagnetism — Group Assignment.pdf"
        safe = normalize_filename(original)
        storage_key = build_storage_key('books', 'books', original, 'abc123')
        self.assertTrue(safe.endswith('.pdf'))
        self.assertLessEqual(len(safe), 96 + 4)
        self.assertNotIn('..', safe)
        self.assertNotIn('’', safe)
        self.assertTrue(storage_key.startswith('books/books/abc123-'))
        self.assertLessEqual(len(storage_key), 255)

    def test_array_ids_are_deduplicated(self):
        self.assertEqual(normalize_array_ids(['CSC20233', 'CSC20233', '', None, 'CS20111']), ['CSC20233', 'CS20111'])

    def test_whitespace_and_email_are_normalized(self):
        self.assertEqual(normalize_text('   Gilbert   Tuyambaze   '), 'Gilbert Tuyambaze')
        self.assertEqual(normalize_email(' GILBERT@EXAMPLE.COM '), 'gilbert@example.com')

    def test_traversal_filename_is_rejected_or_isolated(self):
        self.assertTrue(normalize_filename('../../secret.pdf').startswith('secret'))
        self.assertNotIn('../', normalize_filename('../../secret.pdf'))


if __name__ == '__main__':
    unittest.main()
