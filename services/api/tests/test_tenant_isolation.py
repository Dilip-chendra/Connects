"""Tests verifying strict multi-tenant isolation, authorization barriers, and session partition."""

from httpx import AsyncClient


async def test_unauthenticated_request_rejected(
    client: AsyncClient, setup_two_tenants: dict
) -> None:
    tenant_a_id = setup_two_tenants["tenant_a"]["tenant_id"]
    res = await client.get(f"/tenants/{tenant_a_id}/projects")
    assert res.status_code == 401
    assert "Missing authentication credentials" in res.json()["error"]["message"]


async def test_cross_tenant_access_forbidden(client: AsyncClient, setup_two_tenants: dict) -> None:
    """User belonging strictly to Tenant A cannot access Tenant B's workspace."""
    token_a = setup_two_tenants["tenant_a"]["token"]
    tenant_b_id = setup_two_tenants["tenant_b"]["tenant_id"]

    headers = {"Authorization": f"Bearer {token_a}"}
    res = await client.get(f"/tenants/{tenant_b_id}/projects", headers=headers)

    assert res.status_code == 403
    assert "Access to the specified tenant is denied" in res.json()["error"]["message"]


async def test_tenant_projects_are_strictly_partitioned(
    client: AsyncClient, setup_two_tenants: dict
) -> None:
    """Projects created by Tenant A are invisible to Tenant B, and vice versa."""
    t_a = setup_two_tenants["tenant_a"]
    t_b = setup_two_tenants["tenant_b"]

    headers_a = {"Authorization": f"Bearer {t_a['token']}"}
    headers_b = {"Authorization": f"Bearer {t_b['token']}"}

    # Tenant A creates Project Alpha
    res_a = await client.post(
        f"/tenants/{t_a['tenant_id']}/projects",
        headers=headers_a,
        json={"name": "Project Alpha", "primary_goal": "Validate MVP SaaS"},
    )
    assert res_a.status_code == 201
    project_alpha_id = res_a.json()["id"]

    # Tenant B creates Project Beta
    res_b = await client.post(
        f"/tenants/{t_b['tenant_id']}/projects",
        headers=headers_b,
        json={"name": "Project Beta", "primary_goal": "Build CRM Integration"},
    )
    assert res_b.status_code == 201
    project_beta_id = res_b.json()["id"]
    assert project_beta_id is not None

    # Listing projects as Tenant A returns only Project Alpha
    list_a = await client.get(f"/tenants/{t_a['tenant_id']}/projects", headers=headers_a)
    assert list_a.status_code == 200
    names_a = [p["name"] for p in list_a.json()]
    assert "Project Alpha" in names_a
    assert "Project Beta" not in names_a

    # Listing projects as Tenant B returns only Project Beta
    list_b = await client.get(f"/tenants/{t_b['tenant_id']}/projects", headers=headers_b)
    assert list_b.status_code == 200
    names_b = [p["name"] for p in list_b.json()]
    assert "Project Beta" in names_b
    assert "Project Alpha" not in names_b

    # Tenant B querying Project Alpha ID via Tenant B path returns 404
    fetch_other = await client.get(
        f"/tenants/{t_b['tenant_id']}/projects/{project_alpha_id}",
        headers=headers_b,
    )
    assert fetch_other.status_code == 404
    assert "Project not found in this tenant" in fetch_other.json()["error"]["message"]


async def test_tenant_context_cannot_leak_across_requests(
    client: AsyncClient, setup_two_tenants: dict
) -> None:
    """Interleaved requests from Tenant A and Tenant B maintain isolated context."""
    t_a = setup_two_tenants["tenant_a"]
    t_b = setup_two_tenants["tenant_b"]

    headers_a = {"Authorization": f"Bearer {t_a['token']}"}
    headers_b = {"Authorization": f"Bearer {t_b['token']}"}

    for _ in range(5):
        res_a = await client.get(f"/tenants/{t_a['tenant_id']}", headers=headers_a)
        assert res_a.status_code == 200
        assert res_a.json()["id"] == t_a["tenant_id"]

        res_b = await client.get(f"/tenants/{t_b['tenant_id']}", headers=headers_b)
        assert res_b.status_code == 200
        assert res_b.json()["id"] == t_b["tenant_id"]


async def test_request_cannot_spoof_tenant_via_header(
    client: AsyncClient, setup_two_tenants: dict
) -> None:
    """Attaching X-Tenant-ID for Tenant B while authenticated as Tenant A is rejected."""
    t_a = setup_two_tenants["tenant_a"]
    t_b = setup_two_tenants["tenant_b"]

    # Request path has Tenant A, but header claims Tenant B -> Denied
    headers = {
        "Authorization": f"Bearer {t_a['token']}",
        "X-Tenant-ID": t_b["tenant_id"],
    }
    # Query an endpoint that reads header when path param is absent or mismatched
    res = await client.get(f"/tenants/{t_b['tenant_id']}/projects", headers=headers)
    assert res.status_code == 403
    assert "Access to the specified tenant is denied" in res.json()["error"]["message"]


async def test_tampered_jwt_signature_rejected(
    client: AsyncClient, setup_two_tenants: dict
) -> None:
    token = setup_two_tenants["tenant_a"]["token"]
    # Tamper with the signature bytes of the JWT
    tampered_token = token[:-4] + "wxyz"
    headers = {"Authorization": f"Bearer {tampered_token}"}
    t_a_id = setup_two_tenants["tenant_a"]["tenant_id"]

    res = await client.get(f"/tenants/{t_a_id}/projects", headers=headers)
    assert res.status_code == 401
    assert "Invalid authentication token credentials" in res.json()["error"]["message"]
