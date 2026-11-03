import React from 'react';
import { Layers, ShieldCheck, Cpu, Database, Activity, GitFork } from 'lucide-react';

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col justify-between p-8 md:p-16 max-w-6xl mx-auto">
      <header className="flex items-center justify-between border-b border-surface-border pb-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-brand-blue to-brand-cyan flex items-center justify-center font-bold text-white shadow-lg shadow-brand-blue/20">
            C
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-white">Connects</h1>
            <p className="text-xs text-slate-400">Startup Operating System & Orchestration</p>
          </div>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface text-xs text-emerald-400 border border-surface-border">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          Foundation Core Active
        </div>
      </header>

      <div className="py-16 space-y-8">
        <div className="space-y-4 max-w-2xl">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded bg-brand-blue/10 text-brand-cyan text-xs font-mono uppercase tracking-wider border border-brand-blue/20">
            Phase 0 Architecture
          </div>
          <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-white">
            One Goal. Connected Tools. <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-blue to-brand-cyan">
              Real Outcomes.
            </span>
          </h2>
          <p className="text-slate-400 text-base leading-relaxed">
            Coordinating developer tools, payments, deployments, and verification into a unified business operating layer.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4">
          <div className="p-6 rounded-xl bg-surface border border-surface-border space-y-3">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center text-brand-blue">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-semibold text-white">Multi-Tenant Isolation</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Row-Level Security (RLS) and transaction-bound tenant contexts preventing cross-tenant leakage.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-surface border border-surface-border space-y-3">
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 flex items-center justify-center text-brand-cyan">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-semibold text-white">AES-256-GCM Vault</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Envelope encryption with authenticated associated data binding secrets to tenant and connector scopes.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-surface border border-surface-border space-y-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400">
              <Database className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-semibold text-white">Context Graph & DAG</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Durable execution state machines and business context nodes stored in PostgreSQL 16.
            </p>
          </div>
        </div>
      </div>

      <footer className="border-t border-surface-border pt-6 flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-slate-500">
        <div className="flex items-center gap-4">
          <span>PostgreSQL 16</span>
          <span>•</span>
          <span>Redis 7</span>
          <span>•</span>
          <span>FastAPI</span>
          <span>•</span>
          <span>Next.js 14</span>
        </div>
        <div>Connects Platform Architecture v0.1.0</div>
      </footer>
    </main>
  );
}
