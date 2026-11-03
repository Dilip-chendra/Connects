"""Tests for durable workflow state transitions, retry limits, and DAG cycle validation."""

import pytest

from src.domain.workflows.state_machine import (
    DependencyCycleError,
    DependencyGraphValidator,
    ErrorClassification,
    InvalidStateTransitionError,
    TaskLifecycleManager,
    TaskStatus,
)


def test_valid_task_lifecycle_transitions() -> None:
    # PLANNED -> READY -> RUNNING -> VERIFYING -> COMPLETED
    TaskLifecycleManager.validate_transition(TaskStatus.PLANNED, TaskStatus.READY)
    TaskLifecycleManager.validate_transition(TaskStatus.READY, TaskStatus.RUNNING)
    TaskLifecycleManager.validate_transition(TaskStatus.RUNNING, TaskStatus.VERIFYING)
    TaskLifecycleManager.validate_transition(TaskStatus.VERIFYING, TaskStatus.COMPLETED)


def test_approval_workflow_transitions() -> None:
    # RUNNING -> AWAITING_APPROVAL -> RUNNING
    TaskLifecycleManager.validate_transition(TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL)
    TaskLifecycleManager.validate_transition(TaskStatus.AWAITING_APPROVAL, TaskStatus.RUNNING)


def test_invalid_task_transition_rejected() -> None:
    # Cannot jump directly from PLANNED to COMPLETED without executing
    with pytest.raises(InvalidStateTransitionError):
        TaskLifecycleManager.validate_transition(TaskStatus.PLANNED, TaskStatus.COMPLETED)

    # Terminal state COMPLETED cannot transition to anything
    with pytest.raises(InvalidStateTransitionError):
        TaskLifecycleManager.validate_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)

    # Terminal state BLOCKED cannot transition to READY
    with pytest.raises(InvalidStateTransitionError):
        TaskLifecycleManager.validate_transition(TaskStatus.BLOCKED, TaskStatus.READY)


def test_failure_handling_and_retry_limits() -> None:
    # 1. Transient error with retry attempts remaining -> READY, retry=True
    status, retry = TaskLifecycleManager.handle_failure(
        current_retries=1, max_retries=3, error_type=ErrorClassification.TRANSIENT
    )
    assert status == TaskStatus.READY
    assert retry is True

    # 2. Transient error with retries exhausted -> BLOCKED, retry=False
    status, retry = TaskLifecycleManager.handle_failure(
        current_retries=3, max_retries=3, error_type=ErrorClassification.TRANSIENT
    )
    assert status == TaskStatus.BLOCKED
    assert retry is False

    # 3. Fatal error (e.g. invalid credentials) -> BLOCKED immediately, retry=False
    status, retry = TaskLifecycleManager.handle_failure(
        current_retries=0, max_retries=3, error_type=ErrorClassification.FATAL
    )
    assert status == TaskStatus.BLOCKED
    assert retry is False

    # 4. Manual intervention required -> MANUAL_HANDOFF, retry=False
    status, retry = TaskLifecycleManager.handle_failure(
        current_retries=0, max_retries=3, error_type=ErrorClassification.MANUAL_REQUIRED
    )
    assert status == TaskStatus.MANUAL_HANDOFF
    assert retry is False


def test_dag_acyclic_graph_passes() -> None:
    valid_dag = {
        "repo_scan": [],
        "env_setup": ["repo_scan"],
        "code_patch": ["env_setup"],
        "deploy": ["code_patch"],
        "verify": ["deploy"],
    }
    # Should not raise
    DependencyGraphValidator.detect_cycles(valid_dag)


def test_dag_direct_cycle_detected() -> None:
    circular_dag = {
        "task_a": ["task_b"],
        "task_b": ["task_a"],
    }
    with pytest.raises(DependencyCycleError, match="Dependency cycle detected"):
        DependencyGraphValidator.detect_cycles(circular_dag)


def test_dag_deep_cycle_detected() -> None:
    deep_circular_dag = {
        "task_1": ["task_3"],
        "task_2": ["task_1"],
        "task_3": ["task_2"],
    }
    with pytest.raises(DependencyCycleError, match="Dependency cycle detected"):
        DependencyGraphValidator.detect_cycles(deep_circular_dag)
