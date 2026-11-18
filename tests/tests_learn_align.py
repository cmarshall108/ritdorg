"""Word alignment for the learn-a-language reader."""

import unittest

from ritdorg.learn_align import align_verse, guess_lang, text_dir, verse_words


class LearnAlignTestCase(unittest.TestCase):
    def test_equal_length_keeps_order_and_sentence_neighbors(self):
        aligned = align_verse(
            "For God so loved the world",
            "Mert úgy szerette Isten a világot",
        )
        self.assertEqual([item["word"] for item in aligned], ["For", "God", "so", "loved", "the", "world"])
        self.assertEqual([item["gloss"] for item in aligned], ["Mert", "úgy", "szerette", "Isten", "a", "világot"])
        self.assertFalse(any(item["shared"] for item in aligned))
        loved = aligned[3]
        self.assertEqual(loved["phrase"], "szerette Isten a")
        self.assertEqual(loved["target_span"], [3, 3])

    def test_longer_target_keeps_every_word_in_a_phrase(self):
        aligned = align_verse("God loved the world", "Dios amó tanto al mundo entero")
        glosses = [word for item in aligned for word in item["gloss_words"]]
        self.assertEqual(glosses, ["Dios", "amó", "tanto", "al", "mundo", "entero"])
        self.assertTrue(any(len(item["gloss_words"]) > 1 for item in aligned))
        self.assertTrue(all(item["gloss"] for item in aligned))

    def test_shorter_target_still_glosses_every_native_word_without_dropping_context(self):
        aligned = align_verse("In the beginning God created the heavens", "Al principio creó Dios")
        self.assertEqual(len(aligned), 7)
        self.assertTrue(all(item["gloss"] for item in aligned))
        covered = []
        for item in aligned:
            for word in item["gloss_words"]:
                if word not in covered:
                    covered.append(word)
        self.assertEqual(covered, ["Al", "principio", "creó", "Dios"])
        self.assertTrue(any(item["shared"] for item in aligned))
        spans = [item["target_span"][0] for item in aligned]
        self.assertEqual(spans, sorted(spans))

    def test_punctuation_numbers_and_maqaf_follow_the_reader_tokens(self):
        self.assertEqual(verse_words('God\'s world, 40 days!'), ["God's", "world", "40", "days"])
        self.assertEqual(verse_words("בֶּן־הָאֱלֹהִים"), ["בֶּן", "הָאֱלֹהִים"])
        aligned = align_verse("בֶּן־הָאֱלֹהִים", "Son of God")
        self.assertEqual([item["word"] for item in aligned], ["בֶּן", "הָאֱלֹהִים"])
        self.assertEqual(text_dir("בֶּן"), "rtl")
        self.assertEqual(text_dir("Son of God"), "ltr")

    def test_empty_and_unknown_language_do_not_invent_words(self):
        self.assertEqual(align_verse("", "Amó"), [])
        blank = align_verse("God loved", "")
        self.assertEqual([item["gloss"] for item in blank], ["", ""])
        self.assertEqual(guess_lang("Hungarian-Revised"), "hu")
        self.assertEqual(guess_lang("Arabic2018"), "ar")
        self.assertEqual(guess_lang("Aramaic"), "arc")
        self.assertEqual(guess_lang("NIV"), "en")
        self.assertEqual(guess_lang("AdilabadGondi"), "")
