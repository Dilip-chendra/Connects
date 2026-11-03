'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Layers, CheckCircle2, Activity, FolderGit2, LogOut, ShieldAlert } from 'lucide-react';
import { api } from '@/lib/api';

interface NavbarProps {
  tenantId?: string;
  workspaceName?: string;
  userEmail?: string;
}

export function Navbar({ tenantId, workspaceName, userEmail }: NavbarProps) {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await api.auth.logout();
    } catch {
      // ignore
    }
    router.push('/login');
  };

  const navLinks = tenantId
    ? [
        { href: `/workspaces/${tenantId}`, label: 'Overview', icon: Layers },
        { href: `/workspaces/${tenantId}/projects`, label: 'Projects', icon: FolderGit2 },
        { href: `/workspaces/${tenantId}/approvals`, label: 'Approvals', icon: ShieldAlert },
        { href: `/workspaces/${tenantId}/activity`, label: 'Activity', icon: Activity },
      ]
    : [];

  return (
    <header className="border-b border-surface-border bg-surface/80 backdrop-blur-md sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link href={tenantId ? `/workspaces/${tenantId}` : '/workspaces'} className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-blue to-brand-cyan flex items-center justify-center font-bold text-white shadow-md shadow-brand-blue/20">
              C
            </div>
            <span className="font-semibold text-white tracking-tight text-lg">Connects</span>
          </Link>

          {workspaceName && (
            <div className="flex items-center gap-2 pl-4 border-l border-surface-border">
              <Link
                href="/workspaces"
                className="text-xs font-medium px-2.5 py-1 rounded bg-surface-muted text-slate-300 hover:text-white border border-surface-border flex items-center gap-1.5 transition-colors"
                title="Switch Workspace"
              >
                <span>{workspaceName}</span>
                <span className="text-[10px] text-brand-cyan">▾</span>
              </Link>
            </div>
          )}

          <nav className="hidden md:flex items-center gap-1 ml-4">
            {navLinks.map((link) => {
              const Icon = link.icon;
              const isActive = pathname === link.href || (link.href !== `/workspaces/${tenantId}` && pathname.startsWith(link.href));
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-brand-blue/15 text-brand-cyan border border-brand-blue/30'
                      : 'text-slate-400 hover:text-white hover:bg-surface-muted'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {userEmail && (
            <span className="text-xs text-slate-400 hidden sm:inline-block font-mono">
              {userEmail}
            </span>
          )}
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-red-400 transition-colors p-1.5 rounded hover:bg-surface-muted"
            title="Sign out"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline">Sign out</span>
          </button>
        </div>
      </div>
    </header>
  );
}
