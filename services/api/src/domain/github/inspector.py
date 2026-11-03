"""Repository Inspection and Deterministic Intelligence Engine.

Performs read-only, commit-pinned analysis of connected GitHub repositories,
detecting frameworks, application structure, testing readiness, database setup,
deployment configuration, and security posture with strictly verifiable evidence.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from src.core.logging import logger
from src.domain.github.client import GitHubClient


@dataclass
class FindingDraft:
    finding_id: str
    category: str
    severity: str
    title: str
    description: str
    confidence: str
    verification_status: str
    rule_id: str
    recommended_action: str
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    evidence_excerpt: str | None = None


@dataclass
class InspectionResult:
    commit_sha: str
    branch: str
    files_analyzed_count: int
    findings: list[FindingDraft]
    scan_summary: dict[str, Any]
    duration_ms: int


# Denylist of sensitive file patterns that must NEVER be fetched or analyzed
SENSITIVE_FILE_PATTERNS = [
    re.compile(r"^\.env($|\..*)", re.IGNORECASE),  # .env, .env.local, .env.production (NOT .env.example)
    re.compile(r".*\.(pem|key|pkcs12|pfx|p12|kdbx)$", re.IGNORECASE),
    re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)($|\..*)", re.IGNORECASE),
    re.compile(r".*(credential|secret|password|token).*\.(json|yaml|yml|txt)$", re.IGNORECASE),
    re.compile(r".*\.(exe|dll|so|dylib|bin|zip|tar|gz|7z|rar|pyc|class)$", re.IGNORECASE),
]

# High-priority files to inspect for deterministic technology and architecture detection
PRIORITY_MANIFEST_PATHS = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "requirements.txt",
    "Pipfile",
    "setup.py",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "alembic.ini",
    "prisma/schema.prisma",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "vercel.json",
    "render.yaml",
    "Procfile",
    ".gitignore",
    ".env.example",
    ".env.template",
    "README.md",
    "pytest.ini",
    "jest.config.js",
    "jest.config.ts",
    "vitest.config.ts",
    "vitest.config.js",
}

# Regex for common secret patterns (redacted immediately upon match)
SECRET_DETECTORS = [
    (
        "SEC-PAT-AWS",
        "AWS Access Key ID",
        re.compile(r"(?<![A-Z0-9])[A-Z0-9]{20}(?![A-Z0-9])"),
        lambda s: s.startswith(("AKIA", "ASIA")),
    ),
    (
        "SEC-PAT-STRIPE",
        "Stripe API Secret Key",
        re.compile(r"sk_(live|test)_[0-9a-zA-Z]{24,99}"),
        lambda _: True,
    ),
    (
        "SEC-PAT-GITHUB",
        "GitHub Personal Access Token",
        re.compile(r"gh[pousr]_[0-9a-zA-Z]{36,255}"),
        lambda _: True,
    ),
    (
        "SEC-PAT-PRIVATE-KEY",
        "Unencrypted Private Key Block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        lambda _: True,
    ),
]


def redact_secret_string(val: str) -> str:
    """Safely redacts a matched secret leaving only prefix and asterisks."""
    if len(val) <= 8:
        return "****"
    return f"{val[:4]}...****"


class RepositoryInspector:
    """Isolated, read-only repository analysis engine."""

    MAX_ANALYSIS_FILES = 80
    MAX_FILE_BYTES = 100_000  # 100 KB max content fetch per file

    def __init__(self, github_client: GitHubClient) -> None:
        self.github = github_client

    def is_sensitive_file(self, path: str) -> bool:
        """Determines if a file path matches secret or binary denylists."""
        filename = path.split("/")[-1]
        # .env.example and .env.template are safe configuration templates
        if filename in (".env.example", ".env.template", ".env.sample"):
            return False
        for pat in SENSITIVE_FILE_PATTERNS:
            if pat.match(filename) or pat.match(path):
                return True
        return False

    async def inspect(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        selected_branch: str = "main",
    ) -> InspectionResult:
        """Executes a full, commit-pinned deterministic scan of the repository."""
        start_time = datetime.now(UTC)

        # 1. Resolve selected branch to exact commit SHA
        branch_info = await self.github.get_branch(
            installation_id, owner, repo, selected_branch
        )
        commit_sha = branch_info["commit"]["sha"]

        # 2. Fetch Git tree for this exact commit SHA
        raw_tree, is_truncated = await self.github.get_tree(
            installation_id, owner, repo, commit_sha, recursive=True
        )

        all_paths = [item["path"] for item in raw_tree if item.get("type") == "blob"]
        tree_by_path = {item["path"]: item for item in raw_tree if item.get("type") == "blob"}

        findings: list[FindingDraft] = []
        analyzed_count = 0

        # Handle Truncation Notice if repository is extremely large
        if is_truncated:
            findings.append(
                FindingDraft(
                    finding_id="REPO-TREE-TRUNCATED",
                    category="application_structure",
                    severity="medium",
                    title="Large Repository: Git Tree Truncated",
                    description=(
                        "The repository contains more files than GitHub's recursive tree API limit. "
                        "Connects performed bounded analysis of available top-level and manifest files."
                    ),
                    confidence="high",
                    verification_status="OBSERVED",
                    rule_id="RULE-BOUNDED-TREE",
                    recommended_action="Ensure key application entry points and manifests reside in the root or standard subdirectories.",
                )
            )

        # 3. Categorize & Select Priority Files for Content Inspection
        selected_paths: list[str] = []
        for path in all_paths:
            if self.is_sensitive_file(path):
                # Flag committed sensitive file without reading its contents!
                findings.append(
                    FindingDraft(
                        finding_id=f"SEC-SENSITIVE-COMMITTED-{path.replace('/', '-')[:50]}",
                        category="security",
                        severity="high",
                        title=f"Committed Sensitive File: {path}",
                        description=f"File '{path}' appears to be a sensitive credential, private key, or environment store committed to version control.",
                        confidence="high",
                        verification_status="OBSERVED",
                        file_path=path,
                        rule_id="RULE-SEC-COMMITTED-FILE",
                        recommended_action=f"Remove '{path}' from git history and add it to .gitignore.",
                    )
                )
                continue

            # Prioritize manifests, configs, and workflow files
            if (
                path in PRIORITY_MANIFEST_PATHS
                or path.startswith(".github/workflows/")
                or (path.endswith((".py", ".ts", ".js", ".json", ".toml", ".yml", ".yaml")) and path.count("/") <= 2)
            ) and len(selected_paths) < self.MAX_ANALYSIS_FILES:
                selected_paths.append(path)

        # 4. Fetch content and analyze selected priority files
        file_contents: dict[str, str] = {}
        for path in selected_paths:
            item = tree_by_path.get(path)
            if not item:
                continue

            file_size = item.get("size", 0)
            if file_size > self.MAX_FILE_BYTES:
                continue

            file_sha = item.get("sha")
            if not file_sha:
                continue

            try:
                content = await self.github.get_blob_content(
                    installation_id, owner, repo, file_sha
                )
                if content:
                    file_contents[path] = content
                    analyzed_count += 1
            except (httpx.HTTPError, UnicodeDecodeError, ValueError) as e:
                logger.warning(f"Could not fetch blob for {path} ({file_sha}): {e!s}")

        # 5. Execute Deterministic Analyzers
        tech_summary: dict[str, Any] = {
            "languages": set(),
            "frameworks": set(),
            "database": set(),
            "deployment": set(),
            "testing": set(),
        }

        # Analyze .gitignore
        self._analyze_gitignore(all_paths, file_contents, findings)

        # Analyze Node / JavaScript / TypeScript manifests
        self._analyze_node_ecosystem(all_paths, file_contents, findings, tech_summary)

        # Analyze Python manifests
        self._analyze_python_ecosystem(all_paths, file_contents, findings, tech_summary)

        # Analyze Database & Migrations
        self._analyze_database(all_paths, file_contents, findings, tech_summary)

        # Analyze Deployment & Infrastructure
        self._analyze_deployment(all_paths, file_contents, findings, tech_summary)

        # Analyze Testing Infrastructure
        self._analyze_testing(all_paths, file_contents, findings, tech_summary)

        # Scan for committed secret patterns inside fetched text files
        self._scan_for_secret_patterns(file_contents, findings)

        # 6. Synthesize Summary
        duration = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
        scan_summary = {
            "commit_sha": commit_sha,
            "branch": selected_branch,
            "total_files_discovered": len(all_paths),
            "files_analyzed": analyzed_count,
            "findings_count": len(findings),
            "technologies": {
                k: sorted(v) if isinstance(v, set) else v for k, v in tech_summary.items()
            },
            "readiness_score": self._calculate_readiness_score(findings),
        }

        return InspectionResult(
            commit_sha=commit_sha,
            branch=selected_branch,
            files_analyzed_count=analyzed_count,
            findings=findings,
            scan_summary=scan_summary,
            duration_ms=duration,
        )

    def _analyze_gitignore(
        self, all_paths: list[str], contents: dict[str, str], findings: list[FindingDraft]
    ) -> None:
        if ".gitignore" not in all_paths:
            findings.append(
                FindingDraft(
                    finding_id="SEC-GITIGNORE-MISSING",
                    category="security",
                    severity="medium",
                    title="Missing .gitignore File",
                    description="The repository does not contain a root .gitignore file. Sensitive files or build artifacts may accidentally be committed.",
                    confidence="high",
                    verification_status="OBSERVED",
                    rule_id="RULE-SEC-GITIGNORE",
                    recommended_action="Create a root .gitignore file excluding node_modules, .venv, .env, and local build artifacts.",
                )
            )
        else:
            git_content = contents.get(".gitignore", "")
            if ".env" not in git_content:
                findings.append(
                    FindingDraft(
                        finding_id="SEC-GITIGNORE-NO-ENV",
                        category="security",
                        severity="medium",
                        title=".gitignore Does Not Ignore .env",
                        description="Root .gitignore does not explicitly exclude .env files. Local secrets may be at risk of being committed.",
                        confidence="medium",
                        verification_status="OBSERVED",
                        file_path=".gitignore",
                        rule_id="RULE-SEC-GITIGNORE-ENV",
                        recommended_action="Add '.env' and '.env.*' (except .env.example) to .gitignore.",
                    )
                )

    def _analyze_node_ecosystem(
        self,
        all_paths: list[str],
        contents: dict[str, str],
        findings: list[FindingDraft],
        tech_summary: dict[str, Any],
    ) -> None:
        if "package.json" not in contents:
            return

        tech_summary["languages"].add("JavaScript / TypeScript")
        raw_pkg = contents["package.json"]
        try:
            pkg = json.loads(raw_pkg)
        except (json.JSONDecodeError, ValueError):
            return

        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        scripts = pkg.get("scripts", {})

        # Framework detection
        if "next" in deps:
            tech_summary["frameworks"].add("Next.js")
            findings.append(
                FindingDraft(
                    finding_id="TECH-FRAMEWORK-NEXTJS",
                    category="application_structure",
                    severity="info",
                    title="Next.js Application Framework Detected",
                    description=f"Project declares Next.js version '{deps.get('next')}' in package.json.",
                    confidence="high",
                    verification_status="OBSERVED",
                    file_path="package.json",
                    evidence_excerpt=f'"next": "{deps.get("next")}"',
                    rule_id="RULE-TECH-NEXTJS",
                    recommended_action="Validate Next.js build scripts and environment variables.",
                )
            )

        if "react" in deps:
            tech_summary["frameworks"].add("React")

        if "express" in deps:
            tech_summary["frameworks"].add("Express")
            findings.append(
                FindingDraft(
                    finding_id="TECH-FRAMEWORK-EXPRESS",
                    category="application_structure",
                    severity="info",
                    title="Express.js Web Framework Detected",
                    description=f"Project declares Express.js version '{deps.get('express')}' in package.json.",
                    confidence="high",
                    verification_status="OBSERVED",
                    file_path="package.json",
                    rule_id="RULE-TECH-EXPRESS",
                    recommended_action="Ensure Express server port is configurable via process.env.PORT.",
                )
            )

        # Build script check
        if "build" in scripts:
            findings.append(
                FindingDraft(
                    finding_id="APP-BUILD-SCRIPT-OBSERVED",
                    category="application_structure",
                    severity="info",
                    title="Build Script Configured",
                    description=f"package.json defines a build script: '{scripts.get('build')}'.",
                    confidence="high",
                    verification_status="OBSERVED",
                    file_path="package.json",
                    evidence_excerpt=f'"build": "{scripts.get("build")}"',
                    rule_id="RULE-APP-BUILD-SCRIPT",
                    recommended_action="Verify build command produces clean production bundle without warnings.",
                )
            )
        else:
            findings.append(
                FindingDraft(
                    finding_id="APP-BUILD-SCRIPT-MISSING",
                    category="application_structure",
                    severity="medium",
                    title="Missing 'build' Script in package.json",
                    description="No 'build' script found in package.json. Automated deployment pipelines may fail.",
                    confidence="high",
                    verification_status="OBSERVED",
                    file_path="package.json",
                    rule_id="RULE-APP-NO-BUILD",
                    recommended_action="Define a 'build' script in package.json for production bundling.",
                )
            )

    def _analyze_python_ecosystem(
        self,
        all_paths: list[str],
        contents: dict[str, str],
        findings: list[FindingDraft],
        tech_summary: dict[str, Any],
    ) -> None:
        has_py = any(p.endswith(".py") for p in all_paths) or "pyproject.toml" in all_paths or "requirements.txt" in all_paths
        if not has_py:
            return

        tech_summary["languages"].add("Python")
        reqs = contents.get("requirements.txt", "")
        pyproject = contents.get("pyproject.toml", "")
        combined = f"{reqs}\n{pyproject}".lower()

        if "fastapi" in combined:
            tech_summary["frameworks"].add("FastAPI")
            findings.append(
                FindingDraft(
                    finding_id="TECH-FRAMEWORK-FASTAPI",
                    category="application_structure",
                    severity="info",
                    title="FastAPI Web Framework Detected",
                    description="FastAPI dependency observed in Python manifest files.",
                    confidence="high",
                    verification_status="OBSERVED",
                    file_path="pyproject.toml" if "fastapi" in pyproject.lower() else "requirements.txt",
                    rule_id="RULE-TECH-FASTAPI",
                    recommended_action="Verify API route documentation (/docs) and health endpoints.",
                )
            )

        if "django" in combined:
            tech_summary["frameworks"].add("Django")

        if "sqlalchemy" in combined:
            tech_summary["database"].add("SQLAlchemy")

    def _analyze_database(
        self,
        all_paths: list[str],
        contents: dict[str, str],
        findings: list[FindingDraft],
        tech_summary: dict[str, Any],
    ) -> None:
        has_alembic = "alembic.ini" in all_paths or any("alembic" in p for p in all_paths)
        has_prisma = any(p.startswith("prisma/") for p in all_paths)

        if has_alembic:
            tech_summary["database"].add("Alembic")
            findings.append(
                FindingDraft(
                    finding_id="DB-MIGRATIONS-ALEMBIC",
                    category="database",
                    severity="info",
                    title="Alembic Database Migrations Detected",
                    description="Alembic configuration and migration directories observed in repository.",
                    confidence="high",
                    verification_status="OBSERVED",
                    file_path="alembic.ini" if "alembic.ini" in all_paths else None,
                    rule_id="RULE-DB-ALEMBIC",
                    recommended_action="Ensure all schema changes are backed by reproducible Alembic migrations.",
                )
            )

        if has_prisma:
            tech_summary["database"].add("Prisma")
            findings.append(
                FindingDraft(
                    finding_id="DB-MIGRATIONS-PRISMA",
                    category="database",
                    severity="info",
                    title="Prisma ORM & Migrations Detected",
                    description="Prisma schema directory observed in repository.",
                    confidence="high",
                    verification_status="OBSERVED",
                    file_path="prisma/schema.prisma" if "prisma/schema.prisma" in all_paths else None,
                    rule_id="RULE-DB-PRISMA",
                    recommended_action="Verify prisma migrate status against target database environment.",
                )
            )

        # Detect database docker services
        docker_compose = contents.get("docker-compose.yml") or contents.get("docker-compose.yaml", "")
        if "postgres" in docker_compose.lower():
            tech_summary["database"].add("PostgreSQL")
        if "redis" in docker_compose.lower():
            tech_summary["database"].add("Redis")

    def _analyze_deployment(
        self,
        all_paths: list[str],
        contents: dict[str, str],
        findings: list[FindingDraft],
        tech_summary: dict[str, Any],
    ) -> None:
        if "Dockerfile" in all_paths:
            tech_summary["deployment"].add("Docker")
            findings.append(
                FindingDraft(
                    finding_id="DEPLOY-DOCKERFILE-OBSERVED",
                    category="deployment",
                    severity="info",
                    title="Containerization: Dockerfile Detected",
                    description="Root Dockerfile observed for reproducible container builds.",
                    confidence="high",
                    verification_status="OBSERVED",
                    file_path="Dockerfile",
                    rule_id="RULE-DEPLOY-DOCKER",
                    recommended_action="Test local container build and run commands.",
                )
            )
        else:
            findings.append(
                FindingDraft(
                    finding_id="DEPLOY-DOCKERFILE-ABSENT",
                    category="deployment",
                    severity="low",
                    title="No Dockerfile Observed in Scanned Scope",
                    description="No Dockerfile was detected in the root directory. If deploying to container environments, a Dockerfile may be required.",
                    confidence="medium",
                    verification_status="NOT_FOUND_IN_SCANNED_SCOPE",
                    rule_id="RULE-DEPLOY-NO-DOCKER",
                    recommended_action="Consider adding a Dockerfile if deploying to cloud container platforms like AWS ECS, GCP Cloud Run, or Render.",
                )
            )

        if "docker-compose.yml" in all_paths or "docker-compose.yaml" in all_paths:
            tech_summary["deployment"].add("Docker Compose")

        # Environment variable template
        if ".env.example" in all_paths or ".env.template" in all_paths:
            env_file = ".env.example" if ".env.example" in all_paths else ".env.template"
            raw_env = contents.get(env_file, "")
            lines = [line.split("=")[0].strip() for line in raw_env.splitlines() if "=" in line and not line.strip().startswith("#")]
            findings.append(
                FindingDraft(
                    finding_id="CONFIG-ENV-TEMPLATE-OBSERVED",
                    category="deployment",
                    severity="info",
                    title="Environment Variables Template Configured",
                    description=f"{env_file} defines {len(lines)} configuration variables for deployment.",
                    confidence="high",
                    verification_status="OBSERVED",
                    file_path=env_file,
                    evidence_excerpt=", ".join(lines[:6]) + ("..." if len(lines) > 6 else ""),
                    rule_id="RULE-CONFIG-ENV-TEMPLATE",
                    recommended_action="Ensure production environment variables are provided before launching.",
                )
            )
        else:
            findings.append(
                FindingDraft(
                    finding_id="CONFIG-ENV-TEMPLATE-MISSING",
                    category="deployment",
                    severity="medium",
                    title="Missing .env.example Template",
                    description="No .env.example or configuration template was observed. Required launch variables may be undocumented.",
                    confidence="medium",
                    verification_status="NOT_FOUND_IN_SCANNED_SCOPE",
                    rule_id="RULE-CONFIG-NO-ENV-EXAMPLE",
                    recommended_action="Create .env.example documenting all required environment variables.",
                )
            )

    def _analyze_testing(
        self,
        all_paths: list[str],
        contents: dict[str, str],
        findings: list[FindingDraft],
        tech_summary: dict[str, Any],
    ) -> None:
        test_files = [p for p in all_paths if "test" in p.lower() or "spec" in p.lower()]
        has_ci_workflows = any(p.startswith(".github/workflows/") for p in all_paths)

        if test_files:
            tech_summary["testing"].add(f"{len(test_files)} test file(s)")
            findings.append(
                FindingDraft(
                    finding_id="TEST-SUITE-FILES-OBSERVED",
                    category="testing",
                    severity="info",
                    title="Automated Test Suite Files Observed",
                    description=f"Discovered {len(test_files)} test/spec files in repository.",
                    confidence="high",
                    verification_status="OBSERVED",
                    evidence_excerpt=", ".join(test_files[:3]) + ("..." if len(test_files) > 3 else ""),
                    rule_id="RULE-TEST-FILES",
                    recommended_action="Run automated tests in CI/CD pipeline prior to deployment.",
                )
            )
            # Crucial honest boundary: finding tests does NOT mean tests pass!
            findings.append(
                FindingDraft(
                    finding_id="TEST-EXECUTION-UNVERIFIED",
                    category="testing",
                    severity="low",
                    title="Test Pass/Fail Status Unverified",
                    description="Connects observed test files, but does not execute arbitrary repository code. Test pass/fail status is unverified.",
                    confidence="high",
                    verification_status="UNVERIFIED",
                    rule_id="RULE-TEST-EXEC-STATUS",
                    recommended_action="Configure a continuous integration test runner to verify test results.",
                )
            )
        else:
            findings.append(
                FindingDraft(
                    finding_id="TEST-SUITE-MISSING",
                    category="testing",
                    severity="high",
                    title="No Automated Test Suite Observed in Scanned Scope",
                    description="No test files or framework configurations were detected. Deploying without automated tests presents significant risk.",
                    confidence="medium",
                    verification_status="NOT_FOUND_IN_SCANNED_SCOPE",
                    rule_id="RULE-TEST-MISSING",
                    recommended_action="Establish automated unit and integration tests before launching.",
                )
            )

        if has_ci_workflows:
            tech_summary["deployment"].add("GitHub Actions")
            findings.append(
                FindingDraft(
                    finding_id="DEPLOY-CI-WORKFLOWS-OBSERVED",
                    category="deployment",
                    severity="info",
                    title="GitHub Actions CI/CD Configured",
                    description="GitHub Actions workflow definitions observed under .github/workflows/.",
                    confidence="high",
                    verification_status="OBSERVED",
                    rule_id="RULE-DEPLOY-GHA",
                    recommended_action="Verify GitHub Actions runs pass on pull requests and pushes.",
                )
            )

    def _scan_for_secret_patterns(
        self, contents: dict[str, str], findings: list[FindingDraft]
    ) -> None:
        """Scans analyzed file contents for secret patterns, redacting all evidence."""
        for path, text in contents.items():
            lines = text.splitlines()
            for line_idx, line in enumerate(lines, start=1):
                # Ignore comment lines that document placeholders
                if any(k in line.lower() for k in ("example", "placeholder", "replace_with", "your_")):
                    continue

                for rule_id, desc, regex, validator in SECRET_DETECTORS:
                    match = regex.search(line)
                    if match:
                        matched_str = match.group(0)
                        if validator(matched_str):
                            redacted_evidence = redact_secret_string(matched_str)
                            findings.append(
                                FindingDraft(
                                    finding_id=f"SEC-SECRET-MATCH-{rule_id}-{path.replace('/', '-')[:30]}-{line_idx}",
                                    category="security",
                                    severity="critical",
                                    title=f"Potential Secret Committed: {desc}",
                                    description=f"Potential unredacted credential matching pattern '{desc}' found in '{path}' at line {line_idx}.",
                                    confidence="high",
                                    verification_status="NEEDS_REVIEW",
                                    file_path=path,
                                    line_start=line_idx,
                                    line_end=line_idx,
                                    evidence_excerpt=f"Matched pattern: {redacted_evidence}",
                                    rule_id=rule_id,
                                    recommended_action="Immediately revoke and rotate this secret, then remove it from git history.",
                                )
                            )
                            # Once found on a line, continue to next line
                            break

    def _calculate_readiness_score(self, findings: list[FindingDraft]) -> int:
        """Calculates a 0-100 launch readiness indicator based on observed gaps and severity."""
        score = 100
        for f in findings:
            if f.severity == "critical":
                score -= 30
            elif f.severity == "high":
                score -= 15
            elif f.severity == "medium":
                score -= 8
            elif f.severity == "low":
                score -= 3
        return max(0, min(100, score))
