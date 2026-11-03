/**
 * Connects Shared Type Definitions
 * Strict domain models shared across client and server abstractions.
 */

export type TenantTier = 'free' | 'individual' | 'pro' | 'team' | 'enterprise';

export type MembershipRole = 'owner' | 'admin' | 'member' | 'viewer';

export type ProjectStatus = 'draft' | 'active' | 'launched' | 'paused' | 'archived';

export type ExecutionPlanStatus =
  | 'draft'
  | 'reviewed'
  | 'approved'
  | 'rejected'
  | 'executing'
  | 'completed';

export type ContextNodeType =
  | 'goal'
  | 'requirement'
  | 'constraint'
  | 'decision'
  | 'task'
  | 'integration_requirement'
  | 'verification_requirement'
  | 'launch_criterion'
  | 'repository'
  | 'env_var'
  | 'pricing_plan'
  | 'entitlement'
  | 'endpoint';

export type ContextEdgeType =
  | 'REQUIRES'
  | 'DEPENDS_ON'
  | 'IMPLEMENTS'
  | 'VERIFIES'
  | 'BLOCKED_BY'
  | 'SUPPORTS_GOAL'
  | 'implements'
  | 'requires'
  | 'configures'
  | 'deploys'
  | 'verifies'
  | 'monetizes';

export type WorkflowStatus =
  | 'planned'
  | 'running'
  | 'paused'
  | 'awaiting_approval'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type TaskStatus =
  | 'planned'
  | 'ready'
  | 'running'
  | 'awaiting_approval'
  | 'verifying'
  | 'completed'
  | 'failed'
  | 'blocked'
  | 'cancelled'
  | 'manual_handoff';

export type VerificationType =
  | 'http_probe'
  | 'ssl_check'
  | 'webhook_ack'
  | 'test_suite'
  | 'db_assertion';

export type VerificationStatus = 'passed' | 'failed' | 'warning';

export type ApprovalStatus = 'pending' | 'approved' | 'rejected';

export type ConnectorProvider = 'github' | 'vercel' | 'render' | 'stripe' | 'razorpay';

export type ConnectorAuthType = 'oauth2' | 'api_key' | 'personal_access_token';

export type ConnectorCapability =
  | 'repo:read'
  | 'repo:write'
  | 'deploy:trigger'
  | 'deploy:read'
  | 'payment:read'
  | 'payment:write'
  | 'payment:mutate'
  | 'monitor:read';

export interface TenantSummary {
  id: string;
  name: string;
  slug: string;
  tier: TenantTier;
  role?: MembershipRole | null;
  createdAt: string;
}

export interface UserSummary {
  id: string;
  email: string;
  fullName: string | null;
  isActive: boolean;
  memberships?: Array<{ tenant_id: string; role: string }>;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: UserSummary;
}

export interface WorkspaceMember {
  id: string;
  userId: string;
  email: string;
  fullName: string | null;
  role: MembershipRole;
  createdAt: string;
}

export interface ProjectSummary {
  id: string;
  tenantId: string;
  name: string;
  description: string | null;
  primaryGoal: string;
  category: string | null;
  targetLaunchDate: string | null;
  status: ProjectStatus;
  createdBy: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ContextNode {
  id: string;
  nodeType: string;
  key: string;
  version: number;
  isVerified: boolean;
  data: Record<string, unknown>;
  sourceAttribution: string;
  createdAt: string;
}

export interface ContextEdge {
  id: string;
  sourceNodeId: string;
  targetNodeId: string;
  relationshipType: string;
  createdAt: string;
}

export interface PlanTask {
  id: string;
  title: string;
  description: string;
  taskType: string;
  prerequisites: string[];
  executionCapability: string;
  isSupportedInternally: boolean;
  missingCapabilityReason?: string | null;
  expectedOutput: string;
  verificationCriteria: string;
  estimatedEffort?: string | null;
  riskClassification: 'low' | 'medium' | 'high';
  requiresApproval: boolean;
  status: string;
}

export interface PlanMilestone {
  id: string;
  title: string;
  description: string;
  taskIds: string[];
}

export interface ExecutionPlanData {
  goal: string;
  desiredOutcome: string;
  planningSource: string;
  version: number;
  assumptions: string[];
  missingInformation: string[];
  milestones: PlanMilestone[];
  tasks: PlanTask[];
  requiredCapabilities: string[];
  approvalGates: string[];
  acceptanceCriteria: string[];
  metadata: Record<string, unknown>;
}

export interface ExecutionPlanSummary {
  id: string;
  tenantId: string;
  projectId: string;
  version: number;
  status: ExecutionPlanStatus;
  goal: string;
  planSource: string;
  taskCount: number;
  createdAt: string;
  approvedAt: string | null;
}

export interface ExecutionPlanDetail {
  id: string;
  tenantId: string;
  projectId: string;
  version: number;
  status: ExecutionPlanStatus;
  goal: string;
  planSource: string;
  planData: ExecutionPlanData;
  createdBy: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ExecutionAttemptSummary {
  id: string;
  attemptNumber: number;
  status: string;
  errorMessage: string | null;
  outputPayload: Record<string, unknown>;
  startedAt: string;
  completedAt: string | null;
}

export interface TaskSummary {
  id: string;
  workflowExecutionId: string;
  name: string;
  description?: string | null;
  taskType: string;
  connectorId: string | null;
  status: TaskStatus;
  idempotencyKey: string;
  retryCount: number;
  maxRetries: number;
  requiresApproval: boolean;
  inputPayload?: Record<string, unknown>;
  outputPayload?: Record<string, unknown>;
  errorDetails?: Record<string, unknown> | null;
  prerequisites?: string[];
  attempts?: ExecutionAttemptSummary[];
  verificationRecords?: VerificationRecordSummary[];
  createdAt: string;
  updatedAt: string;
}

export interface VerificationRecordSummary {
  id: string;
  taskId: string;
  verificationType: VerificationType;
  status: VerificationStatus;
  evidence: Record<string, unknown>;
  timestamp: string;
}

export interface ApprovalRequestSummary {
  id: string;
  taskId: string;
  taskName?: string;
  requestedAction: string;
  impactAssessment: string;
  status: ApprovalStatus;
  reviewedBy: string | null;
  reviewedAt: string | null;
  decisionNotes: string | null;
  createdAt: string;
}

export interface WorkspaceActivityItem {
  id: string;
  action: string;
  resourceType: string;
  resourceId: string | null;
  details: Record<string, unknown>;
  createdAt: string;
}

// -----------------------------------------------------------------------------
// Phase 2: GitHub Integration & Repository Intelligence Types
// -----------------------------------------------------------------------------

export type FindingCategory =
  | 'application_structure'
  | 'testing'
  | 'database'
  | 'deployment'
  | 'security';

export type FindingSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';

export type FindingVerificationStatus =
  | 'OBSERVED'
  | 'NEEDS_REVIEW'
  | 'NOT_FOUND_IN_SCANNED_SCOPE'
  | 'UNVERIFIED';

export interface GitHubConfig {
  is_configured: boolean;
  app_name: string | null;
  install_url: string | null;
  setup_required: boolean;
}

export interface GitHubInstallation {
  id: string;
  installation_id: number;
  account_login: string;
  account_type: string;
  account_avatar_url: string | null;
  repository_selection: string;
  status: string;
  created_at: string;
}

export interface GitHubAvailableRepo {
  id: number;
  name: string;
  full_name: string;
  owner: string;
  html_url: string;
  is_private: boolean;
  default_branch: string;
  description: string | null;
}

export interface ConnectedRepository {
  id: string;
  tenant_id: string;
  project_id: string;
  installation_id: string;
  github_repo_id: number;
  owner: string;
  name: string;
  full_name: string;
  html_url: string;
  is_private: boolean;
  default_branch: string;
  selected_branch: string;
  latest_commit_sha: string | null;
  status: string;
  last_error_category: string | null;
  last_scanned_at: string | null;
  created_at: string;
}

export interface RepositoryScanSummary {
  commit_sha: string;
  branch: string;
  total_files_discovered: number;
  files_analyzed: number;
  findings_count: number;
  technologies: {
    languages?: string[];
    frameworks?: string[];
    database?: string[];
    deployment?: string[];
    testing?: string[];
  };
  readiness_score: number;
}

export interface RepositoryScan {
  id: string;
  tenant_id: string;
  project_id: string;
  repository_id: string;
  commit_sha: string;
  branch: string;
  status: string;
  files_analyzed_count: number;
  findings_count: number;
  duration_ms: number | null;
  error_category: string | null;
  error_message: string | null;
  scan_summary: RepositoryScanSummary;
  created_at: string;
  completed_at: string | null;
}

export interface RepositoryFinding {
  id: string;
  finding_id: string;
  category: FindingCategory;
  severity: FindingSeverity;
  title: string;
  description: string;
  confidence: string;
  verification_status: FindingVerificationStatus;
  file_path: string | null;
  line_start: number | null;
  line_end: number | null;
  evidence_excerpt: string | null;
  commit_sha: string;
  rule_id: string;
  recommended_action: string;
  created_at: string;
}

