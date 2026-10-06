import unittest

from prototype.service_crypto import (
    InMemoryTestKeyRegistry,
    ServiceCryptoError,
    SessionEnvelopeCodec,
)


class ServiceCryptoTests(unittest.TestCase):
    def setUp(self):
        self.registry = InMemoryTestKeyRegistry()
        self.registry.create_key("session-a")
        self.registry.create_key("session-b")
        self.codec = SessionEnvelopeCodec(self.registry)

    def test_round_trip_and_distinct_nonces(self):
        value = {"text": "会議の内容", "sequence": 1}
        first = self.codec.encrypt_json("session-a", "evidence", "e1", value)
        second = self.codec.encrypt_json("session-a", "evidence", "e1", value)
        self.assertNotEqual(first, second)
        self.assertNotIn("会議の内容".encode(), first)
        self.assertEqual(self.codec.decrypt_json("session-a", "evidence", "e1", first), value)

    def test_session_kind_and_identity_are_authenticated(self):
        blob = self.codec.encrypt_json("session-a", "evidence", "e1", {"text": "秘密"})
        for session_id, kind, record_id in (
            ("session-b", "evidence", "e1"),
            ("session-a", "event", "e1"),
            ("session-a", "evidence", "e2"),
        ):
            with self.assertRaisesRegex(ServiceCryptoError, "decrypt_failed"):
                self.codec.decrypt_json(session_id, kind, record_id, blob)

    def test_key_deletion_makes_ciphertext_unreadable(self):
        blob = self.codec.encrypt_json("session-a", "event", "1", {"label": "案"})
        self.registry.delete_key("session-a")
        with self.assertRaisesRegex(ServiceCryptoError, "key_unavailable"):
            self.codec.decrypt_json("session-a", "event", "1", blob)

    def test_provider_identity_is_blinded_per_session(self):
        first = self.codec.blind_provider_item_id("session-a", "item-123")
        self.assertEqual(first, self.codec.blind_provider_item_id("session-a", "item-123"))
        self.assertNotEqual(first, self.codec.blind_provider_item_id("session-b", "item-123"))
        self.assertNotIn(b"item-123", first)


if __name__ == "__main__":
    unittest.main()
