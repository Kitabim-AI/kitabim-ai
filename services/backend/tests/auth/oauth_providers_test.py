"""Unit tests for OAuth provider helpers and placeholder email predicates."""

from __future__ import annotations

import pytest

from auth.oauth_providers import PLACEHOLDER_EMAIL_DOMAINS, is_placeholder_email


def test_placeholder_domains_constant():
    assert PLACEHOLDER_EMAIL_DOMAINS == frozenset(
        {"facebook.placeholder", "twitter.placeholder", "instagram.placeholder"}
    )


@pytest.mark.parametrize(
    "email",
    [
        "12345@facebook.placeholder",
        "  98765@TWITTER.PLACEHOLDER  ",
        "abc@instagram.placeholder",
    ],
)
def test_is_placeholder_email_without_provider_matches_all_placeholder_domains(
    email: str,
):
    assert is_placeholder_email(email) is True


@pytest.mark.parametrize(
    "email",
    [
        "",
        "facebook.placeholder",
        "@facebook.placeholder",
        "a@b@facebook.placeholder",
        "user@gmail.com",
        "user@google.placeholder",
        "user@sub.facebook.placeholder",
    ],
)
def test_is_placeholder_email_rejects_non_placeholder_or_malformed_inputs(email: str):
    assert is_placeholder_email(email) is False
    assert is_placeholder_email(email, provider="facebook") is False


def test_is_placeholder_email_enforces_exact_provider_match():
    assert (
        is_placeholder_email("12345@facebook.placeholder", provider="facebook") is True
    )
    assert (
        is_placeholder_email("12345@facebook.placeholder", provider="  FACEBOOK ")
        is True
    )
    assert (
        is_placeholder_email("12345@twitter.placeholder", provider="facebook") is False
    )
    assert (
        is_placeholder_email("12345@facebook.placeholder", provider="google") is False
    )
