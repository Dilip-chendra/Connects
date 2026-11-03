"""Durable workflow state machine, task lifecycle validation, and DAG dependency graph rules."""

from enum import Enum


class TaskStatus(str, Enum):
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    MANUAL_HANDOFF = "manual_handoff"


class WorkflowStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorClassification(str, Enum):
    TRANSIENT = "transient"  # Network timeout, 429 rate limit -> Safe for retry
    FATAL = "fatal"  # Bad credentials, 400 validation error -> Block immediately
    MANUAL_REQUIRED = "manual"  # Needs user intervention or guided handoff


class InvalidStateTransitionError(Exception):
    """Raised when attempting an unauthorized or illogical task/workflow transition."""


class DependencyCycleError(Exception):
    """Raised when a task dependency creates a circular graph loop."""


# Strict allowed transitions for tasks
TASK_PERMITTED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PLANNED: {TaskStatus.READY, TaskStatus.CANCELLED},
    TaskStatus.READY: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.AWAITING_APPROVAL,
        TaskStatus.VERIFYING,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.MANUAL_HANDOFF,
        TaskStatus.CANCELLED,
    },
    TaskStatus.AWAITING_APPROVAL: {TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.VERIFYING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.FAILED: {TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.MANUAL_HANDOFF: {TaskStatus.VERIFYING, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),  # Terminal
    TaskStatus.BLOCKED: set(),  # Terminal
    TaskStatus.CANCELLED: set(),  # Terminal
}


class TaskLifecycleManager:
    """Enforces deterministic task state transitions, retry limits, and crash recovery rules."""

    @staticmethod
    def validate_transition(current_status: TaskStatus, target_status: TaskStatus) -> None:
        """Validates that a transition between states is permissible."""
        permitted = TASK_PERMITTED_TRANSITIONS.get(current_status, set())
        if target_status not in permitted:
            raise InvalidStateTransitionError(
                f"Invalid task transition from '{current_status.value}' to '{target_status.value}'. "
                f"Allowed target states: {[s.value for s in permitted]}"
            )

    @staticmethod
    def handle_failure(
        current_retries: int,
        max_retries: int,
        error_type: ErrorClassification,
    ) -> tuple[TaskStatus, bool]:
        """Calculates next status and whether a retry should be scheduled based on error classification."""
        if error_type == ErrorClassification.FATAL:
            return TaskStatus.BLOCKED, False

        if error_type == ErrorClassification.MANUAL_REQUIRED:
            return TaskStatus.MANUAL_HANDOFF, False

        # Transient error
        if current_retries < max_retries:
            return TaskStatus.READY, True
        else:
            return TaskStatus.BLOCKED, False


class DependencyGraphValidator:
    """Validates Directed Acyclic Graph (DAG) constraints for task dependencies."""

    @staticmethod
    def detect_cycles(adjacency_list: dict[str, list[str]]) -> None:
        """Performs Depth-First Search (DFS) with 3-color marking to detect cycles in task dependencies.

        adjacency_list: maps task_id -> list of task_ids that must complete before this task.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        colors: dict[str, int] = {node: WHITE for node in adjacency_list}

        def visit(node: str, path: list[str]) -> None:
            colors[node] = GRAY
            for neighbor in adjacency_list.get(node, []):
                if colors.get(neighbor) == GRAY:
                    cycle = " -> ".join(path + [neighbor])
                    raise DependencyCycleError(
                        f"Dependency cycle detected in workflow DAG: {cycle}"
                    )
                if colors.get(neighbor) == WHITE:
                    visit(neighbor, path + [neighbor])
            colors[node] = BLACK

        for node in adjacency_list:
            if colors[node] == WHITE:
                visit(node, [node])
