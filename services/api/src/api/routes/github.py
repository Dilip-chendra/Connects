"""GitHub Integration & Repository Intelligence API Routes."""

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.security.auth import TenantContext, get_tenant_context
from src.database.models import (
    AuditLog,
    ConnectedRepository,
    GitHubInstallation,
    Project,
    RepositoryFinding,
    RepositoryScan,
)
from src.database.session import get_db_session
from src.domain.github.client import (
    GitHubClient,
    GitHubError,
    GitHubRateLimitError,
)
from src.domain.github.context_sync import RepoContextSyncService
from src.domain.github.inspector import RepositoryInspector

router = APIRouter(tags=["github"])


# -----------------------------------------------------------------------------
# Request & Response Schemas
# -----------------------------------------------------------------------------

class GitHubConfigResponse(BaseModel):
    is_configured: bool
    app_name: str | None = None
    install_url: str | None = None
    setup_required: bool


class GitHubInstallInitResponse(BaseModel):
    state: str
    install_url: str | None


class GitHubInstallCallbackRequest(BaseModel):
    installation_id: int
    setup_action: str | None = None
    state: str | None = None


class GitHubInstallationResponse(BaseModel):
    id: str
    installation_id: int
    account_login: str
    account_type: str
    account_avatar_url: str | None
    repository_selection: str
    status: str
    created_at: str


class GitHubAvailableRepoResponse(BaseModel):
    id: int
    name: str
    full_name: str
    owner: str
    html_url: str
    is_private: bool
    default_branch: str
    description: str | None


class ConnectRepositoryRequest(BaseModel):
    installation_id: str
    github_repo_id: int
    owner: str
    name: str
    full_name: str
    html_url: str
    is_private: bool = True
    default_branch: str = "main"
    selected_branch: str = "main"


class ConnectedRepositoryResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    installation_id: str
    github_repo_id: int
    owner: str
    name: str
    full_name: str
    html_url: str
    is_private: bool
    default_branch: str
    selected_branch: str
    latest_commit_sha: str | None
    status: str
    last_error_category: str | None
    last_scanned_at: str | None
    created_at: str


class InitiateScanRequest(BaseModel):
    branch: str | None = None


class FindingResponse(BaseModel):
    id: str
    finding_id: str
    category: str
    severity: str
    title: str
    description: str
    confidence: str
    verification_status: str
    file_path: str | None
    line_start: int | None
    line_end: int | None
    evidence_excerpt: str | None
    commit_sha: str
    rule_id: str
    recommended_action: str
    created_at: str


class ScanDetailResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    repository_id: str
    commit_sha: str
    branch: str
    status: str
    files_analyzed_count: int
    findings_count: int
    duration_ms: int | None
    error_category: str | None
    error_message: str | None
    scan_summary: dict[str, Any]
    created_at: str
    completed_at: str | None


# -----------------------------------------------------------------------------
# Configuration & Installation Routes
# -----------------------------------------------------------------------------

@router.get("/config", response_model=GitHubConfigResponse)
async def get_github_config(
    tenant_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> GitHubConfigResponse:
    """Returns the current server-side GitHub App configuration status."""
    is_conf = settings.is_github_configured()
    install_url = None
    if is_conf and settings.GITHUB_APP_NAME:
        install_url = f"https://github.com/apps/{settings.GITHUB_APP_NAME}/installations/new"

    return GitHubConfigResponse(
        is_configured=is_conf,
        app_name=settings.GITHUB_APP_NAME,
        install_url=install_url,
        setup_required=not is_conf,
    )


@router.post("/install-init", response_model=GitHubInstallInitResponse)
async def initiate_github_install(
    tenant_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> GitHubInstallInitResponse:
    """Generates a secure state token for GitHub App installation."""
    state_token = f"{tenant_ctx.tenant_id}_{secrets.token_urlsafe(16)}"
    install_url = None
    if settings.GITHUB_APP_NAME:
        install_url = f"https://github.com/apps/{settings.GITHUB_APP_NAME}/installations/new?state={state_token}"

    return GitHubInstallInitResponse(state=state_token, install_url=install_url)


@router.post("/install-callback", response_model=GitHubInstallationResponse)
async def process_installation_callback(
    tenant_id: str,
    req: GitHubInstallCallbackRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> GitHubInstallationResponse:
    """Validates and persists GitHub App installation for the active workspace."""
    if not tenant_ctx.can_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Owner role is required to manage GitHub connections.",
        )

    if not settings.is_github_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub App integration is not configured on the server.",
        )

    client = GitHubClient()
    try:
        gh_data = await client.get_installation(req.installation_id)
    except GitHubError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to verify GitHub installation: {e!s}",
        ) from e

    account = gh_data.get("account", {})
    account_login = account.get("login", "unknown")
    account_type = account.get("type", "User")
    avatar_url = account.get("avatar_url")
    repo_selection = gh_data.get("repository_selection", "selected")
    permissions = gh_data.get("permissions", {})

    # Check existing installation record
    res = await session.execute(
        select(GitHubInstallation).where(
            GitHubInstallation.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
            GitHubInstallation.installation_id == req.installation_id,
        )
    )
    inst = res.scalar_one_or_none()
    if not inst:
        inst = GitHubInstallation(
            tenant_id=uuid.UUID(tenant_ctx.tenant_id),
            installation_id=req.installation_id,
            account_login=account_login,
            account_type=account_type,
            account_avatar_url=avatar_url,
            repository_selection=repo_selection,
            permissions=permissions,
            status="active",
            installed_by=uuid.UUID(tenant_ctx.user_id),
        )
        session.add(inst)
    else:
        inst.account_login = account_login
        inst.account_type = account_type
        inst.account_avatar_url = avatar_url
        inst.repository_selection = repo_selection
        inst.permissions = permissions
        inst.status = "active"
        inst.updated_at = datetime.now(UTC)

    audit = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="github.installation_connected",
        resource_type="github_installation",
        resource_id=str(req.installation_id),
        details={"account_login": account_login, "account_type": account_type},
    )
    session.add(audit)
    await session.flush()
    await session.refresh(inst)

    return GitHubInstallationResponse(
        id=str(inst.id),
        installation_id=inst.installation_id,
        account_login=inst.account_login,
        account_type=inst.account_type,
        account_avatar_url=inst.account_avatar_url,
        repository_selection=inst.repository_selection,
        status=inst.status,
        created_at=inst.created_at.isoformat(),
    )


@router.get("/installations", response_model=list[GitHubInstallationResponse])
async def list_installations(
    tenant_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[GitHubInstallationResponse]:
    """Lists authorized GitHub installations for the workspace."""
    res = await session.execute(
        select(GitHubInstallation)
        .where(
            GitHubInstallation.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
            GitHubInstallation.status == "active",
        )
        .order_by(GitHubInstallation.created_at.desc())
    )
    installations = res.scalars().all()
    return [
        GitHubInstallationResponse(
            id=str(inst.id),
            installation_id=inst.installation_id,
            account_login=inst.account_login,
            account_type=inst.account_type,
            account_avatar_url=inst.account_avatar_url,
            repository_selection=inst.repository_selection,
            status=inst.status,
            created_at=inst.created_at.isoformat(),
        )
        for inst in installations
    ]


@router.get(
    "/installations/{installation_id}/repositories",
    response_model=list[GitHubAvailableRepoResponse],
)
async def list_installation_repositories(
    tenant_id: str,
    installation_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[GitHubAvailableRepoResponse]:
    """Lists repositories accessible to the authorized installation."""
    # Verify installation belongs to active tenant
    res = await session.execute(
        select(GitHubInstallation).where(
            GitHubInstallation.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
            GitHubInstallation.installation_id == installation_id,
            GitHubInstallation.status == "active",
        )
    )
    inst = res.scalar_one_or_none()
    if not inst:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GitHub installation not found in this workspace.",
        )

    client = GitHubClient()
    try:
        repos, _ = await client.list_installation_repositories(
            installation_id=installation_id, page=page, per_page=per_page
        )
        return [
            GitHubAvailableRepoResponse(
                id=r["id"],
                name=r["name"],
                full_name=r["full_name"],
                owner=r["owner"]["login"],
                html_url=r["html_url"],
                is_private=r.get("private", True),
                default_branch=r.get("default_branch", "main"),
                description=r.get("description"),
            )
            for r in repos
        ]
    except GitHubError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# -----------------------------------------------------------------------------
# Project Connected Repository Routes
# -----------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/repositories",
    response_model=ConnectedRepositoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def connect_repository_to_project(
    tenant_id: str,
    project_id: str,
    req: ConnectRepositoryRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ConnectedRepositoryResponse:
    """Connects an accessible GitHub repository to a Connects project."""
    if not tenant_ctx.can_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Owner role is required to connect repositories.",
        )

    # 1. Verify project exists in active tenant
    proj_res = await session.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    project = proj_res.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    # 2. Verify installation belongs to active tenant
    inst_res = await session.execute(
        select(GitHubInstallation).where(
            GitHubInstallation.id == uuid.UUID(req.installation_id),
            GitHubInstallation.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    inst = inst_res.scalar_one_or_none()
    if not inst:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GitHub installation not found in this workspace.",
        )

    # 3. Upsert connected_repositories
    existing_res = await session.execute(
        select(ConnectedRepository).where(
            ConnectedRepository.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
            ConnectedRepository.project_id == uuid.UUID(project_id),
            ConnectedRepository.github_repo_id == req.github_repo_id,
        )
    )
    connected_repo = existing_res.scalar_one_or_none()
    if not connected_repo:
        connected_repo = ConnectedRepository(
            tenant_id=uuid.UUID(tenant_ctx.tenant_id),
            project_id=uuid.UUID(project_id),
            installation_id=inst.id,
            github_repo_id=req.github_repo_id,
            owner=req.owner,
            name=req.name,
            full_name=req.full_name,
            html_url=req.html_url,
            is_private=req.is_private,
            default_branch=req.default_branch,
            selected_branch=req.selected_branch or req.default_branch,
            status="connected",
        )
        session.add(connected_repo)
    else:
        connected_repo.status = "connected"
        connected_repo.owner = req.owner
        connected_repo.name = req.name
        connected_repo.full_name = req.full_name
        connected_repo.html_url = req.html_url
        connected_repo.default_branch = req.default_branch
        connected_repo.selected_branch = req.selected_branch or req.default_branch
        connected_repo.updated_at = datetime.now(UTC)

    audit = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="github.repository_connected",
        resource_type="connected_repository",
        resource_id=str(connected_repo.id),
        details={"full_name": req.full_name, "project_id": project_id},
    )
    session.add(audit)
    await session.flush()
    await session.refresh(connected_repo)

    return ConnectedRepositoryResponse(
        id=str(connected_repo.id),
        tenant_id=str(connected_repo.tenant_id),
        project_id=str(connected_repo.project_id),
        installation_id=str(connected_repo.installation_id),
        github_repo_id=connected_repo.github_repo_id,
        owner=connected_repo.owner,
        name=connected_repo.name,
        full_name=connected_repo.full_name,
        html_url=connected_repo.html_url,
        is_private=connected_repo.is_private,
        default_branch=connected_repo.default_branch,
        selected_branch=connected_repo.selected_branch,
        latest_commit_sha=connected_repo.latest_commit_sha,
        status=connected_repo.status,
        last_error_category=connected_repo.last_error_category,
        last_scanned_at=connected_repo.last_scanned_at.isoformat() if connected_repo.last_scanned_at else None,
        created_at=connected_repo.created_at.isoformat(),
    )


@router.get(
    "/projects/{project_id}/repositories",
    response_model=list[ConnectedRepositoryResponse],
)
async def list_project_repositories(
    tenant_id: str,
    project_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[ConnectedRepositoryResponse]:
    """Lists repositories linked to the specified project."""
    res = await session.execute(
        select(ConnectedRepository)
        .where(
            ConnectedRepository.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
            ConnectedRepository.project_id == uuid.UUID(project_id),
            ConnectedRepository.status == "connected",
        )
        .order_by(ConnectedRepository.created_at.desc())
    )
    repos = res.scalars().all()
    return [
        ConnectedRepositoryResponse(
            id=str(r.id),
            tenant_id=str(r.tenant_id),
            project_id=str(r.project_id),
            installation_id=str(r.installation_id),
            github_repo_id=r.github_repo_id,
            owner=r.owner,
            name=r.name,
            full_name=r.full_name,
            html_url=r.html_url,
            is_private=r.is_private,
            default_branch=r.default_branch,
            selected_branch=r.selected_branch,
            latest_commit_sha=r.latest_commit_sha,
            status=r.status,
            last_error_category=r.last_error_category,
            last_scanned_at=r.last_scanned_at.isoformat() if r.last_scanned_at else None,
            created_at=r.created_at.isoformat(),
        )
        for r in repos
    ]


@router.delete(
    "/projects/{project_id}/repositories/{repository_id}",
    response_model=ConnectedRepositoryResponse,
)
async def disconnect_repository(
    tenant_id: str,
    project_id: str,
    repository_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ConnectedRepositoryResponse:
    """Disconnects a repository from a project without deleting historical scan records."""
    if not tenant_ctx.can_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Owner role is required to disconnect repositories.",
        )

    res = await session.execute(
        select(ConnectedRepository).where(
            ConnectedRepository.id == uuid.UUID(repository_id),
            ConnectedRepository.project_id == uuid.UUID(project_id),
            ConnectedRepository.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    repo = res.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")

    repo.status = "disconnected"
    repo.updated_at = datetime.now(UTC)

    audit = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="github.repository_disconnected",
        resource_type="connected_repository",
        resource_id=str(repo.id),
        details={"full_name": repo.full_name},
    )
    session.add(audit)
    await session.flush()
    await session.refresh(repo)

    return ConnectedRepositoryResponse(
        id=str(repo.id),
        tenant_id=str(repo.tenant_id),
        project_id=str(repo.project_id),
        installation_id=str(repo.installation_id),
        github_repo_id=repo.github_repo_id,
        owner=repo.owner,
        name=repo.name,
        full_name=repo.full_name,
        html_url=repo.html_url,
        is_private=repo.is_private,
        default_branch=repo.default_branch,
        selected_branch=repo.selected_branch,
        latest_commit_sha=repo.latest_commit_sha,
        status=repo.status,
        last_error_category=repo.last_error_category,
        last_scanned_at=repo.last_scanned_at.isoformat() if repo.last_scanned_at else None,
        created_at=repo.created_at.isoformat(),
    )


# -----------------------------------------------------------------------------
# Repository Scan & Findings Routes
# -----------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/repositories/{repository_id}/scans",
    response_model=ScanDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_repository_scan(
    tenant_id: str,
    project_id: str,
    repository_id: str,
    req: InitiateScanRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ScanDetailResponse:
    """Initiates a real, commit-pinned repository inspection and persists findings."""
    if not tenant_ctx.can_mutate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted to initiate repository scans.",
        )

    # 1. Fetch connected repo and installation
    res = await session.execute(
        select(ConnectedRepository)
        .options(selectinload(ConnectedRepository.installation))
        .where(
            ConnectedRepository.id == uuid.UUID(repository_id),
            ConnectedRepository.project_id == uuid.UUID(project_id),
            ConnectedRepository.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    repo = res.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")

    target_branch = req.branch or repo.selected_branch or repo.default_branch

    # 2. Execute Inspector
    client = GitHubClient()
    inspector = RepositoryInspector(client)

    try:
        inspection = await inspector.inspect(
            installation_id=repo.installation.installation_id,
            owner=repo.owner,
            repo=repo.name,
            selected_branch=target_branch,
        )
    except GitHubRateLimitError as rle:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"GitHub API rate limit exceeded. Reset at: {rle.reset_timestamp}",
        ) from rle
    except GitHubError as ge:
        repo.status = "error"
        repo.last_error_category = type(ge).__name__
        await session.flush()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub inspection failed: {ge!s}",
        ) from ge

    # 3. Create Scan Record
    scan = RepositoryScan(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        project_id=uuid.UUID(project_id),
        repository_id=repo.id,
        commit_sha=inspection.commit_sha,
        branch=inspection.branch,
        status="completed",
        files_analyzed_count=inspection.files_analyzed_count,
        findings_count=len(inspection.findings),
        duration_ms=inspection.duration_ms,
        scan_summary=inspection.scan_summary,
        initiated_by=uuid.UUID(tenant_ctx.user_id),
        completed_at=datetime.now(UTC),
    )
    session.add(scan)
    await session.flush()

    # 4. Persist Findings
    db_findings: list[RepositoryFinding] = []
    for f in inspection.findings:
        rf = RepositoryFinding(
            tenant_id=uuid.UUID(tenant_ctx.tenant_id),
            project_id=uuid.UUID(project_id),
            scan_id=scan.id,
            finding_id=f.finding_id,
            category=f.category,
            severity=f.severity,
            title=f.title,
            description=f.description,
            confidence=f.confidence,
            verification_status=f.verification_status,
            file_path=f.file_path,
            line_start=f.line_start,
            line_end=f.line_end,
            evidence_excerpt=f.evidence_excerpt,
            commit_sha=inspection.commit_sha,
            rule_id=f.rule_id,
            recommended_action=f.recommended_action,
        )
        session.add(rf)
        db_findings.append(rf)
    await session.flush()

    # 5. Update Connected Repository state
    repo.latest_commit_sha = inspection.commit_sha
    repo.last_scanned_at = scan.completed_at
    repo.status = "connected"
    repo.last_error_category = None

    # 6. Synchronize into Context Graph
    await RepoContextSyncService.sync_findings_to_context_graph(
        session=session,
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        project_id=uuid.UUID(project_id),
        scan=scan,
        findings=db_findings,
        repo=repo,
    )

    # 7. Audit Log
    audit = AuditLog(
        tenant_id=uuid.UUID(tenant_ctx.tenant_id),
        user_id=uuid.UUID(tenant_ctx.user_id),
        action="github.repository_scan_completed",
        resource_type="repository_scan",
        resource_id=str(scan.id),
        details={
            "commit_sha": inspection.commit_sha,
            "findings_count": len(inspection.findings),
            "files_analyzed": inspection.files_analyzed_count,
        },
    )
    session.add(audit)
    await session.flush()
    await session.refresh(scan)

    return ScanDetailResponse(
        id=str(scan.id),
        tenant_id=str(scan.tenant_id),
        project_id=str(scan.project_id),
        repository_id=str(scan.repository_id),
        commit_sha=scan.commit_sha,
        branch=scan.branch,
        status=scan.status,
        files_analyzed_count=scan.files_analyzed_count,
        findings_count=scan.findings_count,
        duration_ms=scan.duration_ms,
        error_category=scan.error_category,
        error_message=scan.error_message,
        scan_summary=scan.scan_summary,
        created_at=scan.created_at.isoformat(),
        completed_at=scan.completed_at.isoformat() if scan.completed_at else None,
    )


@router.get(
    "/projects/{project_id}/repositories/{repository_id}/scans",
    response_model=list[ScanDetailResponse],
)
async def list_repository_scans(
    tenant_id: str,
    project_id: str,
    repository_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[ScanDetailResponse]:
    """Lists historical scan runs for a repository."""
    res = await session.execute(
        select(RepositoryScan)
        .where(
            RepositoryScan.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
            RepositoryScan.project_id == uuid.UUID(project_id),
            RepositoryScan.repository_id == uuid.UUID(repository_id),
        )
        .order_by(RepositoryScan.created_at.desc())
    )
    scans = res.scalars().all()
    return [
        ScanDetailResponse(
            id=str(s.id),
            tenant_id=str(s.tenant_id),
            project_id=str(s.project_id),
            repository_id=str(s.repository_id),
            commit_sha=s.commit_sha,
            branch=s.branch,
            status=s.status,
            files_analyzed_count=s.files_analyzed_count,
            findings_count=s.findings_count,
            duration_ms=s.duration_ms,
            error_category=s.error_category,
            error_message=s.error_message,
            scan_summary=s.scan_summary,
            created_at=s.created_at.isoformat(),
            completed_at=s.completed_at.isoformat() if s.completed_at else None,
        )
        for s in scans
    ]


@router.get(
    "/projects/{project_id}/scans/{scan_id}",
    response_model=ScanDetailResponse,
)
async def get_scan_detail(
    tenant_id: str,
    project_id: str,
    scan_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ScanDetailResponse:
    """Returns details and summary metrics of a repository scan."""
    res = await session.execute(
        select(RepositoryScan).where(
            RepositoryScan.id == uuid.UUID(scan_id),
            RepositoryScan.project_id == uuid.UUID(project_id),
            RepositoryScan.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    scan = res.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found.")

    return ScanDetailResponse(
        id=str(scan.id),
        tenant_id=str(scan.tenant_id),
        project_id=str(scan.project_id),
        repository_id=str(scan.repository_id),
        commit_sha=scan.commit_sha,
        branch=scan.branch,
        status=scan.status,
        files_analyzed_count=scan.files_analyzed_count,
        findings_count=scan.findings_count,
        duration_ms=scan.duration_ms,
        error_category=scan.error_category,
        error_message=scan.error_message,
        scan_summary=scan.scan_summary,
        created_at=scan.created_at.isoformat(),
        completed_at=scan.completed_at.isoformat() if scan.completed_at else None,
    )


@router.get(
    "/projects/{project_id}/scans/{scan_id}/findings",
    response_model=list[FindingResponse],
)
async def list_scan_findings(
    tenant_id: str,
    project_id: str,
    scan_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[FindingResponse]:
    """Returns granular, evidence-backed findings for a repository scan."""
    res = await session.execute(
        select(RepositoryFinding)
        .where(
            RepositoryFinding.scan_id == uuid.UUID(scan_id),
            RepositoryFinding.project_id == uuid.UUID(project_id),
            RepositoryFinding.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
        .order_by(RepositoryFinding.created_at.asc())
    )
    findings = res.scalars().all()
    return [
        FindingResponse(
            id=str(f.id),
            finding_id=f.finding_id,
            category=f.category,
            severity=f.severity,
            title=f.title,
            description=f.description,
            confidence=f.confidence,
            verification_status=f.verification_status,
            file_path=f.file_path,
            line_start=f.line_start,
            line_end=f.line_end,
            evidence_excerpt=f.evidence_excerpt,
            commit_sha=f.commit_sha,
            rule_id=f.rule_id,
            recommended_action=f.recommended_action,
            created_at=f.created_at.isoformat(),
        )
        for f in findings
    ]


@router.post(
    "/projects/{project_id}/scans/{scan_id}/create-plan",
    response_model=dict[str, Any],
    status_code=status.HTTP_201_CREATED,
)
async def create_plan_from_scan(
    tenant_id: str,
    project_id: str,
    scan_id: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Converts repository intelligence findings into a reviewable execution plan."""
    if not tenant_ctx.can_mutate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role not permitted to create execution plans.",
        )

    res = await session.execute(
        select(RepositoryScan).where(
            RepositoryScan.id == uuid.UUID(scan_id),
            RepositoryScan.project_id == uuid.UUID(project_id),
            RepositoryScan.tenant_id == uuid.UUID(tenant_ctx.tenant_id),
        )
    )
    scan = res.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found.")

    try:
        plan = await RepoContextSyncService.generate_plan_from_findings(
            session=session,
            tenant_id=uuid.UUID(tenant_ctx.tenant_id),
            project_id=uuid.UUID(project_id),
            scan=scan,
            user_id=uuid.UUID(tenant_ctx.user_id),
        )
        return {
            "id": str(plan.id),
            "tenant_id": str(plan.tenant_id),
            "project_id": str(plan.project_id),
            "version": plan.version,
            "status": plan.status,
            "goal": plan.goal,
            "plan_source": plan.plan_source,
            "plan_data": plan.plan_data,
            "created_at": plan.created_at.isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate plan from scan findings: {e!s}",
        ) from e
