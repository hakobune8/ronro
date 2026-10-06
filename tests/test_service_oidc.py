"""Synthetic OIDC proof: no external IdP and no real user claims."""

from __future__ import annotations

import time
import unittest
import json
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from joserfc import jwt
from joserfc.jwk import RSAKey

from prototype.service_errors import ServiceStoreError
from prototype.service_oidc import AuthorizationAttempt, OidcConfiguration, ServiceOidcClient


class ServiceOidcTests(unittest.TestCase):
    def setUp(self):
        self.config = OidcConfiguration(
            issuer="https://idp.example.test", client_id="ronro-dedicated-client",
            public_origin="https://ronro.example.test",
            redirect_uri="https://ronro.example.test/api/service/auth/callback",
            authorization_endpoint="https://idp.example.test/oauth/v2/authorize",
            token_endpoint="https://idp.example.test/oauth/v2/token",
            jwks_uri="https://idp.example.test/oauth/v2/keys",
        )
        self.client = ServiceOidcClient(self.config)
        self.key = RSAKey.generate_key(auto_kid=True)
        self.jwks = {"keys": [self.key.as_dict()]}
        self.attempt = AuthorizationAttempt("synthetic-state", "synthetic-nonce", "synthetic-verifier")

    def _id_token(self, **changes):
        now = int(time.time())
        claims = {
            "iss": self.config.issuer, "sub": "synthetic-subject",
            "aud": self.config.client_id, "exp": now + 600,
            "iat": now, "nonce": self.attempt.nonce,
        }
        claims.update(changes)
        return jwt.encode({"alg": "RS256", "kid": self.key.kid}, claims, self.key)

    def test_authorization_request_uses_code_pkce_nonce_and_fixed_redirect(self):
        url, attempt = self.client.begin_authorization()
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme + "://" + parsed.netloc, self.config.issuer)
        self.assertEqual(query["client_id"], [self.config.client_id])
        self.assertEqual(query["redirect_uri"], [self.config.redirect_uri])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["scope"], ["openid"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["state"], [attempt.state])
        self.assertEqual(query["nonce"], [attempt.nonce])
        self.assertNotIn(attempt.code_verifier, url)
        self.client.require_callback_state(attempt, attempt.state)
        with self.assertRaises(ServiceStoreError):
            self.client.require_callback_state(attempt, "wrong-state")

    def test_configuration_rejects_cross_origin_or_plain_http_endpoints(self):
        values = vars(self.config)
        for replacement in (
            {"authorization_endpoint": "https://attacker.example/authorize"},
            {"token_endpoint": "http://idp.example.test/token"},
            {"jwks_uri": "https://idp.example.test.evil.test/keys"},
            {"redirect_uri": "https://attacker.example/callback"},
            {"issuer": "http://idp.example.test"},
        ):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                OidcConfiguration(**(values | replacement))

    def test_valid_signed_id_token_returns_only_issuer_and_subject(self):
        self.assertEqual(
            vars(self.client.verify_id_token(
                id_token=self._id_token(), jwks=self.jwks, attempt=self.attempt,
            )),
            {"issuer": self.config.issuer, "subject": "synthetic-subject"},
        )

    def test_rejects_wrong_issuer_audience_nonce_expiry_and_signature(self):
        bad_tokens = (
            self._id_token(iss="https://other.example.test"),
            self._id_token(aud="another-client"),
            self._id_token(nonce="wrong-nonce"),
            self._id_token(exp=int(time.time()) - 120),
            self._id_token(iat=int(time.time()) + 600),
        )
        for value in bad_tokens:
            with self.subTest(value=value[:15]), self.assertRaises(ServiceStoreError) as caught:
                self.client.verify_id_token(
                    id_token=value, jwks=self.jwks, attempt=self.attempt,
                )
            self.assertEqual(caught.exception.code, "oidc_token_invalid")
        unrelated_key = RSAKey.generate_key(auto_kid=True)
        with self.assertRaises(ServiceStoreError):
            self.client.verify_id_token(
                id_token=self._id_token(), jwks={"keys": [unrelated_key.as_dict()]},
                attempt=self.attempt,
            )

    def test_jwks_fetch_rejects_redirect_malformed_and_oversize(self):
        class FakeResponse:
            def __init__(self, status, content):
                self.status_code = status
                self.content = content

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield self.content

        valid = json.dumps(self.jwks).encode()
        with patch("prototype.service_oidc.requests.get", return_value=FakeResponse(200, valid)) as fetch:
            self.assertEqual(self.client.fetch_jwks(), self.jwks)
        self.assertEqual(fetch.call_args.args, (self.config.jwks_uri,))
        self.assertIs(fetch.call_args.kwargs["allow_redirects"], False)
        for status, content in ((302, valid), (200, b"{}"), (200, b"x" * 65537)):
            with self.subTest(status=status, length=len(content)), \
                    patch("prototype.service_oidc.requests.get",
                          return_value=FakeResponse(status, content)), \
                    self.assertRaises(ServiceStoreError) as caught:
                self.client.fetch_jwks()
            self.assertEqual(caught.exception.code, "oidc_jwks_unavailable")

    def test_code_exchange_requires_id_token_and_server_side_verifier(self):
        with patch("prototype.service_oidc.OAuth2Session.fetch_token") as exchange:
            exchange.return_value = {"id_token": self._id_token(), "access_token": "synthetic"}
            token = self.client.exchange_code(code="synthetic-code", attempt=self.attempt)
        self.assertIn("id_token", token)
        self.assertEqual(exchange.call_args.kwargs["code_verifier"], self.attempt.code_verifier)
        with patch("prototype.service_oidc.OAuth2Session.fetch_token", return_value={"access_token": "x"}):
            with self.assertRaises(ServiceStoreError):
                self.client.exchange_code(code="synthetic-code", attempt=self.attempt)

    def test_completion_checks_state_before_token_exchange_and_signature_after(self):
        with patch("prototype.service_oidc.OAuth2Session.fetch_token") as exchange, \
                patch.object(self.client, "fetch_jwks", return_value=self.jwks):
            exchange.return_value = {"id_token": self._id_token()}
            with self.assertRaises(ServiceStoreError):
                self.client.complete_authorization(
                    code="synthetic-code", received_state="wrong-state",
                    attempt=self.attempt,
                )
            exchange.assert_not_called()
            self.assertEqual(
                vars(self.client.complete_authorization(
                    code="synthetic-code", received_state=self.attempt.state,
                    attempt=self.attempt,
                )),
                {"issuer": self.config.issuer, "subject": "synthetic-subject"},
            )
