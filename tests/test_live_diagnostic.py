import json
import unittest
from prototype.live_diagnostic import DiagnosticRecorder, capture_diagnostics, diagnostic


class DiagnosticTests(unittest.TestCase):
    def test_default_is_disabled_and_context_is_scoped(self):
        r=DiagnosticRecorder()
        diagnostic('outside')
        with capture_diagnostics(r):diagnostic('inside')
        diagnostic('outside')
        self.assertEqual([x['kind'] for x in r.rows],['inside'])

    def test_raw_event_allowlist_excludes_content_and_credentials(self):
        r=DiagnosticRecorder()
        with capture_diagnostics(r):
            diagnostic('provider_receive',raw={'type':'conversation.item.input_audio_transcription.delta','item_id':'test-A','event_id':'test-e1','delta':'PRIVATE PHRASE','audio':'RAW PCM','api_key':'SECRET'})
            diagnostic('provider_receive',raw={'type':'conversation.item.input_audio_transcription.completed','item_id':'test-A','event_id':'test-e2','transcript':'PRIVATE PHRASE'})
        serialized=json.dumps(r.rows)
        for forbidden in ('PRIVATE PHRASE','RAW PCM','SECRET'):self.assertNotIn(forbidden,serialized)
        self.assertEqual(r.rows[0]['event']['delta_length'],14)
        self.assertFalse(r.rows[1]['event']['transcript_empty'])

    def test_duplicate_and_out_of_order_are_observations_only(self):
        r=DiagnosticRecorder()
        with capture_diagnostics(r):
            for item in ('test-A','test-B'):
                diagnostic('provider_receive',raw={'type':'input_audio_buffer.committed','item_id':item})
            for item in ('test-B','test-A','test-A'):
                diagnostic('provider_receive',raw={'type':'conversation.item.input_audio_transcription.completed','item_id':item,'transcript':''})
        self.assertTrue(r.rows[-2]['event']['out_of_order_completion'])
        self.assertTrue(r.rows[-1]['event']['duplicate_completion'])
        self.assertEqual(len(r.completed),2)

    def test_sink_failure_does_not_raise_into_product(self):
        class Broken:
            dropped=0
            def record(self,*args,**kwargs):raise ValueError('diagnostic only')
        r=Broken()
        with capture_diagnostics(r):diagnostic('test')
        self.assertEqual(r.dropped,1)

    def test_old_item_clear_is_unknown_without_item_end(self):
        r=DiagnosticRecorder()
        with capture_diagnostics(r):diagnostic('buffer_clear_before',item_id='test-A')
        self.assertIsNone(r.rows[0]['older_item_clears_newer_audio'])
