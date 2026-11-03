'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  Loader2,
  RefreshCw,
  FileText,
  UserCheck,
} from 'lucide-react';
import { ApprovalRequestSummary } from '@connects/shared';
import { api } from '@/lib/api';
import { Navbar } from '@/components/Navbar';

interface ApprovalItem {
  id: string;
  task_id: string;
  task_name: string;
  requested_action: string;
  impact_assessment: string;
  status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  decision_notes: string | null;
  created_at: string;
}

export default function ApprovalsPage() {
  const params = useParams();
  const router = useRouter();
  const tenantId = params.tenantId as string;

  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Decision Modal State
  const [selectedApproval, setSelectedApproval] = useState<ApprovalItem | null>(null);
  const [decisionType, setDecisionType] = useState<'approved' | 'rejected'>('approved');
  const [decisionNotes, setDecisionNotes] = useState('');

  const loadApprovals = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.approvals.list(tenantId);
      setApprovals(data as unknown as ApprovalItem[]);
    } catch (err: any) {
      if (err.status === 401) {
        router.push('/login');
        return;
      }
      setError(err.message || 'Failed to load approval requests.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadApprovals();
  }, [tenantId]);

  const openDecisionModal = (item: ApprovalItem, type: 'approved' | 'rejected') => {
    setSelectedApproval(item);
    setDecisionType(type);
    setDecisionNotes('');
  };

  const submitDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedApproval) return;

    setActionLoadingId(selectedApproval.id);
    setError(null);
    try {
      await api.approvals.submitDecision(
        tenantId,
        selectedApproval.id,
        decisionType,
        decisionNotes || undefined
      );
      setSuccessMsg(
        `Approval request was successfully marked as '${decisionType}'.`
      );
      setSelectedApproval(null);
      await loadApprovals();
    } catch (err: any) {
      setError(err.message || `Failed to submit decision.`);
    } finally {
      setActionLoadingId(null);
    }
  };

  return (
    <div className="min-h-screen bg-surface-ground text-slate-100 flex flex-col font-sans">
      <Navbar tenantId={tenantId} />

      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <ShieldAlert className="w-5 h-5 text-amber-400" />
              <h1 className="text-2xl font-bold text-white tracking-tight">
                Founder Approval Queue
              </h1>
            </div>
            <p className="text-xs text-slate-400">
              Human-in-the-loop safety gates requiring explicit founder sign-off before executing critical actions.
            </p>
          </div>

          <button
            onClick={loadApprovals}
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white px-3 py-1.5 rounded-md bg-surface border border-surface-border transition-colors self-start sm:self-auto"
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

        {successMsg && (
          <div className="mb-6 p-4 rounded-xl bg-emerald-950/40 border border-emerald-800 text-emerald-200 text-sm flex items-center gap-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}

        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-400">
            <Loader2 className="w-8 h-8 animate-spin text-brand-blue mb-4" />
            <p className="text-sm">Loading approval requests...</p>
          </div>
        ) : approvals.length === 0 ? (
          <div className="p-12 text-center bg-surface rounded-2xl border border-surface-border space-y-4">
            <div className="w-12 h-12 rounded-full bg-emerald-500/10 text-emerald-400 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <h3 className="text-base font-semibold text-white">
              No Pending Approvals
            </h3>
            <p className="text-xs text-slate-400 max-w-md mx-auto">
              There are no tasks currently awaiting founder approval. When a workflow reaches a high-risk safety gate or sensitive configuration step, it will appear here for your review.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {approvals.map((item) => (
              <div
                key={item.id}
                className="p-6 rounded-2xl bg-surface border border-surface-border space-y-4 shadow-sm"
              >
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs px-2 py-0.5 rounded bg-surface-muted text-slate-400 border border-surface-border">
                        Task: {item.task_name}
                      </span>
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 uppercase tracking-wider font-mono">
                        <Clock className="w-3 h-3" />
                        {item.status}
                      </span>
                    </div>
                    <h3 className="text-base font-semibold text-white">
                      {item.requested_action}
                    </h3>
                  </div>

                  {/* Approve / Reject Buttons */}
                  {item.status === 'pending' && (
                    <div className="flex items-center gap-2.5 shrink-0">
                      <button
                        onClick={() => openDecisionModal(item, 'rejected')}
                        disabled={actionLoadingId === item.id}
                        className="px-4 py-2 rounded-lg border border-red-900/40 bg-red-950/20 hover:bg-red-950/40 text-red-300 text-xs font-medium transition-colors disabled:opacity-50"
                      >
                        Reject
                      </button>
                      <button
                        onClick={() => openDecisionModal(item, 'approved')}
                        disabled={actionLoadingId === item.id}
                        className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1.5 transition-all shadow-md shadow-emerald-900/20 disabled:opacity-50"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Approve Action
                      </button>
                    </div>
                  )}
                </div>

                {/* Impact Assessment Card */}
                <div className="p-4 rounded-xl bg-amber-950/20 border border-amber-800/40 space-y-1.5">
                  <span className="text-xs font-semibold text-amber-400 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    Safety & Impact Assessment
                  </span>
                  <p className="text-xs text-slate-200 leading-relaxed font-sans">
                    {item.impact_assessment}
                  </p>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400 pt-2 border-t border-surface-border">
                  <span className="font-mono">
                    Created: {new Date(item.created_at).toLocaleString()}
                  </span>
                  <span className="font-mono">
                    ID: {item.id.slice(0, 8)}...
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Decision Modal */}
        {selectedApproval && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200">
            <div className="bg-surface border border-surface-border rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl">
              <div className="space-y-1">
                <span className="font-mono text-xs text-brand-cyan uppercase">
                  Confirm Decision
                </span>
                <h3 className="text-lg font-bold text-white">
                  {decisionType === 'approved' ? 'Approve Action' : 'Reject Action'}
                </h3>
                <p className="text-xs text-slate-300">
                  {selectedApproval.requested_action}
                </p>
              </div>

              <form onSubmit={submitDecision} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Founder Rationale / Notes (Optional)
                  </label>
                  <textarea
                    rows={3}
                    value={decisionNotes}
                    onChange={(e) => setDecisionNotes(e.target.value)}
                    placeholder="Enter context, reasons, or verification notes..."
                    className="w-full px-3.5 py-2.5 rounded-xl bg-surface-muted border border-surface-border text-white text-xs placeholder:text-slate-500 focus:outline-none focus:border-brand-blue"
                  />
                </div>

                <div className="flex items-center justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setSelectedApproval(null)}
                    className="px-4 py-2 rounded-lg text-xs text-slate-400 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={actionLoadingId === selectedApproval.id}
                    className={`px-5 py-2 rounded-lg text-xs font-semibold text-white transition-all shadow-md flex items-center gap-1.5 disabled:opacity-50 ${
                      decisionType === 'approved'
                        ? 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-900/20'
                        : 'bg-red-600 hover:bg-red-500 shadow-red-900/20'
                    }`}
                  >
                    {actionLoadingId === selectedApproval.id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : decisionType === 'approved' ? (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    ) : (
                      <XCircle className="w-3.5 h-3.5" />
                    )}
                    Confirm {decisionType === 'approved' ? 'Approval' : 'Rejection'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
