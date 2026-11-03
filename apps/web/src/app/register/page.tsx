'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, AlertCircle, Lock, Mail, User } from 'lucide-react';
import { api } from '@/lib/api';

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    setLoading(true);

    try {
      await api.auth.register({
        email,
        password,
        full_name: fullName || undefined,
      });
      router.push('/workspaces');
    } catch (err: any) {
      setError(err.message || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-center items-center px-4 sm:px-6 lg:px-8 bg-background">
      <div className="max-w-md w-full space-y-8 p-8 rounded-2xl bg-surface border border-surface-border shadow-2xl shadow-black/50">
        <div className="text-center space-y-2">
          <div className="inline-flex w-12 h-12 rounded-xl bg-gradient-to-br from-brand-blue to-brand-cyan items-center justify-center font-bold text-white text-xl shadow-lg shadow-brand-blue/20">
            C
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-white">Create an account</h2>
          <p className="text-xs text-slate-400">
            Get started with Connects startup orchestration platform
          </p>
        </div>

        {error && (
          <div className="p-3.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">Full Name</label>
            <div className="relative">
              <User className="w-4 h-4 absolute left-3 top-3 text-slate-500" />
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Ada Lovelace"
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-surface-muted border border-surface-border text-white text-sm focus:outline-none focus:border-brand-blue transition-colors placeholder:text-slate-600"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">Email Address</label>
            <div className="relative">
              <Mail className="w-4 h-4 absolute left-3 top-3 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="founder@startup.com"
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-surface-muted border border-surface-border text-white text-sm focus:outline-none focus:border-brand-blue transition-colors placeholder:text-slate-600"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">Password (8+ chars)</label>
            <div className="relative">
              <Lock className="w-4 h-4 absolute left-3 top-3 text-slate-500" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-surface-muted border border-surface-border text-white text-sm focus:outline-none focus:border-brand-blue transition-colors placeholder:text-slate-600"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 rounded-lg bg-brand-blue hover:bg-blue-600 disabled:opacity-50 text-white font-medium text-sm flex items-center justify-center gap-2 transition-all shadow-md shadow-brand-blue/20 mt-2"
          >
            {loading ? 'Creating account...' : 'Create account'}
            {!loading && <ArrowRight className="w-4 h-4" />}
          </button>
        </form>

        <div className="text-center pt-2 border-t border-surface-border">
          <p className="text-xs text-slate-400">
            Already have an account?{' '}
            <Link href="/login" className="text-brand-cyan hover:underline font-medium">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
