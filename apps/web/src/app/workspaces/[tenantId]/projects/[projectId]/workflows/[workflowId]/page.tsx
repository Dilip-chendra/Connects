'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Play,
  RotateCw,
  XCircle,
  CheckCircle2,
  Clock,
  ShieldAlert,
  AlertTriangle,
  Cpu,
  Loader2,
  ChevronRight,
  X,
  FileJson,
  CheckCheck,
  RefreshCw,
  Terminal,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Navbar } from '@/components/Navbar';

interface TaskAttempt {
  id: string;
  attempt_number: number;
  status: string;
  error_message: string | null;
  output_payload: Record<string, unknown>;
  started_at: string;
  completed_at: string | null;
}

interface VerificationRecord {
  id?: string;
  task_id?: string;
  verification_type?: string;
  status?: string;
  evidence?: Record<string, unknown>;
  created_at?: string;
  timestamp?: string;
}

interface TaskDetail {
  id: string;
  name: string;
  description: string | null;
  task_type: string;
  connector_id: string | null;
  status: string;
  idempotency_key: string;
  retry_count: number;
  max_retries: number;
  requires_approval: boolean;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  error_details: Record<string, unknown> | null;
  prerequisites: string[];
  attempts: TaskAttempt[];
  verification_records: VerificationRecord[];
  created_at: string;
  updated_at: string;
}

interface WorkflowState {
  id: string;
  tenant_id: string;
  project_id: string;
  plan_id: string | null;
  template_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export default function WorkflowDetailPage() {
  const params = useParams();
  const router = useRouter();
  const tenantId = params.tenantId as string;
  const projectId = params.projectId as string;
  const workflowId = params.workflowId as string;

  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [tasks, setTasks] = useState<TaskDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [stepping, setStepping] = useState(false);
  const [stepResult, setStepResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Task Drawer State
  const [selectedTask, setSelectedTask] = useState<TaskDetail | null>(null);
  const [completingHandoffId, setCompletingHandoffId] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setError(null);
      const [wfData, tasksData] = await Promise.all([
        api.workflows.get(tenantId, workflowId),
        api.workflows.listTasks(tenantId, workflowId),
      ]);
      setWorkflow(wfData as unknown as WorkflowState);
      setTasks(tasksData as unknown as TaskDetail[]);

      // Update selected task in drawer if open
      if (selectedTask) {
        const updated = tasksData.find((t: any) => t.id === selectedTask.id);
        if (updated) setSelectedTask(updated as unknown as TaskDetail);
      }
    } catch (err: any) {
      if (err.status === 401) {
        router.push('/login');
        return;
      }
      setError(err.message || 'Failed to load workflow state.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [tenantId, workflowId]);

  const handleStep = async () => {
    setStepping(true);
    setStepResult(null);
    setError(null);
    try {
      const res = await api.workflows.step(tenantId, workflowId);
      setStepResult(
        `Step dispatched: status is '${res.status}'. ${res.tasks_executed} tasks executed, ${res.tasks_blocked} tasks blocked or awaiting gates.`
      );
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to step workflow.');
    } finally {
      setStepping(false);
    }
  };

  const handleCompleteHandoff = async (taskId: string) => {
    setCompletingHandoffId(taskId);
    setError(null);
    try {
      await api.workflows.completeHandoff(tenantId, workflowId, taskId);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to complete manual handoff.');
    } finally {
      setCompletingHandoffId(null);
    }
  };

  const handleCancelWorkflow = async () => {
    if (!confirm('Are you sure you want to cancel this workflow execution?')) return;
    try {
      await api.workflows.cancel(tenantId, workflowId);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to cancel workflow.');
    }
  };

  // Progress calculations
  const totalTasks = tasks.length;
  const completedTasks = tasks.filter((t) => t.status === 'completed').length;
  const progressPercent = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  return (
    <div className="min-h-screen bg-surface-ground text-slate-100 flex flex-col font-sans">
      <Navbar tenantId={tenantId} />

      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        {/* Back navigation */}
        <div className="mb-6 flex items-center justify-between">
          <Link
            href={`/workspaces/${tenantId}/projects/${projectId}`}
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Project
          </Link>

          <button
            onClick={loadData}
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white px-3 py-1.5 rounded-md bg-surface border border-surface-border transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        </div>

        {error && (
          <div className="mb-6 p-4 rounded-xl bg-red-950/40 border border-red-800 text-red-200 text-sm flex items-center gap-3">
            <XCircle className="w-5 h-5 text-red-400 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {stepResult && (
          <div className="mb-6 p-4 rounded-xl bg-brand-blue/10 border border-brand-blue/30 text-brand-cyan text-sm flex items-center gap-3">
            <Cpu className="w-5 h-5 text-brand-cyan shrink-0" />
            <span>{stepResult}</span>
          </div>
        )}

        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-400">
            <Loader2 className="w-8 h-8 animate-spin text-brand-blue mb-4" />
            <p className="text-sm">Loading workflow execution state...</p>
          </div>
        ) : !workflow ? (
          <div className="p-8 text-center bg-surface rounded-xl border border-surface-border">
            <p className="text-slate-400">Workflow execution not found.</p>
          </div>
        ) : (
          <div className="space-y-8">
            {/* Header Card */}
            <div className="p-6 rounded-2xl bg-surface border border-surface-border flex flex-col md:flex-row md:items-center justify-between gap-6 shadow-sm">
              <div className="space-y-2">
                <div className="flex items-center gap-2.5">
                  <span className="font-mono text-xs px-2.5 py-1 rounded bg-surface-muted text-slate-300 border border-surface-border">
                    Workflow
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium uppercase tracking-wider ${
                      workflow.status === 'completed'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                        : workflow.status === 'failed'
                        ? 'bg-red-500/10 text-red-400 border border-red-500/30'
                        : workflow.status === 'awaiting_approval'
                        ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                        : workflow.status === 'running'
                        ? 'bg-brand-blue/10 text-brand-cyan border border-brand-blue/30'
                        : 'bg-slate-700/50 text-slate-300 border border-slate-600'
                    }`}
                  >
                    {workflow.status === 'completed' ? (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    ) : workflow.status === 'failed' ? (
                      <XCircle className="w-3.5 h-3.5" />
                    ) : (
                      <Clock className="w-3.5 h-3.5" />
                    )}
                    {workflow.status}
                  </span>
                  <span className="text-xs text-slate-400 font-mono">
                    ID: {workflow.id.slice(0, 8)}...
                  </span>
                </div>
                <h1 className="text-2xl font-bold text-white tracking-tight">
                  {workflow.template_name || 'Execution Workflow'}
                </h1>
                <p className="text-xs text-slate-400">
                  Created {new Date(workflow.created_at).toLocaleString()}
                  {workflow.started_at && ` • Started ${new Date(workflow.started_at).toLocaleString()}`}
                  {workflow.completed_at && ` • Completed ${new Date(workflow.completed_at).toLocaleString()}`}
                </p>
              </div>

              {/* Step Controls */}
              <div className="flex items-center gap-3 shrink-0">
                {['running', 'paused'].includes(workflow.status) && (
                  <button
                    onClick={handleCancelWorkflow}
                    className="px-4 py-2 rounded-lg border border-red-900/40 bg-red-950/20 hover:bg-red-950/40 text-red-300 text-xs font-medium transition-colors"
                  >
                    Cancel
                  </button>
                )}

                {workflow.status === 'awaiting_approval' && (
                  <Link
                    href={`/workspaces/${tenantId}/approvals`}
                    className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold flex items-center gap-1.5 transition-all shadow-md shadow-amber-900/20"
                  >
                    <ShieldAlert className="w-4 h-4" />
                    Review Pending Approvals
                  </Link>
                )}

                {!['completed', 'failed', 'cancelled'].includes(workflow.status) && (
                  <button
                    onClick={handleStep}
                    disabled={stepping}
                    className="px-5 py-2.5 rounded-lg bg-brand-blue hover:bg-brand-blue/90 text-white text-xs font-semibold flex items-center gap-2 transition-all shadow-md shadow-brand-blue/30 disabled:opacity-50"
                  >
                    {stepping ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Play className="w-4 h-4 fill-white" />
                    )}
                    Step Workflow
                  </button>
                )}
              </div>
            </div>

            {/* Execution Progress Bar */}
            <div className="p-5 rounded-xl bg-surface border border-surface-border space-y-3">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-white">Execution Progress</span>
                <span className="font-mono text-brand-cyan">
                  {completedTasks} / {totalTasks} tasks completed ({progressPercent}%)
                </span>
              </div>
              <div className="w-full bg-surface-muted rounded-full h-2.5 overflow-hidden">
                <div
                  className="bg-gradient-to-r from-brand-blue to-brand-cyan h-2.5 rounded-full transition-all duration-500"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>

            {/* Tasks List */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-white">
                  Workflow Tasks ({tasks.length})
                </h2>
                <span className="text-xs text-slate-400">
                  Click any task to inspect payload and verification records
                </span>
              </div>

              <div className="space-y-3">
                {tasks.map((task, idx) => {
                  const isAwaitingApproval = task.status === 'awaiting_approval';
                  const isManualHandoff = task.status === 'manual_handoff';
                  const isCompleted = task.status === 'completed';
                  const isFailed = task.status === 'failed';

                  return (
                    <div
                      key={task.id}
                      onClick={() => setSelectedTask(task)}
                      className={`p-5 rounded-xl bg-surface border transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                        selectedTask?.id === task.id
                          ? 'border-brand-cyan ring-1 ring-brand-cyan/20'
                          : 'border-surface-border hover:border-slate-700'
                      }`}
                    >
                      <div className="space-y-1.5 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-mono text-xs px-2 py-0.5 rounded bg-surface-muted text-slate-400">
                            #{idx + 1}
                          </span>
                          <h3 className="text-sm font-semibold text-white">
                            {task.name}
                          </h3>
                          <span className="text-[11px] font-mono text-slate-400">
                            ({task.task_type})
                          </span>
                        </div>

                        {task.description && (
                          <p className="text-xs text-slate-300">
                            {task.description}
                          </p>
                        )}

                        <div className="flex items-center gap-3 text-[11px] text-slate-400 flex-wrap pt-1">
                          <span>
                            Retries: {task.retry_count} / {task.max_retries}
                          </span>
                          {task.attempts && task.attempts.length > 0 && (
                            <span>
                              Attempts: {task.attempts.length}
                            </span>
                          )}
                          {task.verification_records && task.verification_records.length > 0 && (
                            <span className="text-emerald-400 flex items-center gap-1">
                              <CheckCheck className="w-3 h-3" />
                              {task.verification_records.length} verification record(s)
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Right actions and status badge */}
                      <div className="flex items-center gap-3 shrink-0" onClick={(e) => e.stopPropagation()}>
                        {isManualHandoff && (
                          <button
                            onClick={() => handleCompleteHandoff(task.id)}
                            disabled={completingHandoffId === task.id}
                            className="px-3.5 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium transition-colors flex items-center gap-1.5 shadow-sm disabled:opacity-50"
                          >
                            {completingHandoffId === task.id ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <CheckCircle2 className="w-3.5 h-3.5" />
                            )}
                            Complete Handoff
                          </button>
                        )}

                        {isAwaitingApproval && (
                          <Link
                            href={`/workspaces/${tenantId}/approvals`}
                            className="px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-medium hover:bg-amber-500/20 transition-colors flex items-center gap-1"
                          >
                            <ShieldAlert className="w-3.5 h-3.5" />
                            Approval Gate
                          </Link>
                        )}

                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium font-mono uppercase tracking-wider ${
                            isCompleted
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                              : isFailed
                              ? 'bg-red-500/10 text-red-400 border border-red-500/30'
                              : isManualHandoff
                              ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                              : isAwaitingApproval
                              ? 'bg-amber-500/10 text-amber-300 border border-amber-500/30'
                              : task.status === 'running'
                              ? 'bg-brand-blue/15 text-brand-cyan border border-brand-blue/30 animate-pulse'
                              : 'bg-slate-800 text-slate-300 border border-slate-700'
                          }`}
                        >
                          {task.status}
                        </span>

                        <ChevronRight className="w-4 h-4 text-slate-500" />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Task Inspection Drawer Modal */}
        {selectedTask && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex justify-end animate-in fade-in duration-200">
            <div className="w-full max-w-xl bg-surface border-l border-surface-border h-full overflow-y-auto p-6 space-y-6 shadow-2xl">
              <div className="flex items-center justify-between pb-4 border-b border-surface-border">
                <div className="space-y-1">
                  <span className="font-mono text-xs text-brand-cyan uppercase">
                    Task Inspection
                  </span>
                  <h3 className="text-lg font-bold text-white">
                    {selectedTask.name}
                  </h3>
                </div>
                <button
                  onClick={() => setSelectedTask(null)}
                  className="p-1 rounded-lg hover:bg-surface-muted text-slate-400 hover:text-white transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Status and Idempotency */}
              <div className="grid grid-cols-2 gap-4 text-xs">
                <div className="p-3 rounded-lg bg-surface-muted border border-surface-border">
                  <span className="text-slate-400 block mb-1">Status</span>
                  <span className="font-mono font-semibold text-white uppercase">
                    {selectedTask.status}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-surface-muted border border-surface-border">
                  <span className="text-slate-400 block mb-1">Task Type</span>
                  <span className="font-mono text-brand-cyan">
                    {selectedTask.task_type}
                  </span>
                </div>
              </div>

              <div>
                <span className="text-xs text-slate-400 block mb-1">Idempotency Key:</span>
                <p className="text-xs font-mono text-slate-300 bg-surface-ground p-2.5 rounded border border-surface-border break-all">
                  {selectedTask.idempotency_key}
                </p>
              </div>

              {/* Error Details if any */}
              {selectedTask.error_details && Object.keys(selectedTask.error_details).length > 0 && (
                <div className="space-y-2">
                  <span className="text-xs font-semibold text-red-400 block">
                    Execution Error Details
                  </span>
                  <pre className="text-xs font-mono text-red-200 bg-red-950/40 p-3 rounded-lg border border-red-800 overflow-x-auto">
                    {JSON.stringify(selectedTask.error_details, null, 2)}
                  </pre>
                </div>
              )}

              {/* Output Payload */}
              <div className="space-y-2">
                <span className="text-xs font-semibold text-slate-300 block flex items-center gap-1.5">
                  <FileJson className="w-3.5 h-3.5 text-brand-cyan" />
                  Output Payload
                </span>
                <pre className="text-xs font-mono text-slate-200 bg-surface-ground p-3 rounded-lg border border-surface-border overflow-x-auto max-h-60">
                  {JSON.stringify(selectedTask.output_payload || {}, null, 2)}
                </pre>
              </div>

              {/* Input Payload */}
              <div className="space-y-2">
                <span className="text-xs font-semibold text-slate-300 block flex items-center gap-1.5">
                  <Terminal className="w-3.5 h-3.5 text-slate-400" />
                  Input Payload
                </span>
                <pre className="text-xs font-mono text-slate-300 bg-surface-ground p-3 rounded-lg border border-surface-border overflow-x-auto max-h-40">
                  {JSON.stringify(selectedTask.input_payload || {}, null, 2)}
                </pre>
              </div>

              {/* Verification Records */}
              {selectedTask.verification_records && selectedTask.verification_records.length > 0 && (
                <div className="space-y-2">
                  <span className="text-xs font-semibold text-emerald-400 block flex items-center gap-1.5">
                    <CheckCheck className="w-4 h-4" />
                    Verification Records ({selectedTask.verification_records.length})
                  </span>
                  <div className="space-y-2">
                    {selectedTask.verification_records.map((vr, i) => (
                      <div
                        key={i}
                        className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-800/40 text-xs space-y-1.5"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-emerald-300">
                            {vr.verification_type || 'assertion'}
                          </span>
                          <span className="font-mono uppercase text-emerald-400">
                            {vr.status || 'passed'}
                          </span>
                        </div>
                        {vr.evidence && (
                          <pre className="text-[11px] font-mono text-slate-300 bg-surface-ground p-2 rounded border border-surface-border overflow-x-auto">
                            {JSON.stringify(vr.evidence, null, 2)}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Execution Attempts */}
              {selectedTask.attempts && selectedTask.attempts.length > 0 && (
                <div className="space-y-2">
                  <span className="text-xs font-semibold text-slate-300 block">
                    Execution Attempts ({selectedTask.attempts.length})
                  </span>
                  <div className="space-y-2">
                    {selectedTask.attempts.map((att) => (
                      <div
                        key={att.id}
                        className="p-3 rounded-lg bg-surface-muted border border-surface-border text-xs space-y-1"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-white">
                            Attempt #{att.attempt_number}
                          </span>
                          <span className="font-mono uppercase text-slate-300">
                            {att.status}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400">
                          Started: {new Date(att.started_at).toLocaleString()}
                        </p>
                        {att.error_message && (
                          <p className="text-[11px] text-red-300 font-mono">
                            Error: {att.error_message}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Manual Handoff Complete Action */}
              {selectedTask.status === 'manual_handoff' && (
                <div className="pt-4 border-t border-surface-border">
                  <button
                    onClick={() => handleCompleteHandoff(selectedTask.id)}
                    disabled={completingHandoffId === selectedTask.id}
                    className="w-full py-2.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold transition-colors flex items-center justify-center gap-2 shadow-md shadow-amber-900/30"
                  >
                    {completingHandoffId === selectedTask.id ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <CheckCircle2 className="w-4 h-4" />
                    )}
                    Mark Manual Handoff Completed
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
