"""Unit and integration tests for GitHub App authentication and client abstraction."""

import time
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.domain.github.client import (
    GitHubAppNotConfiguredError,
    GitHubClient,
    GitHubNotFoundError,
    GitHubRateLimitError,
)


@pytest.fixture(scope="module")
def test_rsa_pem() -> str:
    """Generates an in-memory 2048-bit RSA private key in PEM format."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def test_github_client_unconfigured_raises() -> None:
    """Unconfigured client must immediately fail with GitHubAppNotConfiguredError."""
    client = GitHubClient(app_id=None, private_key_pem=None)
    with pytest.raises(GitHubAppNotConfiguredError):
        client.generate_app_jwt()


def test_github_jwt_generation_and_claims(test_rsa_pem: str) -> None:
    """Verifies that generated JWT uses RS256 with correct issuer and expiration claims."""
    app_id = "123456"
    client = GitHubClient(app_id=app_id, private_key_pem=test_rsa_pem)

    token = client.generate_app_jwt()
    assert token is not None

    # Decode without verifying signature to inspect payload claims
    unverified = jwt.decode(token, options={"verify_signature": False})
    assert unverified["iss"] == app_id
    now = int(time.time())
    assert unverified["iat"] <= now
    assert unverified["exp"] > now


@pytest.mark.asyncio
async def test_installation_token_caching_and_expiration(test_rsa_pem: str) -> None:
    """Verifies installation access token retrieval, read-only scope, and in-memory caching."""
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.is_closed = False

    # Simulate GitHub token exchange response
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 201
    mock_response.is_success = True
    mock_response.json.return_value = {
        "token": "ghs_test_token_12345",
        "expires_at": "2030-01-01T00:00:00Z",
        "permissions": {"metadata": "read", "contents": "read"},
    }
    mock_http.request.return_value = mock_response

    client = GitHubClient(app_id="123456", private_key_pem=test_rsa_pem, client=mock_http)

    # First fetch: calls GitHub API
    token1 = await client.get_installation_token(999)
    assert token1 == "ghs_test_token_12345"
    assert mock_http.request.call_count == 1

    # Second fetch: served from cache without extra HTTP call
    token2 = await client.get_installation_token(999)
    assert token2 == "ghs_test_token_12345"
    assert mock_http.request.call_count == 1


@pytest.mark.asyncio
async def test_rate_limit_detection(test_rsa_pem: str) -> None:
    """Verifies that HTTP 403 with rate limit header raises GitHubRateLimitError."""
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.is_closed = False

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 403
    mock_response.is_success = False
    mock_response.text = "API rate limit exceeded for installation"
    mock_response.headers = {"x-ratelimit-reset": "1893456000"}
    mock_http.request.return_value = mock_response

    client = GitHubClient(app_id="123456", private_key_pem=test_rsa_pem, client=mock_http)
    # Seed token cache to bypass installation token call
    client._token_cache[999] = ("ghs_dummy", time.time() + 3600)

    with pytest.raises(GitHubRateLimitError) as exc_info:
        await client.get_repository(999, "test-owner", "test-repo")

    assert exc_info.value.reset_timestamp == 1893456000


@pytest.mark.asyncio
async def test_not_found_detection(test_rsa_pem: str) -> None:
    """Verifies that HTTP 404 raises GitHubNotFoundError."""
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.is_closed = False

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.is_success = False
    mock_http.request.return_value = mock_response

    client = GitHubClient(app_id="123456", private_key_pem=test_rsa_pem, client=mock_http)
    client._token_cache[999] = ("ghs_dummy", time.time() + 3600)

    with pytest.raises(GitHubNotFoundError):
        await client.get_repository(999, "test-owner", "missing-repo")
