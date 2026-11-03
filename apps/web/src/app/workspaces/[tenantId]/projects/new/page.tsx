'use client';

import React, { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, ArrowRight, AlertCircle, Sparkles, FolderPlus } from 'lucide-react';
import { api } from '@/lib/api';
import { Navbar } from '@/components/Navbar';

export default function NewProjectPage() {
  const params = useParams();
  const router = useRouter();
  const tenantId = params.tenantId as string;

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('saas');
  const [targetLaunchDate, setTargetLaunchDate] = useState('');
  const [primaryGoal, setPrimaryGoal] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (primaryGoal.trim().length < 5) {
      setError('Please provide a descriptive business goal (at least 5 characters).');
      return;
    }

    setLoading(true);

    try {
      const proj = await api.projects.create(tenantId, {
        name,
        description: description || undefined,
        category,
        target_launch_date: targetLaunchDate ? new Date(targetLaunchDate).toISOString() : undefined,
        primary_goal: primaryGoal,
      });
      router.push(`/workspaces/${tenantId}/projects/${proj.id}`);
    } catch (err: any) {
      setError(err.message || 'Failed to create project.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-white flex flex-col">
      <Navbar tenantId={tenantId} />

      <main className="flex-1 max-w-2xl w-full mx-auto px-4 sm:px-6 py-10">
        <Link
          href={`/workspaces/${tenantId}/projects`}
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white mb-6 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Projects
        </Link>

        <div className="p-8 rounded-2xl bg-surface border border-surface-border shadow-2xl">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-brand-blue/15 border border-brand-blue/30 flex items-center justify-center text-brand-cyan">
              <FolderPlus className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Create New Project</h1>
              <p className="text-xs text-slate-400">
                Define your startup business goal for automated planning and execution
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
              <label className="text-xs font-medium text-slate-300">Project Name *</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. AI Resume Optimizer"
                className="w-full px-3.5 py-2.5 rounded-lg bg-surface-muted border border-surface-border text-white text-sm focus:outline-none focus:border-brand-blue transition-colors placeholder:text-slate-600"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Category</label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-lg bg-surface-muted border border-surface-border text-white text-sm focus:outline-none focus:border-brand-blue transition-colors"
                >
                  <option value="saas">SaaS Application</option>
                  <option value="developer_tool">Developer Tool</option>
                  <option value="ai_agent">AI Agent / Workflow</option>
                  <option value="marketplace">Marketplace</option>
                  <option value="ecommerce">E-Commerce</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Target Launch Date</label>
                <input
                  type="date"
                  value={targetLaunchDate}
                  onChange={(e) => setTargetLaunchDate(e.target.value)}
                  className="w-full px-3.5 py-2 rounded-lg bg-surface-muted border border-surface-border text-white text-sm focus:outline-none focus:border-brand-blue transition-colors"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Description</label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Brief summary of your product and target audience..."
                className="w-full px-3.5 py-2.5 rounded-lg bg-surface-muted border border-surface-border text-white text-sm focus:outline-none focus:border-brand-blue transition-colors placeholder:text-slate-600"
              />
            </div>

            <div className="space-y-1.5 pt-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-white flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-brand-cyan" />
                  Primary Business Goal *
                </label>
                <span className="text-[11px] text-slate-500">Natural language goal</span>
              </div>
              <textarea
                required
                rows={4}
                value={primaryGoal}
                onChange={(e) => setPrimaryGoal(e.target.value)}
                placeholder="Describe what you want to build and launch in natural language. For example:&#10;'Launch an AI resume optimization SaaS with Stripe payments, custom domain hosting, user authentication, and a verified launch checklist.'"
                className="w-full p-3.5 rounded-lg bg-surface-muted border border-surface-border text-white text-xs leading-relaxed focus:outline-none focus:border-brand-blue transition-colors placeholder:text-slate-600"
              />
              <p className="text-[11px] text-slate-400">
                Connects will translate this goal into a structured project plan with milestones, task dependencies, and verification criteria.
              </p>
            </div>

            <button
              type="submit"
              disabled={loading || !name.trim() || !primaryGoal.trim()}
              className="w-full py-2.5 px-4 rounded-lg bg-brand-blue hover:bg-blue-600 disabled:opacity-50 text-white font-medium text-sm flex items-center justify-center gap-2 transition-all shadow-md shadow-brand-blue/20 mt-6"
            >
              {loading ? 'Creating Project...' : 'Create Project'}
              {!loading && <ArrowRight className="w-4 h-4" />}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
