"""Tests for API health probes, root metadata, and error handling consistency."""

from httpx import AsyncClient


async def test_root_endpoint(client: AsyncClient) -> None:
    res = await client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["app"] == "Connects"
    assert "Real Outcomes" in data["tagline"]


async def test_liveness_probe(client: AsyncClient) -> None:
    res = await client.get("/health/live")
    assert res.status_code == 200
    assert res.json() == {"status": "alive"}


async def test_readiness_probe(client: AsyncClient) -> None:
    res = await client.get("/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"


async def test_uniform_error_payload_format(client: AsyncClient) -> None:
    res = await client.get("/non-existent-endpoint-404")
    assert res.status_code == 404
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "HTTP_404"
    assert "Not Found" in data["error"]["message"]


async def test_workflow_execution_creation_and_task_list(
    client: AsyncClient, setup_two_tenants: dict
) -> None:
    t_a = setup_two_tenants["tenant_a"]
    headers = {"Authorization": f"Bearer {t_a['token']}"}

    # 1. Create project
    proj_res = await client.post(
        f"/tenants/{t_a['tenant_id']}/projects",
        headers=headers,
        json={"name": "Workflow Project", "primary_goal": "Test workflow creation"},
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # 2. Create workflow
    wf_res = await client.post(
        f"/tenants/{t_a['tenant_id']}/workflows",
        headers=headers,
        json={"project_id": project_id, "template_name": "ai_app_to_saas"},
    )
    assert wf_res.status_code == 201
    wf_data = wf_res.json()
    assert wf_data["status"] == "planned"
    assert wf_data["template_name"] == "ai_app_to_saas"
    workflow_id = wf_data["id"]

    # 3. List tasks (empty initially)
    tasks_res = await client.get(
        f"/tenants/{t_a['tenant_id']}/workflows/{workflow_id}/tasks",
        headers=headers,
    )
    assert tasks_res.status_code == 200
    assert isinstance(tasks_res.json(), list)
