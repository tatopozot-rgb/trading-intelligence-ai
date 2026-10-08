"""Offline tests for the one-shot Binance permissions probe."""

from __future__ import annotations

import hashlib
import hmac
import json
import unittest
from unittest.mock import patch
from urllib import parse

from readonly_permissions import (
    API_BASE,
    NoRedirect,
    PERMISSIONS_PATH,
    PERMISSION_FLAGS,
    check_permissions,
    summarize_permissions,
)


BASE_FLAGS = {name: False for name in PERMISSION_FLAGS}
BASE_FLAGS["enableReading"] = True


class FakeResponse:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        return self.payload[:size]


class ReadOnlyProbeTests(unittest.TestCase):
    def test_single_signed_get_and_minimal_output(self) -> None:
        calls = []

        def opener(req, *, timeout):
            calls.append((req, timeout))
            return FakeResponse({**BASE_FLAGS, "enableFixReadOnly": True, "createTime": 123456})

        result = check_permissions("synthetic-key", "synthetic-secret", opener=opener, timestamp_ms=123456789)
        self.assertEqual(result, (True, ()))
        self.assertEqual(len(calls), 1)
        req, timeout = calls[0]
        self.assertEqual(timeout, 10)
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.get_header("X-mbx-apikey"), "synthetic-key")
        self.assertTrue(req.full_url.startswith(f"{API_BASE}{PERMISSIONS_PATH}?"))
        query = parse.parse_qs(parse.urlsplit(req.full_url).query)
        expected_payload = "timestamp=123456789&recvWindow=5000"
        expected_signature = hmac.new(b"synthetic-secret", expected_payload.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(query["signature"], [expected_signature])

    def test_extra_permissions_are_not_misreported_as_read_only(self) -> None:
        for name in ("enableSpotAndMarginTrading", "enableWithdrawals", "enableInternalTransfer"):
            with self.subTest(name=name):
                result = summarize_permissions({**BASE_FLAGS, name: True})
                self.assertFalse(result[0])
                self.assertIn(name, result[1])

    def test_missing_required_flag_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            summarize_permissions({name: value for name, value in BASE_FLAGS.items() if name != "enableFutures"})

    def test_non_boolean_required_flag_fails_closed(self) -> None:
        for name, wrong in (("enableReading", "true"), ("enableFutures", "true"), ("enableInternalTransfer", 1)):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    summarize_permissions({**BASE_FLAGS, name: wrong})

    def test_unknown_permission_field_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            summarize_permissions({**BASE_FLAGS, "enableNewTradingFeature": True})

    def test_default_opener_rejects_redirects(self) -> None:
        handler = NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "found", {}, "https://other.example"))

        class FakeOpener:
            def open(self, req, *, timeout):
                return FakeResponse(BASE_FLAGS)

        with patch("readonly_permissions.request.build_opener", return_value=FakeOpener()) as builder:
            self.assertEqual(
                check_permissions("synthetic-key", "synthetic-secret", timestamp_ms=123456789),
                (True, ()),
            )
            self.assertIsInstance(builder.call_args.args[0], NoRedirect)


if __name__ == "__main__":
    unittest.main(verbosity=2)
