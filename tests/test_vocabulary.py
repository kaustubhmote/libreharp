import unittest

from libreharp.vocabulary import is_word_finding, parse_words


class VocabularyTests(unittest.TestCase):
    def test_only_spelling_and_splitting_offer_word_exceptions(self):
        self.assertTrue(is_word_finding({"rule": "SpellCheck"}))
        self.assertTrue(is_word_finding({"rule": "SplitWords"}))
        self.assertFalse(is_word_finding({"rule": "AnA"}))
        self.assertFalse(is_word_finding({"rule": "LibreHarp.Term.example"}))
        self.assertFalse(is_word_finding(None))

    def test_bulk_words_keep_exact_case_and_merge_duplicates(self):
        self.assertEqual(
            parse_words("\ufeffhomonuclear\r\n radiofrequency \n\nHomonuclear\nhomonuclear\nβsheet\n"),
            ["Homonuclear", "homonuclear", "radiofrequency", "βsheet"],
        )
        self.assertEqual(parse_words(" \n\t"), [])

    def test_invalid_word_lists_are_rejected_before_saving(self):
        for text in ("homonuclear\nradio frequency", "term/FLAGS", "x" * 2_000_001, "λ" * 1_000_001):
            with self.subTest(text=text[:40]), self.assertRaises(ValueError):
                parse_words(text)
