'use client';

import React, { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Activity,
  Layers,
  FolderGit2,
  GitBranch,
  Play,
  Cpu,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  Search,
  FileCode,
  ChevronDown,
  ChevronUp,
  Loader2,
  User,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Navbar } from '@/components/Navbar';

interface ActivityItem {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export default function WorkspaceActivityPage() {
  const params = useParams();
  const router = useRouter();
  const tenantId = params.tenantId as string;

  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterQuery, setFilterQuery] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const loadActivity = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.workspaces.getActivity(tenantId);
      setActivities(data as unknown as ActivityItem[]);
    } catch (err: any) {
      if (err.status === 401) {
        router.push('/login');
        return;
      }
      setError(err.message || 'Failed to load workspace activity trail.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadActivity();
  }, [tenantId]);

  const getActionIcon = (action: string) => {
    if (action.startsWith('workspace.')) return <Layers className="w-4 h-4 text-brand-blue" />;
    if (action.startsWith('project.')) return <FolderGit2 className="w-4 h-4 text-purple-400" />;
    if (action.startsWith('plan.')) return <GitBranch className="w-4 h-4 text-brand-cyan" />;
    if (action.startsWith('approval.')) return <ShieldAlert className="w-4 h-4 text-amber-400" />;
    if (action.startsWith('workflow.') || action.startsWith('task.')) return <Cpu className="w-4 h-4 text-emerald-400" />;
    return <Activity className="w-4 h-4 text-slate-400" />;
  };

  const filteredActivities = activities.filter((act) => {
    if (!filterQuery.trim()) return true;
    const q = filterQuery.toLowerCase();
    return (
      act.action.toLowerCase().includes(q) ||
      (act.resource_type && act.resource_type.toLowerCase().includes(q)) ||
      (act.resource_id && act.resource_id.toLowerCase().includes(q))
    );
  });

  return (
    <div className="min-h-screen bg-surface-ground text-slate-100 flex flex-col font-sans">
      <Navbar tenantId={tenantId} />

      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Activity className="w-5 h-5 text-brand-cyan" />
              <h1 className="text-2xl font-bold text-white tracking-tight">
                Workspace Activity & Audit Trail
              </h1>
            </div>
            <p className="text-xs text-slate-400">
              Cryptographically backed, tenant-isolated audit log recording all administrative, planning, and execution events.
            </p>
          </div>

          <button
            onClick={loadActivity}
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

        {/* Filter bar */}
        <div className="mb-6 relative max-w-md">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            placeholder="Filter by action or resource type (e.g. plan, project, workflow)..."
            className="w-full pl-9 pr-4 py-2 rounded-xl bg-surface border border-surface-border text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-brand-blue"
          />
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-400">
            <Loader2 className="w-8 h-8 animate-spin text-brand-blue mb-4" />
            <p className="text-sm">Loading activity logs...</p>
          </div>
        ) : filteredActivities.length === 0 ? (
          <div className="p-12 text-center bg-surface rounded-2xl border border-surface-border space-y-3">
            <Activity className="w-8 h-8 text-slate-500 mx-auto mb-2" />
            <h3 className="text-base font-semibold text-white">No Activity Found</h3>
            <p className="text-xs text-slate-400">
              {filterQuery ? 'No log entries match your filter.' : 'No audit records have been generated yet in this workspace.'}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredActivities.map((act) => {
              const isExpanded = expandedId === act.id;
              const hasDetails = act.details && Object.keys(act.details).length > 0;

              return (
                <div
                  key={act.id}
                  className="p-4 rounded-xl bg-surface border border-surface-border hover:border-slate-700 transition-colors space-y-3"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-surface-muted border border-surface-border flex items-center justify-center shrink-0">
                        {getActionIcon(act.action)}
                      </div>
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-mono text-xs font-semibold text-white">
                            {act.action}
                          </span>
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface-muted text-slate-400 border border-surface-border">
                            {act.resource_type}
                          </span>
                          {act.resource_id && (
                            <span className="text-[10px] font-mono text-slate-500">
                              id:{act.resource_id.slice(0, 8)}...
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-slate-400">
                          {new Date(act.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>

                    {hasDetails && (
                      <button
                        onClick={() => setExpandedId(isExpanded ? null : act.id)}
                        className="text-xs text-slate-400 hover:text-brand-cyan flex items-center gap-1 transition-colors px-2 py-1 rounded hover:bg-surface-muted shrink-0"
                      >
                        <span>{isExpanded ? 'Hide Details' : 'View Details'}</span>
                        {isExpanded ? (
                          <ChevronUp className="w-3.5 h-3.5" />
                        ) : (
                          <ChevronDown className="w-3.5 h-3.5" />
                        )}
                      </button>
                    )}
                  </div>

                  {/* Expanded JSON details */}
                  {isExpanded && hasDetails && (
                    <div className="pt-2 border-t border-surface-border">
                      <pre className="text-[11px] font-mono text-slate-300 bg-surface-ground p-3 rounded-lg border border-surface-border overflow-x-auto max-h-60">
                        {JSON.stringify(act.details, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
