'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, ArrowRight, AlertCircle, Building2 } from 'lucide-react';
import { api } from '@/lib/api';
import { Navbar } from '@/components/Navbar';

export default function NewWorkspacePage() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [tier, setTier] = useState('free');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const ws = await api.workspaces.create({
        name,
        slug: slug.trim() || undefined,
        tier,
      });
      router.push(`/workspaces/${ws.id}`);
    } catch (err: any) {
      setError(err.message || 'Failed to create workspace.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-white flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-xl w-full mx-auto px-4 sm:px-6 py-12">
        <Link
          href="/workspaces"
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white mb-6 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Workspaces
        </Link>

        <div className="p-8 rounded-2xl bg-surface border border-surface-border shadow-2xl">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-brand-blue/15 border border-brand-blue/30 flex items-center justify-center text-brand-cyan">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Create New Workspace</h1>
              <p className="text-xs text-slate-400">
                Each workspace is an isolated organization with dedicated RLS policies
              </p>
            </div>
          </div>

          {error && (
            <div className="mb-6 p-3.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Workspace Name *</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Acme Ventures"
                className="w-full px-3.5 py-2.5 rounded-lg bg-surface-muted border border-surface-border text-white text-sm focus:outline-none focus:border-brand-blue transition-colors placeholder:text-slate-600"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">
                Workspace URL Slug <span className="text-slate-500 font-normal">(optional)</span>
              </label>
              <input
                type="text"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="acme-ventures"
                className="w-full px-3.5 py-2.5 rounded-lg bg-surface-muted border border-surface-border text-white text-sm focus:outline-none focus:border-brand-blue transition-colors placeholder:text-slate-600 font-mono text-xs"
              />
              <p className="text-[11px] text-slate-500">Auto-generated from name if left empty.</p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Plan Tier</label>
              <select
                value={tier}
                onChange={(e) => setTier(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-lg bg-surface-muted border border-surface-border text-white text-sm focus:outline-none focus:border-brand-blue transition-colors"
              >
                <option value="free">Free Tier (Solo Builders)</option>
                <option value="pro">Pro Tier (Multi-project Startup)</option>
                <option value="enterprise">Enterprise Tier</option>
              </select>
            </div>

            <button
              type="submit"
              disabled={loading || !name.trim()}
              className="w-full py-2.5 px-4 rounded-lg bg-brand-blue hover:bg-blue-600 disabled:opacity-50 text-white font-medium text-sm flex items-center justify-center gap-2 transition-all shadow-md shadow-brand-blue/20 mt-6"
            >
              {loading ? 'Creating...' : 'Initialize Workspace'}
              {!loading && <ArrowRight className="w-4 h-4" />}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
