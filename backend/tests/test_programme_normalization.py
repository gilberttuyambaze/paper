import unittest

from core.normalization import normalize_programme_text, tokenize_normalized


class TestProgrammeNormalization(unittest.TestCase):
    def test_basic_normalization(self):
        variants = [
            "B.Sc Information Systems & Technology",
            "BSc Information Systems and Technology",
            "bachelor of science in information systems & technology",
            "Information Systems and Technology",
        ]

        normalized = [normalize_programme_text(v) for v in variants]
        # all normalized forms should be identical
        self.assertTrue(len(set(normalized)) == 1)

    def test_tokenization(self):
        s = "B.Sc Information Systems & Technology"
        tokens = tokenize_normalized(s)
        self.assertIn("information", tokens)
        self.assertIn("systems", tokens)
        self.assertIn("and", tokens)
        self.assertIn("technology", tokens)

    def test_empty_and_none(self):
        self.assertEqual(normalize_programme_text(None), "")
        self.assertEqual(tokenize_normalized("") , [])


if __name__ == "__main__":
    unittest.main()
