'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  FolderGit2,
  Plus,
  Search,
  ArrowRight,
  Filter,
  Archive,
  Calendar,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { ProjectSummary } from '@connects/shared';
import { api } from '@/lib/api';
import { Navbar } from '@/components/Navbar';

export default function ProjectsListPage() {
  const params = useParams();
  const router = useRouter();
  const tenantId = params.tenantId as string;

  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = async () => {
    try {
      setLoading(true);
      const data = await api.projects.list(tenantId, {
        q: search || undefined,
        status: statusFilter || undefined,
        includeArchived: statusFilter === 'archived',
      });
      setProjects(data);
    } catch (err: any) {
      if (err.status === 401) {
        router.push('/login');
        return;
      }
      setError(err.message || 'Failed to load projects.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, [tenantId, statusFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchProjects();
  };

  const handleArchive = async (e: React.MouseEvent, projectId: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Are you sure you want to archive this project? Historical workflow data will be preserved.')) {
      return;
    }
    try {
      await api.projects.archive(tenantId, projectId);
      await fetchProjects();
    } catch (err: any) {
      alert(err.message || 'Failed to archive project.');
    }
  };

  return (
    <div className="min-h-screen bg-background text-white flex flex-col">
      <Navbar tenantId={tenantId} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-surface-border">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Projects</h1>
            <p className="text-xs text-slate-400 mt-1">
              Manage startup goals, plan decompositions, and execution workflows
            </p>
          </div>
          <Link
            href={`/workspaces/${tenantId}/projects/new`}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-brand-blue hover:bg-blue-600 text-white text-xs font-medium transition-colors shadow-sm shadow-brand-blue/20 self-start sm:self-auto"
          >
            <Plus className="w-4 h-4" />
            New Project
          </Link>
        </div>

        {/* Filter & Search Bar */}
        <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
          <form onSubmit={handleSearchSubmit} className="relative w-full sm:w-96">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or business goal..."
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-surface border border-surface-border text-white text-xs focus:outline-none focus:border-brand-blue transition-colors placeholder:text-slate-500"
            />
          </form>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Filter className="w-3.5 h-3.5 text-slate-500" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-1.5 rounded-lg bg-surface border border-surface-border text-xs text-slate-300 focus:outline-none focus:border-brand-blue"
            >
              <option value="">All Active</option>
              <option value="draft">Draft</option>
              <option value="active">Active</option>
              <option value="launched">Launched</option>
              <option value="archived">Archived</option>
            </select>
          </div>
        </div>

        {error && (
          <div className="p-3.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center gap-2.5">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-500">
            <Loader2 className="w-7 h-7 animate-spin text-brand-cyan mb-2" />
            <span className="text-xs">Loading projects...</span>
          </div>
        ) : projects.length === 0 ? (
          <div className="p-12 text-center rounded-2xl bg-surface border border-surface-border">
            <FolderGit2 className="w-10 h-10 text-slate-500 mx-auto mb-3" />
            <h3 className="text-sm font-semibold text-white">No projects found</h3>
            <p className="text-xs text-slate-400 max-w-sm mx-auto mt-1 mb-6">
              Create a project by describing a natural language business goal to decompose it into executable tasks.
            </p>
            <Link
              href={`/workspaces/${tenantId}/projects/new`}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-blue hover:bg-blue-600 text-white text-xs font-medium"
            >
              <Plus className="w-4 h-4" /> Create Project
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((p) => (
              <Link
                key={p.id}
                href={`/workspaces/${tenantId}/projects/${p.id}`}
                className="group p-5 rounded-xl bg-surface border border-surface-border hover:border-brand-blue/40 transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-surface-muted text-slate-400 border border-surface-border">
                      {p.category || 'saas'}
                    </span>
                    <span
                      className={`text-[11px] font-medium px-2 py-0.5 rounded ${
                        p.status === 'archived'
                          ? 'bg-slate-800 text-slate-400'
                          : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      }`}
                    >
                      {p.status}
                    </span>
                  </div>

                  <h3 className="text-base font-semibold text-white group-hover:text-brand-cyan transition-colors">
                    {p.name}
                  </h3>

                  <p className="text-xs text-slate-400 mt-2 line-clamp-3 leading-relaxed">
                    {p.primaryGoal}
                  </p>
                </div>

                <div className="mt-6 pt-4 border-t border-surface-border/50 flex items-center justify-between text-xs text-slate-500">
                  <div className="flex items-center gap-1.5 font-mono text-[11px]">
                    <Calendar className="w-3.5 h-3.5 text-slate-500" />
                    <span>{new Date(p.createdAt).toLocaleDateString()}</span>
                  </div>

                  <div className="flex items-center gap-2">
                    {p.status !== 'archived' && (
                      <button
                        onClick={(e) => handleArchive(e, p.id)}
                        className="p-1.5 rounded hover:bg-red-500/10 hover:text-red-400 text-slate-500 transition-colors"
                        title="Archive project"
                      >
                        <Archive className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <span className="text-brand-cyan flex items-center gap-1 group-hover:translate-x-0.5 transition-transform">
                      Open <ArrowRight className="w-3.5 h-3.5" />
                    </span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
