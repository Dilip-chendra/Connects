"""Synchronizes Repository Inspection Findings into Business Context Graph and Execution Plans."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    AuditLog,
    BusinessContextEdge,
    BusinessContextNode,
    ConnectedRepository,
    ExecutionPlan,
    Project,
    RepositoryFinding,
    RepositoryScan,
)
from src.domain.planning.schemas import PlanMilestoneSchema, PlanTaskSchema
from src.domain.workflows.state_machine import DependencyGraphValidator


class RepoContextSyncService:
    """Bridges repository intelligence findings into the Business Context Graph and Planner."""

    @staticmethod
    async def sync_findings_to_context_graph(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        scan: RepositoryScan,
        findings: list[RepositoryFinding],
        repo: ConnectedRepository,
    ) -> int:
        """Upserts Context Graph nodes and edges representing repository intelligence."""
        nodes_created = 0

        # 1. Ensure or update repository node
        repo_node_key = f"repo:{repo.owner}/{repo.name}"
        res = await session.execute(
            select(BusinessContextNode).where(
                BusinessContextNode.tenant_id == tenant_id,
                BusinessContextNode.project_id == project_id,
                BusinessContextNode.key == repo_node_key,
            )
        )
        repo_node = res.scalar_one_or_none()
        if not repo_node:
            repo_node = BusinessContextNode(
                tenant_id=tenant_id,
                project_id=project_id,
                node_type="repository",
                key=repo_node_key,
                version=1,
                is_verified=True,
                data={
                    "owner": repo.owner,
                    "name": repo.name,
                    "html_url": repo.html_url,
                    "default_branch": repo.default_branch,
                    "latest_commit_sha": scan.commit_sha,
                },
                source_attribution=f"github_scan:{scan.id}",
            )
            session.add(repo_node)
            await session.flush()
            nodes_created += 1
        else:
            repo_node.data = {
                **repo_node.data,
                "latest_commit_sha": scan.commit_sha,
                "last_scanned_at": scan.created_at.isoformat(),
            }
            repo_node.version += 1
            await session.flush()

        # 2. Check for project's primary goal node to link SUPPORTS_GOAL
        goal_res = await session.execute(
            select(BusinessContextNode).where(
                BusinessContextNode.tenant_id == tenant_id,
                BusinessContextNode.project_id == project_id,
                BusinessContextNode.node_type == "goal",
            )
        )
        goal_node = goal_res.scalar_one_or_none()
        if goal_node:
            # Create SUPPORTS_GOAL edge from repo to goal if not existing
            edge_res = await session.execute(
                select(BusinessContextEdge).where(
                    BusinessContextEdge.tenant_id == tenant_id,
                    BusinessContextEdge.project_id == project_id,
                    BusinessContextEdge.source_node_id == repo_node.id,
                    BusinessContextEdge.target_node_id == goal_node.id,
                    BusinessContextEdge.relationship_type == "SUPPORTS_GOAL",
                )
            )
            if not edge_res.scalar_one_or_none():
                session.add(
                    BusinessContextEdge(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        source_node_id=repo_node.id,
                        target_node_id=goal_node.id,
                        relationship_type="SUPPORTS_GOAL",
                    )
                )

        # 3. Create/update nodes for observed technologies
        tech_summary = scan.scan_summary.get("technologies", {})
        for category, items in tech_summary.items():
            for item in items:
                tech_key = f"tech:{category}:{item.lower().replace(' ', '_')}"
                t_res = await session.execute(
                    select(BusinessContextNode).where(
                        BusinessContextNode.tenant_id == tenant_id,
                        BusinessContextNode.project_id == project_id,
                        BusinessContextNode.key == tech_key,
                    )
                )
                t_node = t_res.scalar_one_or_none()
                if not t_node:
                    t_node = BusinessContextNode(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        node_type="technology",
                        key=tech_key,
                        version=1,
                        is_verified=True,
                        data={"category": category, "name": item, "commit_sha": scan.commit_sha},
                        source_attribution=f"github_scan:{scan.id}",
                    )
                    session.add(t_node)
                    await session.flush()
                    nodes_created += 1

                    # Add IMPLEMENTS edge: tech -> repo
                    session.add(
                        BusinessContextEdge(
                            tenant_id=tenant_id,
                            project_id=project_id,
                            source_node_id=t_node.id,
                            target_node_id=repo_node.id,
                            relationship_type="IMPLEMENTS",
                        )
                    )

        # 4. Create nodes for high-severity gaps / missing requirements
        for finding in findings:
            if finding.severity in ("high", "critical", "medium") and finding.verification_status != "OBSERVED":
                gap_key = f"gap:{finding.category}:{finding.rule_id.lower()}"
                g_res = await session.execute(
                    select(BusinessContextNode).where(
                        BusinessContextNode.tenant_id == tenant_id,
                        BusinessContextNode.project_id == project_id,
                        BusinessContextNode.key == gap_key,
                    )
                )
                g_node = g_res.scalar_one_or_none()
                if not g_node:
                    g_node = BusinessContextNode(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        node_type="requirement",
                        key=gap_key,
                        version=1,
                        is_verified=False,
                        data={
                            "title": finding.title,
                            "description": finding.description,
                            "severity": finding.severity,
                            "recommended_action": finding.recommended_action,
                        },
                        source_attribution=f"github_finding:{finding.finding_id}",
                    )
                    session.add(g_node)
                    await session.flush()
                    nodes_created += 1

                    # Add REQUIRES edge: repo -> requirement
                    session.add(
                        BusinessContextEdge(
                            tenant_id=tenant_id,
                            project_id=project_id,
                            source_node_id=repo_node.id,
                            target_node_id=g_node.id,
                            relationship_type="REQUIRES",
                        )
                    )

        return nodes_created

    @staticmethod
    async def generate_plan_from_findings(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        scan: RepositoryScan,
        user_id: uuid.UUID,
    ) -> ExecutionPlan:
        """Synthesizes repository intelligence findings into a proposed execution plan for founder review."""
        # Load project
        proj_res = await session.execute(
            select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
        )
        project = proj_res.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found.")

        # Load findings for scan
        f_res = await session.execute(
            select(RepositoryFinding).where(
                RepositoryFinding.scan_id == scan.id, RepositoryFinding.tenant_id == tenant_id
            )
        )
        findings = f_res.scalars().all()

        tasks: list[PlanTaskSchema] = []
        task_counter = 1

        # Task 1: Verify Codebase Baseline (Internal Capability)
        t1_id = f"task_{task_counter}"
        tasks.append(
            PlanTaskSchema(
                id=t1_id,
                title="Verify Repository Metadata & Scanned Commit",
                description=f"Validate project alignment with repository commit {scan.commit_sha[:8]} on branch '{scan.branch}'.",
                task_type="validate_project_metadata",
                prerequisites=[],
                execution_capability="internal:metadata_validator",
                is_supported_internally=True,
                expected_output="Verified repository linkage in project context graph.",
                verification_criteria="Repository node present with status=verified.",
                estimated_effort="5m",
                risk_classification="low",
                requires_approval=False,
            )
        )
        prev_task_id = t1_id
        task_counter += 1

        # Check for Security Gaps
        sec_findings = [f for f in findings if f.category == "security" and f.severity in ("critical", "high")]
        if sec_findings:
            t_sec_id = f"task_{task_counter}"
            tasks.append(
                PlanTaskSchema(
                    id=t_sec_id,
                    title="Remediate Committed Secret Findings & Git Configuration",
                    description=(
                        f"Review and rotate {len(sec_findings)} sensitive credential or gitignore findings identified "
                        "during repository scan."
                    ),
                    task_type="manual_handoff",
                    prerequisites=[prev_task_id],
                    execution_capability="security:secret_remediation",
                    is_supported_internally=False,
                    missing_capability_reason="Sensitive credential revocation and git history rewrite require founder manual intervention.",
                    expected_output="Revocation of exposed keys and updated .gitignore committed.",
                    verification_criteria="Clean repository scan without critical secret patterns.",
                    estimated_effort="30m",
                    risk_classification="high",
                    requires_approval=True,
                )
            )
            prev_task_id = t_sec_id
            task_counter += 1

        # Check for Environment Variable Configuration
        env_findings = [f for f in findings if f.category == "deployment" and "env" in f.finding_id.lower()]
        t_env_id = f"task_{task_counter}"
        tasks.append(
            PlanTaskSchema(
                id=t_env_id,
                title="Configure Production Environment Variables",
                description=(
                    f"Establish verified runtime environment variables based on {len(env_findings)} template observation(s)."
                    if env_findings
                    else "Establish verified runtime environment variables based on repository manifests and templates."
                ),
                task_type="check_required_config",
                prerequisites=[prev_task_id],
                execution_capability="internal:config_checker",
                is_supported_internally=True,
                expected_output="Environment configuration checklist populated.",
                verification_criteria="All required keys declared in .env.example are satisfied.",
                estimated_effort="15m",
                risk_classification="medium",
                requires_approval=True,
            )
        )
        prev_task_id = t_env_id
        task_counter += 1

        # Check for Automated Testing Setup
        test_missing = any(f.finding_id == "TEST-SUITE-MISSING" for f in findings)
        if test_missing:
            t_test_id = f"task_{task_counter}"
            tasks.append(
                PlanTaskSchema(
                    id=t_test_id,
                    title="Implement Automated Test Suite",
                    description="Write automated test specifications for critical application entry points.",
                    task_type="manual_handoff",
                    prerequisites=[prev_task_id],
                    execution_capability="testing:test_suite_setup",
                    is_supported_internally=False,
                    missing_capability_reason="Automated test suite creation requires codebase test implementation.",
                    expected_output="Passing test suite configuration in repository.",
                    verification_criteria="Test runner configuration and test files committed.",
                    estimated_effort="1h",
                    risk_classification="medium",
                    requires_approval=False,
                )
            )
            prev_task_id = t_test_id
            task_counter += 1

        # Task: Generate Launch Checklist (Internal Capability)
        t_launch_id = f"task_{task_counter}"
        tasks.append(
            PlanTaskSchema(
                id=t_launch_id,
                title="Generate Launch-Readiness Checklist",
                description="Synthesize repository findings and project requirements into a pre-flight launch readiness checklist.",
                task_type="generate_launch_checklist",
                prerequisites=[prev_task_id],
                execution_capability="internal:launch_checklist",
                is_supported_internally=True,
                expected_output="Pre-flight verification checklist generated in context graph.",
                verification_criteria="Launch readiness node created with criteria itemized.",
                estimated_effort="5m",
                risk_classification="low",
                requires_approval=False,
            )
        )
        prev_task_id = t_launch_id
        task_counter += 1

        # Final Verification Task (Internal Capability)
        t_verif_id = f"task_{task_counter}"
        tasks.append(
            PlanTaskSchema(
                id=t_verif_id,
                title="Verify Repository Intelligence Integration",
                description="Confirm all repository observations, technologies, and requirements are recorded in project context.",
                task_type="verify_internal_record",
                prerequisites=[prev_task_id],
                execution_capability="internal:record_verifier",
                is_supported_internally=True,
                expected_output="Final verification report recorded in PostgreSQL.",
                verification_criteria="Context graph verification assertion returns PASS.",
                estimated_effort="5m",
                risk_classification="low",
                requires_approval=False,
            )
        )

        # Validate DAG
        adjacency = {t.id: t.prerequisites for t in tasks}
        DependencyGraphValidator.detect_cycles(adjacency)

        # Build Milestones
        milestones = [
            PlanMilestoneSchema(
                id="m1_security_and_config",
                title="Security & Configuration Hygiene",
                description="Resolve secret risks and configure production environment variables.",
                task_ids=[t.id for t in tasks[:3]],
            ),
            PlanMilestoneSchema(
                id="m2_launch_preparation",
                title="Launch Preparation & Verification",
                description="Finalize pre-flight checklist and verify context graph records.",
                task_ids=[t.id for t in tasks[3:]],
            ),
        ]

        # Determine version
        ver_res = await session.execute(
            select(ExecutionPlan.version)
            .where(ExecutionPlan.project_id == project_id, ExecutionPlan.tenant_id == tenant_id)
            .order_by(ExecutionPlan.version.desc())
            .limit(1)
        )
        last_version = ver_res.scalar_one_or_none() or 0
        new_version = last_version + 1

        plan_data = {
            "goal": f"Repository Launch Readiness: {project.primary_goal}",
            "desiredOutcome": "Resolve repository gaps, configure deployment readiness, and establish verified project context.",
            "planningSource": "repo_intelligence_planner_v1",
            "version": new_version,
            "assumptions": [
                f"Repository scan commit {scan.commit_sha[:8]} represents the deployment target.",
                "External manual tasks will be verified prior to production launch.",
            ],
            "missingInformation": [
                f.title for f in findings if f.verification_status == "NOT_FOUND_IN_SCANNED_SCOPE"
            ],
            "milestones": [m.model_dump() for m in milestones],
            "tasks": [t.model_dump() for t in tasks],
            "requiredCapabilities": list({t.execution_capability for t in tasks}),
            "approvalGates": [t.title for t in tasks if t.requires_approval],
            "acceptanceCriteria": [
                "All secret findings remediated and verified.",
                "Production environment variables configured.",
                "Launch checklist successfully generated and reviewed.",
            ],
            "metadata": {
                "scan_id": str(scan.id),
                "commit_sha": scan.commit_sha,
                "readiness_score": scan.scan_summary.get("readiness_score", 100),
            },
        }

        plan = ExecutionPlan(
            tenant_id=tenant_id,
            project_id=project_id,
            version=new_version,
            status="draft",
            goal=f"Launch Readiness for {project.name}",
            plan_source="repo_intelligence_planner_v1",
            plan_data=plan_data,
            created_by=user_id,
        )
        session.add(plan)

        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="plan.generated_from_repo_scan",
            resource_type="execution_plan",
            resource_id=str(plan.id),
            details={"scan_id": str(scan.id), "commit_sha": scan.commit_sha, "version": new_version},
        )
        session.add(audit)
        await session.flush()
        await session.refresh(plan)

        return plan
