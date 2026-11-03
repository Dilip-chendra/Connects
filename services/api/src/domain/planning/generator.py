"""Provider-independent planning engine and deterministic rule-based goal decomposition."""

from abc import ABC, abstractmethod
from typing import Any

from src.domain.planning.schemas import ExecutionPlanData, PlanMilestoneSchema, PlanTaskSchema
from src.domain.workflows.state_machine import DependencyGraphValidator


class PlanGenerator(ABC):
    """Abstract interface for goal decomposition and plan generation engines."""

    @abstractmethod
    async def generate_plan(
        self,
        goal: str,
        project_context: dict[str, Any] | None = None,
    ) -> ExecutionPlanData:
        """Decomposes a founder's business goal into a structured, validated execution plan."""


class RuleBasedPlanGenerator(PlanGenerator):
    """Deterministic, transparent rule-based planner for local execution.

    Never simulates AI and accurately labels its planning source as 'rule_based'.
    """

    async def generate_plan(
        self,
        goal: str,
        project_context: dict[str, Any] | None = None,
    ) -> ExecutionPlanData:
        normalized_goal = goal.lower()

        tasks: list[PlanTaskSchema] = []
        milestones: list[PlanMilestoneSchema] = []
        assumptions: list[str] = [
            "Project metadata and primary business goal are explicitly provided by the user.",
            "Supported internal task capabilities execute directly against local database and context storage.",
            "External provider integrations requiring third-party credentials will pause for manual founder handoff.",
        ]
        missing_information: list[str] = []
        required_capabilities: list[str] = ["internal:core", "internal:context", "internal:verification"]
        approval_gates: list[str] = []
        acceptance_criteria: list[str] = [
            "All project metadata validated and verified.",
            "Business context nodes populated and linked.",
            "Launch readiness checklist evaluated and confirmed.",
        ]

        # Milestone 1: Workspace & Context Foundation (All supported internally)
        tasks.append(
            PlanTaskSchema(
                id="task-1",
                title="Validate Project Metadata",
                description="Inspect project records to ensure goal clarity, category assignment, and ownership validity.",
                task_type="validate_project_metadata",
                prerequisites=[],
                execution_capability="internal:core",
                is_supported_internally=True,
                expected_output="Verified project configuration record.",
                verification_criteria="Project record contains non-empty name, category, and primary goal.",
                risk_classification="low",
                requires_approval=False,
            )
        )
        tasks.append(
            PlanTaskSchema(
                id="task-2",
                title="Validate Plan Structure and DAG",
                description="Verify dependency tree integrity, check for cyclic loops, and confirm prerequisite order.",
                task_type="validate_plan_structure",
                prerequisites=["task-1"],
                execution_capability="internal:core",
                is_supported_internally=True,
                expected_output="Acyclic dependency confirmation proof.",
                verification_criteria="Topological sort succeeds with 0 cyclic edges.",
                risk_classification="low",
                requires_approval=False,
            )
        )
        tasks.append(
            PlanTaskSchema(
                id="task-3",
                title="Establish Project Business Context Nodes",
                description="Create typed context entities (goal, requirements, constraints) in the persistent graph.",
                task_type="create_context_record",
                prerequisites=["task-2"],
                execution_capability="internal:context",
                is_supported_internally=True,
                expected_output="Business context nodes persisted in PostgreSQL.",
                verification_criteria="Nodes queryable via project context API.",
                risk_classification="low",
                requires_approval=False,
            )
        )

        milestones.append(
            PlanMilestoneSchema(
                id="ms-1",
                title="Foundation & Context Setup",
                description="Validates metadata and stores initial business context nodes.",
                task_ids=["task-1", "task-2", "task-3"],
            )
        )

        # Milestone 2: Domain-specific capabilities (Payment / Hosting / Marketing)
        m2_task_ids: list[str] = []
        last_prereq = "task-3"

        has_payment = any(k in normalized_goal for k in ["payment", "stripe", "monetiz", "subscript", "bill", "price", "revenue"])
        has_deploy = any(k in normalized_goal for k in ["deploy", "host", "domain", "ssl", "launch website", "production"])

        if has_payment:
            required_capabilities.append("internal:pricing")
            required_capabilities.append("external:stripe")
            tasks.append(
                PlanTaskSchema(
                    id="task-4",
                    title="Configure Pricing & Monetization Catalog",
                    description="Define subscription tiers, pricing intervals, and quota entitlements in project context.",
                    task_type="create_context_record",
                    prerequisites=[last_prereq],
                    execution_capability="internal:pricing",
                    is_supported_internally=True,
                    expected_output="Pricing plan context node recorded.",
                    verification_criteria="Pricing node contains valid currency, interval, and price points.",
                    risk_classification="medium",
                    requires_approval=False,
                )
            )
            tasks.append(
                PlanTaskSchema(
                    id="task-5",
                    title="Connect Payment Gateway (Stripe)",
                    description="Configure Stripe API credentials and webhook endpoints.",
                    task_type="create_manual_handoff",
                    prerequisites=["task-4"],
                    execution_capability="external:stripe",
                    is_supported_internally=False,
                    missing_capability_reason="Live Stripe Connect connector is scheduled for Phase 3. Manual founder handoff required with guided instructions.",
                    expected_output="Guided handoff instructions with required webhook endpoints.",
                    verification_criteria="Founder confirms payment gateway setup in dashboard.",
                    risk_classification="high",
                    requires_approval=False,
                )
            )
            m2_task_ids.extend(["task-4", "task-5"])
            last_prereq = "task-5"
            missing_information.append("Stripe API keys and webhook signing secret not yet connected.")

        if has_deploy:
            required_capabilities.append("external:deployment")
            tasks.append(
                PlanTaskSchema(
                    id="task-6",
                    title="Configure Production Deployment Target",
                    description="Prepare deployment environment configuration, custom domains, and SSL settings.",
                    task_type="create_manual_handoff",
                    prerequisites=[last_prereq],
                    execution_capability="external:deployment",
                    is_supported_internally=False,
                    missing_capability_reason="Automated deployment connector is scheduled for future phase. Guided manual handoff provided.",
                    expected_output="Deployment environment parameter checklist.",
                    verification_criteria="Production URL reachable via HTTP probe.",
                    risk_classification="medium",
                    requires_approval=False,
                )
            )
            m2_task_ids.append("task-6")
            last_prereq = "task-6"
            missing_information.append("Production hosting provider credentials not yet configured.")

        if m2_task_ids:
            milestones.append(
                PlanMilestoneSchema(
                    id="ms-2",
                    title="Integrations & Configuration",
                    description="Coordinates business operations and external service requirements.",
                    task_ids=m2_task_ids,
                )
            )

        # Milestone 3: Launch Readiness, Human Approval & Verification
        tasks.append(
            PlanTaskSchema(
                id="task-7",
                title="Generate Launch-Readiness Checklist",
                description="Compile launch readiness report by evaluating completed tasks and stored business context.",
                task_type="generate_launch_checklist",
                prerequisites=["task-3"],
                execution_capability="internal:core",
                is_supported_internally=True,
                expected_output="Structured launch readiness evaluation matrix.",
                verification_criteria="Checklist contains 100% evaluated items with zero unreviewed high-risk blockers.",
                risk_classification="low",
                requires_approval=False,
            )
        )
        tasks.append(
            PlanTaskSchema(
                id="task-8",
                title="Founder Launch Approval Gate",
                description="Requires human founder sign-off before marking the project workflow ready for launch.",
                task_type="request_human_approval",
                prerequisites=["task-7"],
                execution_capability="internal:approval",
                is_supported_internally=True,
                expected_output="Recorded founder approval decision in audit log.",
                verification_criteria="Approval decision record signed by authenticated workspace admin/owner.",
                risk_classification="high",
                requires_approval=True,
            )
        )
        approval_gates.append("task-8 (Founder Launch Approval Gate)")

        tasks.append(
            PlanTaskSchema(
                id="task-9",
                title="Verify Project Records and Outcomes",
                description="Execute automated assertions validating internal integrity and audit completeness.",
                task_type="verify_internal_record",
                prerequisites=["task-8"],
                execution_capability="internal:verification",
                is_supported_internally=True,
                expected_output="Cryptographic verification record with status 'passed'.",
                verification_criteria="Verification record timestamped and linked to workflow.",
                risk_classification="low",
                requires_approval=False,
            )
        )

        milestones.append(
            PlanMilestoneSchema(
                id="ms-3",
                title="Launch Verification & Sign-off",
                description="Evaluates checklist, secures human approval, and confirms verified status.",
                task_ids=["task-7", "task-8", "task-9"],
            )
        )

        # Validate DAG acyclicity before returning
        adjacency: dict[str, list[str]] = {t.id: t.prerequisites for t in tasks}
        DependencyGraphValidator.detect_cycles(adjacency)

        return ExecutionPlanData(
            goal=goal,
            desired_outcome=f"Successfully prepare and verify startup launch workflow for: {goal}",
            planning_source="rule_based",
            version=1,
            assumptions=assumptions,
            missing_information=missing_information,
            milestones=milestones,
            tasks=tasks,
            required_capabilities=required_capabilities,
            approval_gates=approval_gates,
            acceptance_criteria=acceptance_criteria,
            metadata={"planner_algorithm": "deterministic_heuristic_v1"},
        )
