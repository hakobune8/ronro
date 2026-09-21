import unittest

from prototype.stt import OpenAICompatibleTranscriber
from prototype.stt_terminology_run import TERMINOLOGY_KEYWORDS, technical_term_accuracy


class TerminologySTTAdapterTests(unittest.TestCase):
    def test_gpt_transcribe_uses_json_response_format(self):
        transcriber = OpenAICompatibleTranscriber(
            endpoint="https://example.test/v1",
            api_key="test-key",
            model="gpt-transcribe",
            context_prompt="技術会議",
            keywords=TERMINOLOGY_KEYWORDS,
        )
        self.assertEqual(transcriber.response_format, "json")

    def test_terminology_accuracy_accepts_japanese_rendering(self):
        dataset = {
            "utterances": [
                {"sequence": 1, "text": "Discussion MapとMVPを確認します。"},
                {"sequence": 2, "text": "Current Topicを表示します。"},
            ]
        }
        aligned = [
            {"reference_sequence": 1, "reference_text": dataset["utterances"][0]["text"], "stt_text": "ディスカッションマップとMVPを確認します。"},
            {"reference_sequence": 2, "reference_text": dataset["utterances"][1]["text"], "stt_text": "CurrentとTOPICを表示します。"},
        ]
        result = technical_term_accuracy(dataset, aligned)
        self.assertEqual(result["terms"]["Discussion Map"]["correct"], 1)
        self.assertEqual(result["terms"]["MVP"]["correct"], 1)
        self.assertEqual(result["terms"]["Current Topic"]["substitution"], 1)


if __name__ == "__main__":
    unittest.main()
