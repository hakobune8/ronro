"""Pure browser-boundary checks; these do not simulate OIDC login."""

from __future__ import annotations

import unittest

from prototype.service_browser_security import COOKIE_NAME, ServiceBrowserSecurity
from prototype.service_errors import ServiceStoreError


class ServiceBrowserSecurityTests(unittest.TestCase):
    def setUp(self):
        self.policy = ServiceBrowserSecurity("https://ronro.example.test")

    def test_exact_origin_required_for_mutations_and_websocket(self):
        self.policy.require_same_origin("https://ronro.example.test")
        for value in (
            None, "null", "http://ronro.example.test",
            "https://evil.ronro.example.test", "https://ronro.example.test.evil.test",
            "https://ronro.example.test:443", "https://ronro.example.test/",
            "https://other.example.test", "https://ronro.example.test@evil.test",
        ):
            with self.subTest(value=value), self.assertRaises(ServiceStoreError) as caught:
                self.policy.require_same_origin(value)
            self.assertEqual(caught.exception.code, "origin_rejected")

    def test_canonical_https_origin_configuration(self):
        for value in ("http://ronro.example.test", "https://ronro.example.test/",
                      "https://ronro.example.test/a", "https://ronro.example.test?q=1",
                      "https://name:pass@ronro.example.test", "https://RONRO.example.test",
                      "https://ronro.example.test:invalid", "https://[invalid", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ServiceBrowserSecurity(value)

    def test_csrf_is_session_bound_and_not_accepted_as_cookie_alone(self):
        first, digest = self.policy.new_csrf_secret()
        second, _ = self.policy.new_csrf_secret()
        self.policy.require_mutation(origin=self.policy.public_origin,
                                     csrf_token=first, session_csrf_digest=digest)
        for value in (None, "", second, first + "x", "A" * 43):
            with self.subTest(value=value), self.assertRaises(ServiceStoreError) as caught:
                self.policy.require_mutation(origin=self.policy.public_origin,
                                             csrf_token=value, session_csrf_digest=digest)
            self.assertEqual(caught.exception.code, "csrf_rejected")
        with self.assertRaises(ServiceStoreError) as caught:
            self.policy.require_mutation(origin="https://other.example.test",
                                         csrf_token=first, session_csrf_digest=digest)
        self.assertEqual(caught.exception.code, "origin_rejected")

    def test_cookie_is_secure_host_only_and_does_not_accept_injection(self):
        header = self.policy.session_cookie("A" * 43, max_age_seconds=1800)
        self.assertTrue(header.startswith(f"{COOKIE_NAME}="))
        for part in ("Path=/", "Max-Age=1800", "Secure", "HttpOnly", "SameSite=Lax"):
            self.assertIn(part, header)
        self.assertNotIn("Domain=", header)
        for value in ("short", "A" * 43 + "; Domain=evil.test", "A" * 43 + "\r\nSet-Cookie:",
                      "A" * 42 + "."):
            with self.subTest(value=value), self.assertRaises(ServiceStoreError):
                self.policy.session_cookie(value, max_age_seconds=1800)
        for lifetime in (0, -1, 86401, True):
            with self.subTest(lifetime=lifetime), self.assertRaises(ServiceStoreError):
                self.policy.session_cookie("A" * 43, max_age_seconds=lifetime)
