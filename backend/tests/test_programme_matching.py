import unittest

from services import programme_discovery as pd


class TestProgrammeMatching(unittest.TestCase):
    def test_similarity_high_for_equivalent_names(self):
        a = "information systems and technology"
        b = "information systems & technology"
        sim = pd._similarity(a, b)
        self.assertGreater(sim, 0.7)

    def test_context_score(self):
        candidate = {"campus_id": "c1", "college_id": "col1", "school_id": "s1"}
        score = pd._context_score(candidate, campus_id="c1", college_id="col1", school_id="s1")
        self.assertAlmostEqual(score, 0.15 + 0.10 + 0.05)

    def test_total_scoring_threshold(self):
        # identical names and matching context should yield a high recommendation score
        normalized = "information systems technology"
        candidate = {"normalized": normalized, "campus_id": "c1", "college_id": "col1", "school_id": "s1"}
        sim = pd._similarity(normalized, candidate["normalized"])
        context = pd._context_score(candidate, campus_id="c1", college_id="col1", school_id="s1")
        total = round(100 * ((0.70 * sim) + context))
        self.assertGreaterEqual(total, 90)


if __name__ == "__main__":
    unittest.main()
