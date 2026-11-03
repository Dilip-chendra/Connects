"""End-to-end integration test for Phase 2 GitHub repository connection, scanning,
context graph synchronization, and plan generation.
"""

import uuid
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security.auth import create_access_token
from src.database.models import Membership, Project, Tenant, User
from src.database.session import get_db_session
from src.domain.github.client import GitHubClient
from src.main import app


@pytest.fixture
async def setup_tenant_and_project(db_session: AsyncSession):
    """Creates a seeded tenant, owner user, JWT token, and active project."""
    tenant = Tenant(name="Acme Corp", slug=f"acme-{uuid.uuid4().hex[:6]}")
    user = User(email=f"founder-{uuid.uuid4().hex[:6]}@acme.com")
    db_session.add_all([tenant, user])
    await db_session.flush()

    mem = Membership(tenant_id=tenant.id, user_id=user.id, role="owner")
    project = Project(
        tenant_id=tenant.id,
        name="Resume SaaS",
        primary_goal="Build and launch an AI-powered resume builder SaaS.",
        category="saas",
    )
    db_session.add_all([mem, project])
    await db_session.commit()

    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        memberships=[{"tenant_id": str(tenant.id), "role": "owner"}],
    )
    return {
        "tenant_id": str(tenant.id),
        "user_id": str(user.id),
        "project_id": str(project.id),
        "token": token,
    }


@pytest.mark.asyncio
async def test_github_e2e_journey_and_plan_generation(
    setup_tenant_and_project: dict, db_session: AsyncSession
) -> None:
    """Tests full Phase 2 journey: config -> callback -> connect -> scan -> sync -> plan generation."""
    tenant_id = setup_tenant_and_project["tenant_id"]
    project_id = setup_tenant_and_project["project_id"]
    token = setup_tenant_and_project["token"]

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        transport = ASGITransport(app=app)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": tenant_id,
        }

        with patch.object(settings, "GITHUB_APP_ID", "12345"), patch.object(
            settings, "GITHUB_APP_PRIVATE_KEY"
        ), patch.object(GitHubClient, "get_installation") as mock_get_inst, patch.object(
            GitHubClient, "list_installation_repositories"
        ) as mock_list_repos, patch.object(
            GitHubClient, "get_branch"
        ) as mock_get_branch, patch.object(
            GitHubClient, "get_tree"
        ) as mock_get_tree, patch.object(
            GitHubClient, "get_blob_content"
        ) as mock_get_blob:
            mock_get_inst.return_value = {
                "id": 8888,
                "account": {"login": "acme-corp", "type": "Organization"},
                "repository_selection": "selected",
                "permissions": {"metadata": "read", "contents": "read"},
            }

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. Inspect config
                cfg_res = await client.get(f"/workspaces/{tenant_id}/github/config", headers=headers)
                assert cfg_res.status_code == 200

                # 2. Simulate installation callback
                cb_res = await client.post(
                    f"/workspaces/{tenant_id}/github/install-callback",
                    json={"installation_id": 8888},
                    headers=headers,
                )
                assert cb_res.status_code == 200
                inst_data = cb_res.json()
                inst_id = inst_data["id"]
                assert inst_data["account_login"] == "acme-corp"

                # 3. List available repositories
                mock_list_repos.return_value = (
                    [
                        {
                            "id": 101,
                            "name": "resume-builder-repo",
                            "full_name": "acme-corp/resume-builder-repo",
                            "owner": {"login": "acme-corp"},
                            "html_url": "https://github.com/acme-corp/resume-builder-repo",
                            "private": True,
                            "default_branch": "main",
                            "description": "Resume builder frontend and API",
                        }
                    ],
                    1,
                )
                avail_res = await client.get(
                    f"/workspaces/{tenant_id}/github/installations/8888/repositories",
                    headers=headers,
                )
                assert avail_res.status_code == 200
                assert len(avail_res.json()) == 1

                # 4. Connect repository to project
                conn_res = await client.post(
                    f"/workspaces/{tenant_id}/github/projects/{project_id}/repositories",
                    json={
                        "installation_id": inst_id,
                        "github_repo_id": 101,
                        "owner": "acme-corp",
                        "name": "resume-builder-repo",
                        "full_name": "acme-corp/resume-builder-repo",
                        "html_url": "https://github.com/acme-corp/resume-builder-repo",
                        "is_private": True,
                        "default_branch": "main",
                    },
                    headers=headers,
                )
                assert conn_res.status_code == 201
                repo_id = conn_res.json()["id"]

                # 5. Execute Repository Scan
                mock_get_branch.return_value = {"commit": {"sha": "abc1234567890abcdef1234567890abcdef12"}}
                mock_get_tree.return_value = (
                    [
                        {"path": "package.json", "type": "blob", "size": 250, "sha": "sha_pkg"},
                        {"path": "Dockerfile", "type": "blob", "size": 150, "sha": "sha_dock"},
                        {"path": "tests/test_app.py", "type": "blob", "size": 300, "sha": "sha_t"},
                    ],
                    False,
                )

                async def fake_blob(inst, owner, repo, sha):
                    if sha == "sha_pkg":
                        return '{"dependencies": {"next": "14.2.0"}, "scripts": {"build": "next build"}}'
                    if sha == "sha_dock":
                        return "FROM node:20\nCMD [\"npm\", \"start\"]"
                    if sha == "sha_t":
                        return "def test_ok(): pass"
                    return ""

                mock_get_blob.side_effect = fake_blob

                scan_res = await client.post(
                    f"/workspaces/{tenant_id}/github/projects/{project_id}/repositories/{repo_id}/scans",
                    json={"branch": "main"},
                    headers=headers,
                )
                assert scan_res.status_code == 201
                scan_data = scan_res.json()
                scan_id = scan_data["id"]
                assert scan_data["status"] == "completed"
                assert scan_data["commit_sha"] == "abc1234567890abcdef1234567890abcdef12"

                # 6. Check Findings
                findings_res = await client.get(
                    f"/workspaces/{tenant_id}/github/projects/{project_id}/scans/{scan_id}/findings",
                    headers=headers,
                )
                assert findings_res.status_code == 200
                findings = findings_res.json()
                assert len(findings) > 0

                # 7. Synthesize Execution Plan from Findings
                plan_res = await client.post(
                    f"/workspaces/{tenant_id}/github/projects/{project_id}/scans/{scan_id}/create-plan",
                    headers=headers,
                )
                assert plan_res.status_code == 201
                plan_data = plan_res.json()
                assert plan_data["plan_source"] == "repo_intelligence_planner_v1"
                assert plan_data["status"] == "draft"
                assert len(plan_data["plan_data"]["tasks"]) >= 3

                # 8. Disconnect Repository
                disc_res = await client.delete(
                    f"/workspaces/{tenant_id}/github/projects/{project_id}/repositories/{repo_id}",
                    headers=headers,
                )
                assert disc_res.status_code == 200
                assert disc_res.json()["status"] == "disconnected"
    finally:
        app.dependency_overrides.clear()
