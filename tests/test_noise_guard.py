import unittest

from prototype.noise_guard import classify_utterance


class NoiseGuardTests(unittest.TestCase):
    def test_skips_exact_backchannel_only(self):
        self.assertEqual(classify_utterance("そうですね。"), {"decision": "skip", "reason": "BACKCHANNEL_ONLY"})

    def test_skips_low_content_closing(self):
        self.assertEqual(classify_utterance("お疲れさまでした。"), {"decision": "skip", "reason": "VERY_LOW_CONTENT"})

    def test_keeps_semantic_short_actions_and_decisions(self):
        for text in ("やります", "外します", "それで進めます", "今回はなしで", "金曜までです", "山田さんで", "戻りましょう", "保留で"):
            self.assertEqual(classify_utterance(text)["decision"], "pass", text)

    def test_keeps_agreement_with_semantic_content(self):
        self.assertEqual(classify_utterance("はい、それで進めましょう。")["decision"], "pass")


if __name__ == "__main__":
    unittest.main()
