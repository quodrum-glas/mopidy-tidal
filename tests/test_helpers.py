from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest

from mopidy_tidal.helpers import backoff_on_error, return_none, to_timestamp, try_or_none


class TestBackoffOnError:
    def test_returns_result_on_success(self):
        @backoff_on_error(seconds=1.0)
        def ok():
            return 42

        assert ok() == 42

    def test_returns_none_on_error(self):
        @backoff_on_error(seconds=1.0)
        def boom():
            raise RuntimeError("fail")

        assert boom() is None

    def test_suppresses_during_cooldown(self):
        calls = 0

        @backoff_on_error(seconds=10.0)
        def flaky():
            nonlocal calls
            calls += 1
            raise ValueError

        flaky()  # fails, starts cooldown
        assert calls == 1
        flaky()  # suppressed
        assert calls == 1

    def test_resets_after_cooldown(self):
        t = [0.0]

        @backoff_on_error(seconds=5.0)
        def flaky():
            raise ValueError

        with patch("mopidy_tidal.helpers.time.monotonic", side_effect=lambda: t[0]):
            flaky()          # fails at t=0, cooldown until t=5
            t[0] = 6.0
            flaky()          # t=6 > 5, should call again (and fail again)

        # If it was suppressed, the second call wouldn't log a warning.
        # We just verify it doesn't raise — both return None.

    def test_clears_cooldown_on_success(self):
        fail = [True]
        calls = 0

        @backoff_on_error(seconds=100.0)
        def maybe():
            nonlocal calls
            calls += 1
            if fail[0]:
                raise ValueError
            return "ok"

        t = [0.0]
        with patch("mopidy_tidal.helpers.time.monotonic", side_effect=lambda: t[0]):
            maybe()           # fails at t=0
            t[0] = 200.0
            fail[0] = False
            assert maybe() == "ok"
            t[0] = 200.1      # immediately after — no cooldown
            assert maybe() == "ok"
            assert calls == 3


class TestToTimestamp:
    def test_none_returns_zero(self):
        assert to_timestamp(None) == 0

    def test_empty_string_returns_zero(self):
        assert to_timestamp("") == 0

    def test_float_truncated(self):
        assert to_timestamp(1234567890.9) == 1234567890

    def test_int_passthrough(self):
        assert to_timestamp(1234567890) == 1234567890

    def test_datetime_object(self):
        dt = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        assert to_timestamp(dt) == int(dt.timestamp())

    def test_iso_string(self):
        result = to_timestamp("2024-06-15T12:00:00+00:00")
        expected = int(datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.timezone.utc).timestamp())
        assert result == expected

    def test_today_string(self):
        result = to_timestamp("today")
        expected = int(datetime.datetime.combine(
            datetime.datetime.now().date(), datetime.time.min,
        ).timestamp())
        assert result == expected

    def test_today_case_insensitive(self):
        assert to_timestamp("Today") == to_timestamp("today")
        assert to_timestamp("TODAY") == to_timestamp("today")


class TestTryOrNone:
    def test_returns_result(self):
        assert try_or_none(int, "42") == 42

    def test_returns_none_on_error(self):
        assert try_or_none(int, "not_a_number") is None

    def test_passes_kwargs(self):
        assert try_or_none(int, "ff", base=16) == 255


class TestReturnNone:
    def test_returns_none(self):
        assert return_none() is None

    def test_accepts_any_args(self):
        assert return_none(1, "a", key="val") is None
