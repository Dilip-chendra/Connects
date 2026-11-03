"""GitHub API Client for Connects Platform.

Handles GitHub App authentication (RS256 JWT generation, installation access token
acquisition), rate limit headers, bounded retries with exponential backoff, and read-only
repository inspection.
"""

import asyncio
import base64
import time
from datetime import datetime
from typing import Any

import httpx
import jwt

from src.core.config import settings
from src.core.logging import logger


class GitHubError(Exception):
    """Base exception for all GitHub integration failures."""


class GitHubAppNotConfiguredError(GitHubError):
    """Raised when GitHub App ID or Private Key is missing from server settings."""


class GitHubAuthenticationError(GitHubError):
    """Raised when GitHub App JWT signing or installation token acquisition fails."""


class GitHubPermissionError(GitHubError):
    """Raised when installation lacks required read permissions."""


class GitHubRateLimitError(GitHubError):
    """Raised when GitHub API rate limit is exceeded."""

    def __init__(self, message: str, reset_timestamp: int | None = None) -> None:
        super().__init__(message)
        self.reset_timestamp = reset_timestamp


class GitHubNotFoundError(GitHubError):
    """Raised when repository, branch, tree, or file is not found."""


class GitHubApiError(GitHubError):
    """General GitHub API error with status code and payload details."""

    def __init__(self, status_code: int, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(f"GitHub API Error [{status_code}]: {message}")
        self.status_code = status_code
        self.details = details or {}


class GitHubClient:
    """Production-grade asynchronous GitHub App client."""

    API_BASE = "https://api.github.com"
    API_VERSION = "2022-11-28"
    DEFAULT_TIMEOUT_SECS = 15.0
    MAX_RETRIES = 3

    def __init__(
        self,
        app_id: str | None = None,
        private_key_pem: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.app_id = app_id or settings.GITHUB_APP_ID
        self.private_key_pem = private_key_pem or settings.get_github_private_key_pem()
        self._client = client
        # In-memory token cache: {installation_id: (token, expires_at_epoch)}
        self._token_cache: dict[int, tuple[str, float]] = {}

    def _ensure_configured(self) -> None:
        if not self.app_id or not self.private_key_pem:
            raise GitHubAppNotConfiguredError(
                "GitHub App integration is not configured on the server. "
                "GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY must be set."
            )

    def generate_app_jwt(self) -> str:
        """Generates an RS256 signed JWT valid for 10 minutes to authenticate as the GitHub App."""
        self._ensure_configured()
        now = int(time.time())
        payload = {
            # 60-second buffer in the past to compensate for clock drift
            "iat": now - 60,
            "exp": now + (9 * 60),  # 9 minutes valid
            "iss": self.app_id,
        }
        try:
            return jwt.encode(payload, self.private_key_pem, algorithm="RS256")
        except Exception as e:
            raise GitHubAuthenticationError(f"Failed to sign GitHub App JWT: {e!s}") from e

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client and not self._client.is_closed:
            return self._client
        return httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT_SECS)

    async def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        url = f"{self.API_BASE}{path}"
        default_headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.API_VERSION,
            "User-Agent": "Connects-Startup-OS/1.0",
        }
        merged_headers = {**default_headers, **headers}

        client = await self._get_client()
        should_close = client is not self._client

        try:
            for attempt in range(1, self.MAX_RETRIES + 1):
                try:
                    res = await client.request(
                        method=method,
                        url=url,
                        headers=merged_headers,
                        params=params,
                        json=json_body,
                    )

                    # Handle Rate Limits
                    if res.status_code == 403 and "rate limit" in res.text.lower():
                        reset_header = res.headers.get("x-ratelimit-reset")
                        reset_ts = int(reset_header) if reset_header and reset_header.isdigit() else None
                        raise GitHubRateLimitError(
                            "GitHub API rate limit exceeded.", reset_timestamp=reset_ts
                        )

                    # Handle 404
                    if res.status_code == 404:
                        raise GitHubNotFoundError(f"Resource not found: {path}")

                    # Handle Auth/Permissions
                    if res.status_code in (401, 403):
                        raise GitHubPermissionError(
                            f"GitHub authorization error ({res.status_code}): {res.text}"
                        )

                    # Retry transient 5xx errors
                    if res.status_code in (500, 502, 503, 504) and attempt < self.MAX_RETRIES:
                        backoff = 2**attempt
                        logger.warning(
                            f"GitHub API {res.status_code} on {path}. Retrying in {backoff}s (attempt {attempt})."
                        )
                        await asyncio.sleep(backoff)
                        continue

                    if not res.is_success:
                        raise GitHubApiError(
                            res.status_code,
                            res.text,
                            details=res.json() if res.headers.get("content-type", "").startswith("application/json") else None,
                        )

                    return res.json()

                except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                    if attempt < self.MAX_RETRIES:
                        backoff = 2**attempt
                        await asyncio.sleep(backoff)
                        continue
                    raise GitHubApiError(504, f"Network timeout contacting GitHub API: {net_err!s}") from net_err

            raise GitHubApiError(500, "Maximum retries exceeded connecting to GitHub API.")

        finally:
            if should_close:
                await client.aclose()

    async def get_installation_token(self, installation_id: int) -> str:
        """Retrieves or creates a cached, read-only installation access token."""
        now = time.time()
        cached = self._token_cache.get(installation_id)
        if cached:
            token, expires_at = cached
            # Buffer by 2 minutes
            if now < (expires_at - 120):
                return token

        app_jwt = self.generate_app_jwt()
        headers = {"Authorization": f"Bearer {app_jwt}"}

        # Request strictly read-only scoped token
        payload = {
            "permissions": {
                "metadata": "read",
                "contents": "read",
            }
        }

        data = await self._request(
            method="POST",
            path=f"/app/installations/{installation_id}/access_tokens",
            headers=headers,
            json_body=payload,
        )

        token = data.get("token")
        if not token:
            raise GitHubAuthenticationError("Failed to obtain installation token from GitHub.")

        # Parse expires_at ISO string (e.g. 2026-10-20T14:30:00Z)
        expires_at_str = data.get("expires_at")
        if expires_at_str:
            exp_dt = datetime.fromisoformat(expires_at_str)
            exp_epoch = exp_dt.timestamp()
        else:
            exp_epoch = now + 3600

        self._token_cache[installation_id] = (token, exp_epoch)
        return token

    async def get_installation(self, installation_id: int) -> dict[str, Any]:
        """Fetches installation metadata using the App JWT."""
        app_jwt = self.generate_app_jwt()
        headers = {"Authorization": f"Bearer {app_jwt}"}
        return await self._request("GET", f"/app/installations/{installation_id}", headers=headers)

    async def list_installation_repositories(
        self, installation_id: int, page: int = 1, per_page: int = 30
    ) -> tuple[list[dict[str, Any]], int]:
        """Lists repositories accessible to the installation with pagination."""
        token = await self.get_installation_token(installation_id)
        headers = {"Authorization": f"Bearer {token}"}
        params = {"page": page, "per_page": min(per_page, 100)}

        data = await self._request(
            "GET", "/installation/repositories", headers=headers, params=params
        )
        repos = data.get("repositories", [])
        total_count = data.get("total_count", len(repos))
        return repos, total_count

    async def get_repository(
        self, installation_id: int, owner: str, repo: str
    ) -> dict[str, Any]:
        """Fetches repository metadata."""
        token = await self.get_installation_token(installation_id)
        headers = {"Authorization": f"Bearer {token}"}
        return await self._request("GET", f"/repos/{owner}/{repo}", headers=headers)

    async def get_branch(
        self, installation_id: int, owner: str, repo: str, branch: str
    ) -> dict[str, Any]:
        """Fetches branch info, including the latest commit SHA."""
        token = await self.get_installation_token(installation_id)
        headers = {"Authorization": f"Bearer {token}"}
        return await self._request("GET", f"/repos/{owner}/{repo}/branches/{branch}", headers=headers)

    async def get_tree(
        self, installation_id: int, owner: str, repo: str, commit_sha: str, recursive: bool = True
    ) -> tuple[list[dict[str, Any]], bool]:
        """Fetches the Git tree for an exact commit SHA.
        
        Returns:
            (tree_items, is_truncated)
        """
        token = await self.get_installation_token(installation_id)
        headers = {"Authorization": f"Bearer {token}"}
        params = {"recursive": "1"} if recursive else {}

        data = await self._request(
            "GET", f"/repos/{owner}/{repo}/git/trees/{commit_sha}", headers=headers, params=params
        )
        items = data.get("tree", [])
        is_truncated = bool(data.get("truncated", False))
        return items, is_truncated

    async def get_blob_content(
        self, installation_id: int, owner: str, repo: str, file_sha: str
    ) -> str:
        """Fetches blob content by immutable SHA and decodes to UTF-8 text."""
        token = await self.get_installation_token(installation_id)
        headers = {"Authorization": f"Bearer {token}"}

        data = await self._request(
            "GET", f"/repos/{owner}/{repo}/git/blobs/{file_sha}", headers=headers
        )
        content_b64 = data.get("content", "")
        encoding = data.get("encoding", "base64")

        if encoding == "base64":
            raw_bytes = base64.b64decode(content_b64)
            try:
                return raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # Binary file
                return ""
        return content_b64

    async def get_file_content(
        self, installation_id: int, owner: str, repo: str, path: str, ref: str
    ) -> str:
        """Fetches file content by path at a specific commit ref."""
        token = await self.get_installation_token(installation_id)
        headers = {"Authorization": f"Bearer {token}"}

        data = await self._request(
            "GET", f"/repos/{owner}/{repo}/contents/{path}", headers=headers, params={"ref": ref}
        )
        content_b64 = data.get("content", "")
        if content_b64:
            raw_bytes = base64.b64decode(content_b64)
            try:
                return raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return ""
        return ""
