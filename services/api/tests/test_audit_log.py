"""Tests verifying audit log isolation and structured logging secret redaction."""

import logging

from httpx import AsyncClient

from src.core.logging import RedactingFormatter


def test_redacting_formatter_scrubs_secrets() -> None:
    formatter = RedactingFormatter(fmt="%(message)s")

    # Test Bearer token redaction
    rec1 = logging.LogRecord(
        "test", logging.INFO, "", 0, "Authorization: Bearer eyJhbGciOi...", (), None
    )
    formatted1 = formatter.format(rec1)
    assert "eyJhbGciOi..." not in formatted1
    assert "Bearer [REDACTED]" in formatted1

    # Test password redaction
    rec2 = logging.LogRecord(
        "test", logging.INFO, "", 0, "User login password='super_secret_pass_123'", (), None
    )
    formatted2 = formatter.format(rec2)
    assert "super_secret_pass_123" not in formatted2
    assert "[REDACTED]" in formatted2

    # Test API key redaction
    rec3 = logging.LogRecord(
        "test", logging.INFO, "", 0, "Provider request with api_key='sk_live_999999'", (), None
    )
    formatted3 = formatter.format(rec3)
    assert "sk_live_999999" not in formatted3
    assert "[REDACTED]" in formatted3


async def test_audit_logs_are_tenant_scoped(client: AsyncClient, setup_two_tenants: dict) -> None:
    t_a = setup_two_tenants["tenant_a"]
    t_b = setup_two_tenants["tenant_b"]

    headers_a = {"Authorization": f"Bearer {t_a['token']}"}
    headers_b = {"Authorization": f"Bearer {t_b['token']}"}

    # Tenant A triggers an action that creates an audit log
    res_create = await client.post(
        f"/tenants/{t_a['tenant_id']}/projects",
        headers=headers_a,
        json={"name": "Audited Project", "primary_goal": "Audit test"},
    )
    assert res_create.status_code == 201

    # Tenant A fetches audit logs -> finds the project.created log
    res_logs_a = await client.get(f"/tenants/{t_a['tenant_id']}/audit-logs", headers=headers_a)
    assert res_logs_a.status_code == 200
    actions_a = [entry["action"] for entry in res_logs_a.json()]
    assert "project.created" in actions_a

    # Tenant B fetches audit logs -> sees no logs from Tenant A
    res_logs_b = await client.get(f"/tenants/{t_b['tenant_id']}/audit-logs", headers=headers_b)
    assert res_logs_b.status_code == 200
    assert len(res_logs_b.json()) == 0
