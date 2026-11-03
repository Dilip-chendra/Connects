'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  Play,
  XCircle,
  ShieldAlert,
  AlertTriangle,
  Layers,
  Cpu,
  ArrowRight,
  ExternalLink,
  Loader2,
  Info,
  CheckSquare,
  HelpCircle,
  Sparkles,
} from 'lucide-react';
import { ExecutionPlanDetail, PlanTask } from '@connects/shared';
import { api } from '@/lib/api';
import { Navbar } from '@/components/Navbar';

export default function PlanDetailPage() {
  const params = useParams();
  const router = useRouter();
  const tenantId = params.tenantId as string;
  const projectId = params.projectId as string;
  const planId = params.planId as string;

  const [plan, setPlan] = useState<ExecutionPlanDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const loadPlan = async () => {
    try {
      setLoading(true);
      const data = await api.plans.get(tenantId, projectId, planId);
      setPlan(data);
    } catch (err: any) {
      if (err.status === 401) {
        router.push('/login');
        return;
      }
      setError(err.message || 'Failed to load execution plan.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPlan();
  }, [tenantId, projectId, planId]);

  const handleApprove = async () => {
    setActionLoading(true);
    setError(null);
    try {
      const updated = await api.plans.approve(tenantId, projectId, planId);
      setPlan(updated);
      setSuccessMsg('Plan approved successfully. Ready for workflow execution.');
    } catch (err: any) {
      setError(err.message || 'Failed to approve plan.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!confirm('Are you sure you want to reject this execution plan?')) return;
    setActionLoading(true);
    setError(null);
    try {
      const updated = await api.plans.reject(tenantId, projectId, planId);
      setPlan(updated);
      setSuccessMsg('Plan marked as rejected.');
    } catch (err: any) {
      setError(err.message || 'Failed to reject plan.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleExecute = async () => {
    setActionLoading(true);
    setError(null);
    try {
      const wf = await api.workflows.executePlan(tenantId, projectId, planId);
      router.push(`/workspaces/${tenantId}/projects/${projectId}/workflows/${wf.id}`);
    } catch (err: any) {
      setError(err.message || 'Failed to start workflow execution.');
      setActionLoading(false);
    }
  };

  const planData = (plan?.planData || (plan as any)?.plan_data) || {};
  const tasks: PlanTask[] = planData.tasks || [];
  const milestones = planData.milestones || [];
  const assumptions: string[] = planData.assumptions || [];
  const missingInfo: string[] = planData.missingInformation || (planData as any).missing_information || [];
  const approvalGates: string[] = planData.approvalGates || (planData as any).approval_gates || [];
  const acceptanceCriteria: string[] = planData.acceptanceCriteria || (planData as any).acceptance_criteria || [];

  return (
    <div className="min-h-screen bg-surface-ground text-slate-100 flex flex-col font-sans">
      <Navbar tenantId={tenantId} />

      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        {/* Back navigation */}
        <div className="mb-6">
          <Link
            href={`/workspaces/${tenantId}/projects/${projectId}`}
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Project
          </Link>
        </div>

        {error && (
          <div className="mb-6 p-4 rounded-xl bg-red-950/40 border border-red-800 text-red-200 text-sm flex items-center gap-3">
            <XCircle className="w-5 h-5 text-red-400 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {successMsg && (
          <div className="mb-6 p-4 rounded-xl bg-emerald-950/40 border border-emerald-800 text-emerald-200 text-sm flex items-center gap-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}

        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-400">
            <Loader2 className="w-8 h-8 animate-spin text-brand-blue mb-4" />
            <p className="text-sm">Loading execution plan...</p>
          </div>
        ) : !plan ? (
          <div className="p-8 text-center bg-surface rounded-xl border border-surface-border">
            <p className="text-slate-400">Plan not found.</p>
          </div>
        ) : (
          <div className="space-y-8">
            {/* Plan Header */}
            <div className="p-6 rounded-2xl bg-surface border border-surface-border flex flex-col md:flex-row md:items-center justify-between gap-6 shadow-sm">
              <div className="space-y-2">
                <div className="flex items-center gap-2.5">
                  <span className="font-mono text-xs px-2.5 py-1 rounded bg-surface-muted text-slate-300 border border-surface-border">
                    v{plan.version}
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium uppercase tracking-wider ${
                      plan.status === 'approved'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                        : plan.status === 'rejected'
                        ? 'bg-red-500/10 text-red-400 border border-red-500/30'
                        : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                    }`}
                  >
                    {plan.status === 'approved' ? (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    ) : plan.status === 'rejected' ? (
                      <XCircle className="w-3.5 h-3.5" />
                    ) : (
                      <Clock className="w-3.5 h-3.5" />
                    )}
                    {plan.status}
                  </span>
                  <span className="text-xs text-slate-400 font-mono">
                    ID: {plan.id.slice(0, 8)}...
                  </span>
                </div>
                <h1 className="text-2xl font-bold text-white tracking-tight">
                  Execution Plan: {plan.goal}
                </h1>
                <p className="text-xs text-slate-400">
                  Created {new Date(plan.createdAt || (plan as any).created_at).toLocaleString()}
                  {plan.approvedAt && ` • Approved ${new Date(plan.approvedAt).toLocaleString()}`}
                </p>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-3 shrink-0">
                {(plan.status === 'draft' || plan.status === 'reviewed') && (
                  <>
                    <button
                      onClick={handleReject}
                      disabled={actionLoading}
                      className="px-4 py-2 rounded-lg border border-red-900/50 bg-red-950/20 hover:bg-red-950/40 text-red-300 text-xs font-medium transition-colors disabled:opacity-50"
                    >
                      Reject Plan
                    </button>
                    <button
                      onClick={handleApprove}
                      disabled={actionLoading}
                      className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition-colors flex items-center gap-1.5 shadow-md shadow-emerald-900/20 disabled:opacity-50"
                    >
                      {actionLoading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <CheckCircle2 className="w-4 h-4" />
                      )}
                      Approve Plan
                    </button>
                  </>
                )}

                {plan.status === 'approved' && (
                  <button
                    onClick={handleExecute}
                    disabled={actionLoading}
                    className="px-5 py-2.5 rounded-lg bg-brand-blue hover:bg-brand-blue/90 text-white text-xs font-semibold transition-all flex items-center gap-2 shadow-md shadow-brand-blue/30 disabled:opacity-50"
                  >
                    {actionLoading ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Play className="w-4 h-4 fill-white" />
                    )}
                    Start Workflow Execution
                  </button>
                )}
              </div>
            </div>

            {/* Source Transparency Banner */}
            <div className="p-4 rounded-xl bg-brand-blue/10 border border-brand-blue/20 text-xs flex items-start gap-3">
              <Info className="w-5 h-5 text-brand-cyan shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-brand-cyan">
                  Planning Engine:{' '}
                  <span className="font-mono text-white">
                    {plan.planSource || (plan as any).plan_source || 'rule_based_planner_v1'}
                  </span>
                </p>
                <p className="text-slate-300 mt-0.5">
                  This execution plan was generated transparently by the deterministic graph planner.
                  Tasks mapped to internal capabilities execute durably inside the engine; external actions
                  are paused at explicit manual founder handoffs or approval gates.
                </p>
              </div>
            </div>

            {/* Main Content Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              {/* Left 2 Cols: Ordered Tasks */}
              <div className="lg:col-span-2 space-y-6">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                    <Layers className="w-4 h-4 text-brand-cyan" />
                    Execution Tasks ({tasks.length})
                  </h2>
                  <span className="text-xs text-slate-400">
                    Acyclic DAG sequence with explicit dependencies
                  </span>
                </div>

                <div className="space-y-4">
                  {tasks.map((task, idx) => {
                    const isSupported = task.isSupportedInternally ?? (task as any).is_supported_internally;
                    const requiresApproval = task.requiresApproval ?? (task as any).requires_approval;
                    const risk = task.riskClassification || (task as any).risk_classification || 'low';
                    const prereqs = task.prerequisites || [];

                    return (
                      <div
                        key={task.id || idx}
                        className="p-5 rounded-xl bg-surface border border-surface-border hover:border-slate-700 transition-all space-y-3"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-xs font-mono px-2 py-0.5 rounded bg-surface-muted text-slate-400 border border-surface-border">
                                #{idx + 1}
                              </span>
                              <h3 className="text-sm font-semibold text-white">
                                {task.title}
                              </h3>
                              {requiresApproval && (
                                <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
                                  <ShieldAlert className="w-3 h-3" />
                                  Approval Required
                                </span>
                              )}
                              <span
                                className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded font-mono font-semibold ${
                                  risk === 'high'
                                    ? 'bg-red-500/15 text-red-400 border border-red-500/30'
                                    : risk === 'medium'
                                    ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                                    : 'bg-slate-700/50 text-slate-300 border border-slate-600'
                                }`}
                              >
                                {risk} risk
                              </span>
                            </div>
                            <p className="text-xs text-slate-300">
                              {task.description}
                            </p>
                          </div>

                          <div className="shrink-0 text-right">
                            {isSupported ? (
                              <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                <Cpu className="w-3 h-3" />
                                Internal Capability
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                                <AlertTriangle className="w-3 h-3" />
                                Manual Handoff
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Task Metadata & Verification details */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3 border-t border-surface-border text-xs">
                          <div>
                            <span className="text-slate-400 font-medium block mb-1">Expected Output:</span>
                            <p className="text-slate-200 font-mono text-[11px] bg-surface-ground p-2 rounded border border-surface-border">
                              {task.expectedOutput || (task as any).expected_output || 'Structured status report'}
                            </p>
                          </div>
                          <div>
                            <span className="text-slate-400 font-medium block mb-1">Verification Criteria:</span>
                            <p className="text-slate-200 font-mono text-[11px] bg-surface-ground p-2 rounded border border-surface-border">
                              {task.verificationCriteria || (task as any).verification_criteria || 'Internal deterministic assert'}
                            </p>
                          </div>
                        </div>

                        {/* Prerequisites and capability tags */}
                        <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                          <div className="flex items-center gap-2">
                            <span>Capability:</span>
                            <span className="font-mono text-brand-cyan">
                              {task.executionCapability || (task as any).execution_capability}
                            </span>
                          </div>
                          {prereqs.length > 0 && (
                            <div className="flex items-center gap-1.5">
                              <span>Prerequisites:</span>
                              <span className="font-mono text-slate-300">
                                {prereqs.join(', ')}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Right Col: Plan Governance & Governance Metadata */}
              <div className="space-y-6">
                {/* Desired Outcome */}
                <div className="p-5 rounded-xl bg-surface border border-surface-border space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Desired Outcome
                  </h3>
                  <p className="text-sm text-slate-200 leading-relaxed">
                    {planData.desiredOutcome || (planData as any).desired_outcome || plan.goal}
                  </p>
                </div>

                {/* Approval Gates */}
                {approvalGates.length > 0 && (
                  <div className="p-5 rounded-xl bg-surface border border-amber-900/30 space-y-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                      <ShieldAlert className="w-4 h-4" />
                      Approval Gates
                    </h3>
                    <ul className="space-y-2">
                      {approvalGates.map((gate, i) => (
                        <li key={i} className="text-xs text-slate-300 flex items-start gap-2">
                          <span className="text-amber-400 shrink-0 mt-0.5">•</span>
                          <span>{gate}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Acceptance Criteria */}
                {acceptanceCriteria.length > 0 && (
                  <div className="p-5 rounded-xl bg-surface border border-surface-border space-y-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                      <CheckSquare className="w-4 h-4 text-emerald-400" />
                      Acceptance Criteria
                    </h3>
                    <ul className="space-y-2">
                      {acceptanceCriteria.map((crit, i) => (
                        <li key={i} className="text-xs text-slate-300 flex items-start gap-2">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                          <span>{crit}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Assumptions */}
                {assumptions.length > 0 && (
                  <div className="p-5 rounded-xl bg-surface border border-surface-border space-y-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                      <HelpCircle className="w-4 h-4 text-brand-blue" />
                      Planning Assumptions
                    </h3>
                    <ul className="space-y-2">
                      {assumptions.map((assump, i) => (
                        <li key={i} className="text-xs text-slate-300 flex items-start gap-2">
                          <span className="text-brand-cyan shrink-0 mt-0.5">•</span>
                          <span>{assump}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
