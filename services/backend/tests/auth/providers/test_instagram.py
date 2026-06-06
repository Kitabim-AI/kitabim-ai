from auth.providers.instagram import InstagramOAuthProvider


def test_instagram_basic():
    """Test basic Instagram provider properties."""
    provider = InstagramOAuthProvider()
    assert provider.name == "instagram"
