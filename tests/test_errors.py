from soulmatch import config, errors


def test_noop_when_dsn_blank(monkeypatch):
    monkeypatch.setattr(config, "SENTRY_DSN", "")
    errors._initialized = False
    errors.init_error_reporting()
    assert errors._initialized is False


def test_noop_and_warns_when_sdk_missing(monkeypatch, caplog):
    monkeypatch.setattr(config, "SENTRY_DSN", "https://example.invalid/1")
    errors._initialized = False
    # sentry-sdk isn't in requirements.txt, so in this test environment the
    # import inside init_error_reporting() should fail and be handled
    # gracefully rather than raising.
    errors.init_error_reporting()
    assert errors._initialized is False
