'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Plus, ArrowRight, Layers, ShieldCheck, AlertCircle, Loader2 } from 'lucide-react';
import { TenantSummary } from '@connects/shared';
import { api } from '@/lib/api';
import { Navbar } from '@/components/Navbar';

export default function WorkspacesPage() {
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<TenantSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await api.workspaces.list();
        setWorkspaces(data);
      } catch (err: any) {
        if (err.status === 401) {
          router.push('/login');
          return;
        }
        setError(err.message || 'Failed to load workspaces.');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [router]);

  return (
    <div className="min-h-screen bg-background text-white flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="flex items-center justify-between pb-6 border-b border-surface-border">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Your Workspaces</h1>
            <p className="text-xs text-slate-400 mt-1">
              Select an isolated workspace or initialize a new organization
            </p>
          </div>
          <Link
            href="/workspaces/new"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-brand-blue hover:bg-blue-600 text-white text-xs font-medium transition-colors shadow-sm shadow-brand-blue/20"
          >
            <Plus className="w-4 h-4" />
            New Workspace
          </Link>
        </div>

        {error && (
          <div className="mt-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center gap-3">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="flex flex-col items-center justify-center py-24 text-slate-500">
            <Loader2 className="w-8 h-8 animate-spin text-brand-cyan mb-3" />
            <span className="text-xs">Loading workspaces...</span>
          </div>
        ) : workspaces.length === 0 ? (
          <div className="mt-8 p-12 text-center rounded-2xl bg-surface border border-surface-border flex flex-col items-center">
            <div className="w-12 h-12 rounded-xl bg-surface-muted border border-surface-border flex items-center justify-center text-slate-400 mb-4">
              <Layers className="w-6 h-6" />
            </div>
            <h3 className="text-base font-semibold text-white">No workspaces found</h3>
            <p className="text-xs text-slate-400 max-w-sm mt-1 mb-6">
              Connects organizes all your projects, business context, and automations within secure tenant workspaces.
            </p>
            <Link
              href="/workspaces/new"
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-brand-blue hover:bg-blue-600 text-white text-xs font-medium shadow-md shadow-brand-blue/20 transition-all"
            >
              <Plus className="w-4 h-4" />
              Create your first workspace
            </Link>
          </div>
        ) : (
          <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4">
            {workspaces.map((ws) => (
              <Link
                key={ws.id}
                href={`/workspaces/${ws.id}`}
                className="group p-5 rounded-xl bg-surface border border-surface-border hover:border-brand-blue/50 transition-all flex flex-col justify-between hover:shadow-lg hover:shadow-brand-blue/5"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono uppercase px-2 py-0.5 rounded bg-surface-muted text-slate-400 border border-surface-border">
                      {ws.tier} tier
                    </span>
                    {ws.role && (
                      <span className="text-[11px] font-medium text-emerald-400 flex items-center gap-1">
                        <ShieldCheck className="w-3.5 h-3.5" />
                        {ws.role}
                      </span>
                    )}
                  </div>
                  <h3 className="text-base font-semibold text-white mt-3 group-hover:text-brand-cyan transition-colors">
                    {ws.name}
                  </h3>
                  <p className="text-xs text-slate-400 font-mono mt-0.5">/{ws.slug}</p>
                </div>

                <div className="mt-6 pt-4 border-t border-surface-border/50 flex items-center justify-between text-xs text-slate-400 group-hover:text-slate-200">
                  <span>Enter workspace</span>
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform text-brand-cyan" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
