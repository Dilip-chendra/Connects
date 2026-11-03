'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  FolderGit2,
  Plus,
  ArrowRight,
  ShieldAlert,
  Activity,
  CheckCircle2,
  Clock,
  Loader2,
  AlertCircle,
  ExternalLink,
} from 'lucide-react';
import {
  ApprovalRequestSummary,
  ProjectSummary,
  TenantSummary,
  WorkspaceActivityItem,
} from '@connects/shared';
import { api } from '@/lib/api';
import { Navbar } from '@/components/Navbar';

export default function WorkspaceDashboardPage() {
  const params = useParams();
  const router = useRouter();
  const tenantId = params.tenantId as string;

  const [workspace, setWorkspace] = useState<TenantSummary | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRequestSummary[]>([]);
  const [activities, setActivities] = useState<WorkspaceActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const [wsData, projData, apprvData, actData] = await Promise.all([
          api.workspaces.get(tenantId),
          api.projects.list(tenantId),
          api.approvals.list(tenantId),
          api.workspaces.getActivity(tenantId),
        ]);
        setWorkspace(wsData);
        setProjects(projData);
        setApprovals(apprvData);
        setActivities(actData.slice(0, 5));
      } catch (err: any) {
        if (err.status === 401) {
          router.push('/login');
          return;
        }
        setError(err.message || 'Failed to load workspace.');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [tenantId, router]);

  if (loading) {
    return (
      <div className="min-h-screen bg-background text-white flex flex-col">
        <Navbar tenantId={tenantId} />
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-brand-cyan" />
        </div>
      </div>
    );
  }

  if (error || !workspace) {
    return (
      <div className="min-h-screen bg-background text-white flex flex-col">
        <Navbar tenantId={tenantId} />
        <div className="flex-1 max-w-xl mx-auto px-4 py-16 text-center">
          <AlertCircle className="w-10 h-10 text-red-400 mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-white">Workspace Unavailable</h2>
          <p className="text-xs text-slate-400 mt-1 mb-6">{error || 'Workspace could not be found.'}</p>
          <Link
            href="/workspaces"
            className="px-4 py-2 rounded-lg bg-surface-muted border border-surface-border text-xs text-slate-300 hover:text-white"
          >
            Return to Workspaces
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-white flex flex-col">
      <Navbar tenantId={tenantId} workspaceName={workspace.name} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Header section */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-surface-border">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight text-white">{workspace.name}</h1>
              <span className="text-xs font-mono uppercase px-2 py-0.5 rounded bg-surface-muted text-slate-400 border border-surface-border">
                {workspace.tier}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Organization ID: <span className="font-mono text-slate-300">{workspace.id}</span>
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href={`/workspaces/${tenantId}/projects/new`}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-brand-blue hover:bg-blue-600 text-white text-xs font-medium transition-colors shadow-sm shadow-brand-blue/20"
            >
              <Plus className="w-4 h-4" />
              New Project
            </Link>
          </div>
        </div>

        {/* Approvals Banner if pending */}
        {approvals.length > 0 && (
          <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-amber-500/20 flex items-center justify-center text-amber-400 shrink-0">
                <ShieldAlert className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-white">
                  {approvals.length} Action{approvals.length > 1 ? 's' : ''} Awaiting Founder Approval
                </h4>
                <p className="text-xs text-amber-300/80">
                  Execution is paused until launch gates and sensitive operations are explicitly reviewed.
                </p>
              </div>
            </div>
            <Link
              href={`/workspaces/${tenantId}/approvals`}
              className="px-3.5 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-black text-xs font-semibold whitespace-nowrap self-start sm:self-auto transition-colors"
            >
              Review Approvals
            </Link>
          </div>
        )}

        {/* Overview Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="p-5 rounded-xl bg-surface border border-surface-border">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-medium uppercase tracking-wider">Active Projects</span>
              <FolderGit2 className="w-4 h-4 text-brand-blue" />
            </div>
            <div className="text-2xl font-bold text-white">{projects.length}</div>
          </div>

          <div className="p-5 rounded-xl bg-surface border border-surface-border">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-medium uppercase tracking-wider">Pending Approvals</span>
              <ShieldAlert className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-2xl font-bold text-white">{approvals.length}</div>
          </div>

          <div className="p-5 rounded-xl bg-surface border border-surface-border">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-medium uppercase tracking-wider">Tenant RLS Scope</span>
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-sm font-semibold text-emerald-400 mt-1 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              Active & Enforced
            </div>
          </div>
        </div>

        {/* Projects Section */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Projects in Workspace</h2>
            <Link
              href={`/workspaces/${tenantId}/projects`}
              className="text-xs text-brand-cyan hover:underline flex items-center gap-1"
            >
              View all ({projects.length}) <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {projects.length === 0 ? (
            <div className="p-8 text-center rounded-xl bg-surface border border-surface-border">
              <FolderGit2 className="w-8 h-8 text-slate-500 mx-auto mb-2" />
              <p className="text-xs text-slate-400 mb-4">No projects created yet in this workspace.</p>
              <Link
                href={`/workspaces/${tenantId}/projects/new`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-blue hover:bg-blue-600 text-white text-xs font-medium"
              >
                <Plus className="w-3.5 h-3.5" /> Create Project
              </Link>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {projects.slice(0, 6).map((p) => (
                <Link
                  key={p.id}
                  href={`/workspaces/${tenantId}/projects/${p.id}`}
                  className="group p-5 rounded-xl bg-surface border border-surface-border hover:border-brand-blue/40 transition-all flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-surface-muted text-slate-400 border border-surface-border">
                        {p.category || 'saas'}
                      </span>
                      <span className="text-[11px] font-medium text-emerald-400 flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                        {p.status}
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-white group-hover:text-brand-cyan transition-colors">
                      {p.name}
                    </h3>
                    <p className="text-xs text-slate-400 line-clamp-2 mt-1">
                      {p.primaryGoal}
                    </p>
                  </div>
                  <div className="mt-4 pt-3 border-t border-surface-border/50 flex items-center justify-between text-[11px] text-slate-500">
                    <span>Manage workflow</span>
                    <ArrowRight className="w-3.5 h-3.5 text-brand-cyan group-hover:translate-x-1 transition-transform" />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Activity feed */}
        {activities.length > 0 && (
          <div className="space-y-4 pt-4">
            <h2 className="text-base font-semibold text-white">Recent Activity & Audit Trail</h2>
            <div className="rounded-xl bg-surface border border-surface-border divide-y divide-surface-border/50">
              {activities.map((act) => (
                <div key={act.id} className="p-4 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3">
                    <Activity className="w-4 h-4 text-slate-500" />
                    <div>
                      <span className="font-mono text-slate-200 font-medium">{act.action}</span>
                      <span className="text-slate-500 ml-2">({act.resourceType})</span>
                    </div>
                  </div>
                  <div className="text-slate-500 flex items-center gap-1.5 font-mono text-[11px]">
                    <Clock className="w-3 h-3" />
                    {new Date(act.createdAt).toLocaleTimeString()}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
