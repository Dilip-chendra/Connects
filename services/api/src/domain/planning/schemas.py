"""Schemas and data models for Goal Decomposition and Execution Plans."""

from typing import Any

from pydantic import BaseModel, Field


class PlanTaskSchema(BaseModel):
    id: str = Field(description="Stable identifier within plan, e.g. task-1")
    title: str
    description: str
    task_type: str
    prerequisites: list[str] = Field(default_factory=list)
    execution_capability: str
    is_supported_internally: bool = True
    missing_capability_reason: str | None = None
    expected_output: str
    verification_criteria: str
    estimated_effort: str | None = None
    risk_classification: str = Field(default="low")  # low, medium, high
    requires_approval: bool = False
    status: str = Field(default="planned")


class PlanMilestoneSchema(BaseModel):
    id: str
    title: str
    description: str
    task_ids: list[str] = Field(default_factory=list)


class ExecutionPlanData(BaseModel):
    goal: str
    desired_outcome: str
    planning_source: str = Field(default="rule_based")  # rule_based, etc.
    version: int = 1
    assumptions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    milestones: list[PlanMilestoneSchema] = Field(default_factory=list)
    tasks: list[PlanTaskSchema] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    approval_gates: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
