'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Sparkles,
  GitBranch,
  Layers,
  Calendar,
  ArrowRight,
  Plus,
  Network,
  Loader2,
  AlertCircle,
  AlertTriangle,
  GitCommit,
  ExternalLink,
  FolderGit2,
  Lock,
  Globe,
  Trash2,
  Play,
  FileCode2,
  Check,
  Clock,
} from 'lucide-react';
import {
  ConnectedRepository,
  ContextEdge,
  ContextNode,
  ExecutionPlanSummary,
  GitHubAvailableRepo,
  GitHubConfig,
  GitHubInstallation,
  ProjectSummary,
  RepositoryFinding,
  RepositoryScan,
} from '@connects/shared';
import { api } from '@/lib/api';
import { Navbar } from '@/components/Navbar';

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const tenantId = params.tenantId as string;
  const projectId = params.projectId as string;

  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [plans, setPlans] = useState<ExecutionPlanSummary[]>([]);
  const [contextNodes, setContextNodes] = useState<ContextNode[]>([]);
  const [contextEdges, setContextEdges] = useState<ContextEdge[]>([]);
  const [activeTab, setActiveTab] = useState<'plans' | 'context' | 'repositories'>('plans');
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // GitHub / Repository State
  const [githubConfig, setGithubConfig] = useState<GitHubConfig | null>(null);
  const [installations, setInstallations] = useState<GitHubInstallation[]>([]);
  const [connectedRepos, setConnectedRepos] = useState<ConnectedRepository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<ConnectedRepository | null>(null);
  const [repoScans, setRepoScans] = useState<RepositoryScan[]>([]);
  const [selectedScan, setSelectedScan] = useState<RepositoryScan | null>(null);
  const [scanFindings, setScanFindings] = useState<RepositoryFinding[]>([]);
  const [availableRepos, setAvailableRepos] = useState<GitHubAvailableRepo[]>([]);
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [selectedAvailableRepoId, setSelectedAvailableRepoId] = useState<number | null>(null);
  const [scanning, setScanning] = useState(false);
  const [connectingRepo, setConnectingRepo] = useState(false);
  const [creatingPlanFromScan, setCreatingPlanFromScan] = useState(false);
  const [findingCategoryFilter, setFindingCategoryFilter] = useState<string>('all');

  // New Node Form State
  const [showAddNodeModal, setShowAddNodeModal] = useState(false);
  const [newNodeType, setNewNodeType] = useState('requirement');
  const [newNodeKey, setNewNodeKey] = useState('');
  const [newNodeTitle, setNewNodeTitle] = useState('');

  const loadData = async () => {
    try {
      setLoading(true);
      const [projData, plansData, ctxData, ghConf, insts, repos] = await Promise.all([
        api.projects.get(tenantId, projectId),
        api.plans.list(tenantId, projectId),
        api.context.get(tenantId, projectId),
        api.github.getConfig(tenantId).catch(() => ({ is_configured: false, app_name: null, install_url: null, setup_required: true })),
        api.github.listInstallations(tenantId).catch(() => []),
        api.github.listProjectRepositories(tenantId, projectId).catch(() => []),
      ]);
      setProject(projData);
      setPlans(plansData);
      setContextNodes(ctxData.nodes);
      setContextEdges(ctxData.edges);
      setGithubConfig(ghConf);
      setInstallations(insts);
      setConnectedRepos(repos);

      if (repos.length > 0) {
        const first = repos[0];
        setSelectedRepo(first);
        loadRepoScans(first.id);
      }
    } catch (err: any) {
      if (err.status === 401) {
        router.push('/login');
        return;
      }
      setError(err.message || 'Failed to load project details.');
    } finally {
      setLoading(false);
    }
  };

  const loadRepoScans = async (repoId: string) => {
    try {
      const scans = await api.github.listScans(tenantId, projectId, repoId);
      setRepoScans(scans);
      if (scans.length > 0) {
        const latest = scans[0];
        setSelectedScan(latest);
        const findings = await api.github.getFindings(tenantId, projectId, latest.id);
        setScanFindings(findings);
      } else {
        setSelectedScan(null);
        setScanFindings([]);
      }
    } catch {
      // Non-fatal
    }
  };

  useEffect(() => {
    loadData();
  }, [tenantId, projectId]);

  const handleGeneratePlan = async () => {
    setGenerating(true);
    setError(null);
    try {
      const generated = await api.plans.generate(tenantId, projectId);
      router.push(`/workspaces/${tenantId}/projects/${projectId}/plans/${generated.id}`);
    } catch (err: any) {
      setError(err.message || 'Failed to generate plan.');
      setGenerating(false);
    }
  };

  const handleCreateNode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newNodeKey.trim()) return;

    try {
      await api.context.addNode(tenantId, projectId, {
        node_type: newNodeType,
        key: newNodeKey.trim(),
        data: { title: newNodeTitle || newNodeKey },
      });
      setShowAddNodeModal(false);
      setNewNodeKey('');
      setNewNodeTitle('');
      const ctxData = await api.context.get(tenantId, projectId);
      setContextNodes(ctxData.nodes);
      setContextEdges(ctxData.edges);
    } catch (err: any) {
      setError(err.message || 'Failed to create context node.');
    }
  };

  // ---------------------------------------------------------------------------
  // GitHub & Repository Action Handlers
  // ---------------------------------------------------------------------------

  const openConnectModal = async () => {
    setShowConnectModal(true);
    setError(null);
    if (installations.length > 0) {
      try {
        const available = await api.github.listInstallationRepositories(
          tenantId,
          installations[0].installation_id
        );
        setAvailableRepos(available);
      } catch (err: any) {
        setError(err.message || 'Failed to load repositories from GitHub.');
      }
    }
  };

  const handleConnectSelectedRepo = async () => {
    if (!selectedAvailableRepoId || installations.length === 0) return;
    const repoToConnect = availableRepos.find((r) => r.id === selectedAvailableRepoId);
    if (!repoToConnect) return;

    setConnectingRepo(true);
    setError(null);
    try {
      const connected = await api.github.connectRepository(tenantId, projectId, {
        installation_id: installations[0].id,
        github_repo_id: repoToConnect.id,
        owner: repoToConnect.owner,
        name: repoToConnect.name,
        full_name: repoToConnect.full_name,
        html_url: repoToConnect.html_url,
        is_private: repoToConnect.is_private,
        default_branch: repoToConnect.default_branch,
      });
      setShowConnectModal(false);
      setSelectedAvailableRepoId(null);
      const updatedRepos = await api.github.listProjectRepositories(tenantId, projectId);
      setConnectedRepos(updatedRepos);
      setSelectedRepo(connected);
      loadRepoScans(connected.id);
    } catch (err: any) {
      setError(err.message || 'Failed to link repository to project.');
    } finally {
      setConnectingRepo(false);
    }
  };

  const handleDisconnectRepo = async (repoId: string) => {
    if (!confirm('Are you sure you want to disconnect this repository? Past scan history will be preserved.')) return;
    try {
      await api.github.disconnectRepository(tenantId, projectId, repoId);
      const updatedRepos = await api.github.listProjectRepositories(tenantId, projectId);
      setConnectedRepos(updatedRepos);
      if (updatedRepos.length > 0) {
        setSelectedRepo(updatedRepos[0]);
        loadRepoScans(updatedRepos[0].id);
      } else {
        setSelectedRepo(null);
        setRepoScans([]);
        setSelectedScan(null);
        setScanFindings([]);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to disconnect repository.');
    }
  };

  const handleRunScan = async (repo: ConnectedRepository) => {
    setScanning(true);
    setError(null);
    try {
      const scan = await api.github.initiateScan(tenantId, projectId, repo.id, repo.selected_branch);
      await loadRepoScans(repo.id);
      setSelectedScan(scan);
      const findings = await api.github.getFindings(tenantId, projectId, scan.id);
      setScanFindings(findings);
      // Reload context graph
      const ctxData = await api.context.get(tenantId, projectId);
      setContextNodes(ctxData.nodes);
      setContextEdges(ctxData.edges);
    } catch (err: any) {
      setError(err.message || 'Repository scan failed.');
    } finally {
      setScanning(false);
    }
  };

  const handleCreatePlanFromScan = async () => {
    if (!selectedScan) return;
    setCreatingPlanFromScan(true);
    setError(null);
    try {
      const plan = await api.github.createPlanFromScan(tenantId, projectId, selectedScan.id);
      router.push(`/workspaces/${tenantId}/projects/${projectId}/plans/${plan.id}`);
    } catch (err: any) {
      setError(err.message || 'Failed to synthesize execution plan from findings.');
      setCreatingPlanFromScan(false);
    }
  };

  const filteredFindings = scanFindings.filter((f) => {
    if (findingCategoryFilter === 'all') return true;
    return f.category === findingCategoryFilter;
  });

  return (
    <div className="min-h-screen bg-surface-ground text-slate-100 flex flex-col font-sans">
      <Navbar tenantId={tenantId} />

      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full space-y-6">
        {/* Back Link */}
        <Link
          href={`/workspaces/${tenantId}/projects`}
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Projects
        </Link>

        {error && (
          <div className="p-4 rounded-xl bg-red-950/40 border border-red-800 text-red-200 text-sm flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-400">
            <Loader2 className="w-8 h-8 animate-spin text-brand-blue mb-4" />
            <p className="text-sm">Loading project context...</p>
          </div>
        ) : !project ? (
          <div className="p-8 text-center bg-surface rounded-xl border border-surface-border">
            <p className="text-slate-400">Project not found.</p>
          </div>
        ) : (
          <>
            {/* Project Header */}
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 p-6 rounded-2xl bg-surface border border-surface-border">
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-bold tracking-tight text-white">{project.name}</h1>
                  <span className="text-xs font-mono uppercase px-2 py-0.5 rounded bg-surface-muted text-slate-400 border border-surface-border">
                    {project.category || 'saas'}
                  </span>
                  <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    {project.status}
                  </span>
                </div>

                {project.description && (
                  <p className="text-xs text-slate-400">{project.description}</p>
                )}

                <div className="flex items-center gap-4 text-[11px] text-slate-500 font-mono pt-1">
                  <span>ID: {project.id}</span>
                  {project.targetLaunchDate && (
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3 h-3 text-slate-400" />
                      Target: {new Date(project.targetLaunchDate).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>

              <button
                onClick={handleGeneratePlan}
                disabled={generating}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan hover:opacity-95 disabled:opacity-50 text-white text-xs font-medium shadow-md shadow-brand-blue/20 whitespace-nowrap self-start lg:self-auto transition-all"
              >
                {generating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Decomposing Goal...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    Generate Execution Plan
                  </>
                )}
              </button>
            </div>

            {/* Primary Goal Box */}
            <div className="p-6 rounded-2xl bg-surface-muted border border-surface-border space-y-2">
              <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-brand-cyan" />
                Primary Business Goal
              </span>
              <p className="text-sm text-slate-200 leading-relaxed font-sans bg-surface/50 p-4 rounded-xl border border-surface-border">
                &ldquo;{project.primaryGoal}&rdquo;
              </p>
            </div>

            {/* Tabs */}
            <div className="border-b border-surface-border flex items-center gap-6 text-xs font-medium">
              <button
                onClick={() => setActiveTab('plans')}
                className={`pb-3 flex items-center gap-2 border-b-2 transition-colors ${
                  activeTab === 'plans'
                    ? 'border-brand-cyan text-brand-cyan font-semibold'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <Layers className="w-4 h-4" />
                Execution Plans ({plans.length})
              </button>
              <button
                onClick={() => setActiveTab('repositories')}
                className={`pb-3 flex items-center gap-2 border-b-2 transition-colors ${
                  activeTab === 'repositories'
                    ? 'border-brand-cyan text-brand-cyan font-semibold'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <GitBranch className="w-4 h-4" />
                Connected Repositories ({connectedRepos.length})
              </button>
              <button
                onClick={() => setActiveTab('context')}
                className={`pb-3 flex items-center gap-2 border-b-2 transition-colors ${
                  activeTab === 'context'
                    ? 'border-brand-cyan text-brand-cyan font-semibold'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <Network className="w-4 h-4" />
                Business Context Graph ({contextNodes.length} nodes)
              </button>
            </div>

            {/* TAB 1: Execution Plans List */}
            {activeTab === 'plans' && (
              <div className="space-y-4">
                {plans.length === 0 ? (
                  <div className="p-12 text-center rounded-2xl bg-surface border border-surface-border">
                    <Layers className="w-10 h-10 text-slate-500 mx-auto mb-3" />
                    <h3 className="text-sm font-semibold text-white">No plans generated yet</h3>
                    <p className="text-xs text-slate-400 max-w-sm mx-auto mt-1 mb-6">
                      Click &ldquo;Generate Execution Plan&rdquo; above to run the deterministic rule-based planner and turn your goal into ordered tasks.
                    </p>
                    <button
                      onClick={handleGeneratePlan}
                      disabled={generating}
                      className="px-4 py-2 rounded-lg bg-brand-blue text-white text-xs font-medium"
                    >
                      Generate First Plan
                    </button>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {plans.map((p) => (
                      <Link
                        key={p.id}
                        href={`/workspaces/${tenantId}/projects/${projectId}/plans/${p.id}`}
                        className="p-5 rounded-xl bg-surface border border-surface-border hover:border-brand-cyan/50 transition-all flex flex-col justify-between group space-y-4"
                      >
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-xs px-2 py-0.5 rounded bg-surface-muted text-slate-300">
                              v{p.version}
                            </span>
                            <span
                              className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded ${
                                p.status === 'approved'
                                  ? 'bg-emerald-500/15 text-emerald-400'
                                  : p.status === 'rejected'
                                  ? 'bg-red-500/15 text-red-400'
                                  : 'bg-amber-500/15 text-amber-400'
                              }`}
                            >
                              {p.status}
                            </span>
                          </div>
                          <h3 className="text-sm font-semibold text-white group-hover:text-brand-cyan transition-colors line-clamp-2">
                            {p.goal}
                          </h3>
                        </div>

                        <div className="pt-3 border-t border-surface-border/50 flex items-center justify-between text-xs text-slate-400">
                          <span>{p.taskCount || 0} tasks</span>
                          <span className="flex items-center gap-1 text-brand-cyan font-medium group-hover:translate-x-0.5 transition-transform">
                            Inspect Plan <ArrowRight className="w-3.5 h-3.5" />
                          </span>
                        </div>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: Connected Repositories & Intelligence (Phase 2) */}
            {activeTab === 'repositories' && (
              <div className="space-y-6">
                {/* GitHub App Configuration Status Banner */}
                {githubConfig && !githubConfig.is_configured && (
                  <div className="p-6 rounded-2xl bg-amber-950/20 border border-amber-800/40 space-y-3">
                    <div className="flex items-center gap-2 text-amber-400 font-semibold text-sm">
                      <AlertTriangle className="w-5 h-5 shrink-0" />
                      <span>GitHub App Integration Setup Required</span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed max-w-3xl">
                      To connect repositories and perform read-only codebase scans, a GitHub App must be configured on the server.
                      Register a GitHub App in GitHub Developer Settings with read-only permissions for Repository Metadata and Contents,
                      and add <code className="bg-surface-muted px-1.5 py-0.5 rounded text-amber-300">GITHUB_APP_ID</code> and{' '}
                      <code className="bg-surface-muted px-1.5 py-0.5 rounded text-amber-300">GITHUB_APP_PRIVATE_KEY</code> to your environment.
                    </p>
                  </div>
                )}

                {/* Installation & Connect Bar */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-xl bg-surface border border-surface-border">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-surface-muted border border-surface-border flex items-center justify-center text-white">
                      <FolderGit2 className="w-5 h-5 text-brand-cyan" />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-white">Repository Connections</h3>
                      <p className="text-xs text-slate-400">
                        {installations.length > 0
                          ? `GitHub App installed for @${installations[0].account_login}`
                          : 'Connect a GitHub repository to inspect architecture and generate launch tasks'}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {githubConfig?.is_configured && installations.length === 0 && (
                      <a
                        href={githubConfig.install_url || '#'}
                        target="_blank"
                        rel="noreferrer"
                        className="px-4 py-2 rounded-lg bg-brand-blue hover:bg-brand-blue/90 text-white text-xs font-semibold flex items-center gap-1.5 transition-all shadow-md shadow-brand-blue/20"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        Install GitHub App
                      </a>
                    )}

                    {installations.length > 0 && (
                      <button
                        onClick={openConnectModal}
                        className="px-4 py-2 rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan hover:opacity-95 text-white text-xs font-semibold flex items-center gap-1.5 transition-all shadow-md"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        Link Repository
                      </button>
                    )}
                  </div>
                </div>

                {/* Connected Repositories Content */}
                {connectedRepos.length === 0 ? (
                  <div className="p-12 text-center rounded-2xl bg-surface border border-surface-border space-y-3">
                    <GitBranch className="w-10 h-10 text-slate-500 mx-auto mb-2" />
                    <h3 className="text-sm font-semibold text-white">No Repositories Linked</h3>
                    <p className="text-xs text-slate-400 max-w-md mx-auto">
                      Link a GitHub repository to run the automated Repository Inspector, uncover architecture patterns, discover security or testing gaps, and convert findings into an executable plan.
                    </p>
                    {installations.length > 0 && (
                      <button
                        onClick={openConnectModal}
                        className="px-4 py-2 rounded-lg bg-surface-muted hover:bg-surface border border-surface-border text-white text-xs font-medium"
                      >
                        Select from Available Repositories
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="space-y-6">
                    {/* Repository Detail Card */}
                    {selectedRepo && (
                      <div className="p-6 rounded-2xl bg-surface border border-surface-border space-y-6">
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-surface-border">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-sm font-bold text-white flex items-center gap-1.5">
                                {selectedRepo.is_private ? (
                                  <Lock className="w-4 h-4 text-amber-400" />
                                ) : (
                                  <Globe className="w-4 h-4 text-emerald-400" />
                                )}
                                {selectedRepo.full_name}
                              </span>
                              <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-surface-muted text-slate-400 border border-surface-border">
                                {selectedRepo.default_branch}
                              </span>
                              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                {selectedRepo.status}
                              </span>
                            </div>
                            <a
                              href={selectedRepo.html_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-xs text-brand-cyan hover:underline inline-flex items-center gap-1 font-mono"
                            >
                              {selectedRepo.html_url} <ExternalLink className="w-3 h-3" />
                            </a>
                          </div>

                          <div className="flex items-center gap-3">
                            <button
                              onClick={() => handleDisconnectRepo(selectedRepo.id)}
                              className="px-3 py-1.5 rounded-lg border border-red-900/40 bg-red-950/20 text-red-300 hover:bg-red-950/40 text-xs font-medium transition-colors flex items-center gap-1"
                              title="Disconnect repository"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              Disconnect
                            </button>
                            <button
                              onClick={() => handleRunScan(selectedRepo)}
                              disabled={scanning}
                              className="px-4 py-2 rounded-lg bg-brand-blue hover:bg-brand-blue/90 text-white text-xs font-semibold flex items-center gap-2 transition-all shadow-md shadow-brand-blue/20 disabled:opacity-50"
                            >
                              {scanning ? (
                                <>
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  Inspecting Repository...
                                </>
                              ) : (
                                <>
                                  <Play className="w-3.5 h-3.5 fill-white" />
                                  Scan Repository
                                </>
                              )}
                            </button>
                          </div>
                        </div>

                        {/* Selected Scan Report */}
                        {selectedScan ? (
                          <div className="space-y-6">
                            {/* Scan Summary Banner */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                              <div className="p-4 rounded-xl bg-surface-muted border border-surface-border space-y-1">
                                <span className="text-xs text-slate-400 block">Commit Analyzed</span>
                                <span className="font-mono text-sm font-semibold text-white flex items-center gap-1.5">
                                  <GitCommit className="w-4 h-4 text-brand-cyan" />
                                  {selectedScan.commit_sha.slice(0, 8)}
                                </span>
                              </div>
                              <div className="p-4 rounded-xl bg-surface-muted border border-surface-border space-y-1">
                                <span className="text-xs text-slate-400 block">Readiness Score</span>
                                <span className="font-mono text-lg font-bold text-brand-cyan">
                                  {selectedScan.scan_summary?.readiness_score ?? 100} / 100
                                </span>
                              </div>
                              <div className="p-4 rounded-xl bg-surface-muted border border-surface-border space-y-1">
                                <span className="text-xs text-slate-400 block">Files Inspected</span>
                                <span className="font-mono text-sm font-semibold text-white">
                                  {selectedScan.files_analyzed_count} files ({selectedScan.scan_summary?.total_files_discovered ?? 0} discovered)
                                </span>
                              </div>
                              <div className="p-4 rounded-xl bg-surface-muted border border-surface-border space-y-1">
                                <span className="text-xs text-slate-400 block">Verifiable Findings</span>
                                <span className="font-mono text-sm font-semibold text-amber-400">
                                  {selectedScan.findings_count} findings
                                </span>
                              </div>
                            </div>

                            {/* Observed Technologies */}
                            {selectedScan.scan_summary?.technologies && (
                              <div className="p-4 rounded-xl bg-surface-muted border border-surface-border space-y-2">
                                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                                  Observed Technology Stack
                                </span>
                                <div className="flex flex-wrap gap-2 pt-1">
                                  {Object.entries(selectedScan.scan_summary.technologies).map(([cat, items]) =>
                                    (items as string[]).map((tech) => (
                                      <span
                                        key={tech}
                                        className="text-xs font-mono px-2.5 py-1 rounded bg-surface text-slate-200 border border-surface-border flex items-center gap-1.5"
                                      >
                                        <span className="text-brand-cyan text-[10px] uppercase font-bold">{cat}:</span>
                                        {tech}
                                      </span>
                                    ))
                                  )}
                                </div>
                              </div>
                            )}

                            {/* Plan Generation Call-to-Action */}
                            <div className="p-5 rounded-xl bg-brand-blue/10 border border-brand-blue/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                              <div className="space-y-0.5">
                                <h4 className="text-sm font-semibold text-white flex items-center gap-1.5">
                                  <Sparkles className="w-4 h-4 text-brand-cyan" />
                                  Turn Repository Intelligence into Launch Plan
                                </h4>
                                <p className="text-xs text-slate-300">
                                  Synthesize observed gaps (testing, environment variables, security remediation) into ordered execution tasks.
                                </p>
                              </div>
                              <button
                                onClick={handleCreatePlanFromScan}
                                disabled={creatingPlanFromScan}
                                className="px-5 py-2.5 rounded-lg bg-brand-blue hover:bg-brand-blue/90 text-white text-xs font-semibold transition-all flex items-center gap-2 shadow-md shrink-0 disabled:opacity-50"
                              >
                                {creatingPlanFromScan ? (
                                  <Loader2 className="w-4 h-4 animate-spin" />
                                ) : (
                                  <Sparkles className="w-4 h-4" />
                                )}
                                Generate Plan from Findings
                              </button>
                            </div>

                            {/* Findings Filter Bar */}
                            <div className="space-y-4">
                              <div className="flex items-center justify-between flex-wrap gap-3">
                                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                                  <FileCode2 className="w-4 h-4 text-brand-cyan" />
                                  Findings & Launch Readiness Observations ({filteredFindings.length})
                                </h3>

                                <div className="flex items-center gap-1.5 flex-wrap">
                                  {['all', 'security', 'testing', 'deployment', 'database', 'application_structure'].map((cat) => (
                                    <button
                                      key={cat}
                                      onClick={() => setFindingCategoryFilter(cat)}
                                      className={`text-xs px-2.5 py-1 rounded-md transition-colors capitalize ${
                                        findingCategoryFilter === cat
                                          ? 'bg-brand-blue text-white font-semibold'
                                          : 'bg-surface-muted text-slate-400 hover:text-white'
                                      }`}
                                    >
                                      {cat.replace('_', ' ')}
                                    </button>
                                  ))}
                                </div>
                              </div>

                              {/* Findings Cards */}
                              <div className="space-y-3">
                                {filteredFindings.map((finding) => (
                                  <div
                                    key={finding.id}
                                    className="p-4 rounded-xl bg-surface-muted border border-surface-border space-y-3"
                                  >
                                    <div className="flex items-start justify-between gap-4">
                                      <div className="space-y-1">
                                        <div className="flex items-center gap-2 flex-wrap">
                                          <span
                                            className={`text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded ${
                                              finding.severity === 'critical'
                                                ? 'bg-red-500/20 text-red-400 border border-red-500/40'
                                                : finding.severity === 'high'
                                                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                                                : finding.severity === 'medium'
                                                ? 'bg-yellow-500/15 text-yellow-300 border border-yellow-500/30'
                                                : 'bg-slate-700/50 text-slate-300'
                                            }`}
                                          >
                                            {finding.severity}
                                          </span>
                                          <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-surface text-brand-cyan border border-surface-border">
                                            {finding.category.replace('_', ' ')}
                                          </span>
                                          <span
                                            className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded ${
                                              finding.verification_status === 'OBSERVED'
                                                ? 'bg-emerald-500/15 text-emerald-400'
                                                : finding.verification_status === 'NEEDS_REVIEW'
                                                ? 'bg-amber-500/15 text-amber-300'
                                                : 'bg-slate-800 text-slate-400'
                                            }`}
                                          >
                                            {finding.verification_status}
                                          </span>
                                        </div>
                                        <h4 className="text-sm font-semibold text-white">
                                          {finding.title}
                                        </h4>
                                      </div>

                                      {finding.file_path && (
                                        <span className="text-xs font-mono text-slate-400 shrink-0">
                                          {finding.file_path}
                                          {finding.line_start && `:${finding.line_start}`}
                                        </span>
                                      )}
                                    </div>

                                    <p className="text-xs text-slate-300 leading-relaxed">
                                      {finding.description}
                                    </p>

                                    {finding.evidence_excerpt && (
                                      <pre className="text-[11px] font-mono text-brand-cyan bg-surface-ground p-2.5 rounded border border-surface-border overflow-x-auto">
                                        {finding.evidence_excerpt}
                                      </pre>
                                    )}

                                    <div className="pt-2 border-t border-surface-border text-xs flex items-center justify-between text-slate-400">
                                      <span>
                                        Action:{' '}
                                        <strong className="text-slate-200">{finding.recommended_action}</strong>
                                      </span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className="p-8 text-center rounded-xl bg-surface-muted border border-surface-border space-y-2">
                            <Clock className="w-8 h-8 text-slate-500 mx-auto" />
                            <h4 className="text-sm font-semibold text-white">No Scans Recorded Yet</h4>
                            <p className="text-xs text-slate-400">
                              Click &ldquo;Scan Repository&rdquo; to analyze the repository contents at branch {selectedRepo.default_branch}.
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: Business Context Graph */}
            {activeTab === 'context' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-white">Business Context Entities</h3>
                    <p className="text-xs text-slate-400">
                      Typed domain nodes representing goals, requirements, constraints, repositories, and decisions.
                    </p>
                  </div>
                  <button
                    onClick={() => setShowAddNodeModal(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface border border-surface-border hover:bg-surface-muted text-xs font-medium text-slate-200"
                  >
                    <Plus className="w-3.5 h-3.5" /> Add Node
                  </button>
                </div>

                {contextNodes.length === 0 ? (
                  <div className="p-12 text-center rounded-2xl bg-surface border border-surface-border">
                    <Network className="w-10 h-10 text-slate-500 mx-auto mb-3" />
                    <h3 className="text-sm font-semibold text-white">Context graph is empty</h3>
                    <p className="text-xs text-slate-400 max-w-sm mx-auto mt-1 mb-6">
                      Context nodes are generated from your project goals, repository scans, and manual business constraints.
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {contextNodes.map((n) => (
                      <div
                        key={n.id}
                        className="p-4 rounded-xl bg-surface border border-surface-border hover:border-slate-700 transition-colors space-y-2"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono uppercase text-[10px] px-2 py-0.5 rounded bg-brand-blue/15 text-brand-cyan border border-brand-blue/30">
                            {n.nodeType}
                          </span>
                          <span className="text-[10px] font-mono text-slate-500">v{n.version}</span>
                        </div>
                        <div className="text-xs font-semibold text-white break-words">
                          {n.key}
                        </div>
                        <div className="text-[11px] text-slate-400 font-mono bg-surface-muted p-2 rounded border border-surface-border/50 max-h-24 overflow-y-auto">
                          {JSON.stringify(n.data, null, 2)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Connect Repository Modal */}
            {showConnectModal && (
              <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
                <div className="max-w-lg w-full bg-surface border border-surface-border p-6 rounded-2xl shadow-2xl space-y-5">
                  <div className="space-y-1">
                    <h3 className="text-base font-semibold text-white">Link GitHub Repository</h3>
                    <p className="text-xs text-slate-400">
                      Select an authorized repository from GitHub installation{' '}
                      {installations.length > 0 && <strong>@{installations[0].account_login}</strong>}.
                    </p>
                  </div>

                  {availableRepos.length === 0 ? (
                    <div className="p-8 text-center bg-surface-muted rounded-xl border border-surface-border text-xs text-slate-400 space-y-2">
                      <Loader2 className="w-6 h-6 animate-spin text-brand-blue mx-auto" />
                      <p>Loading accessible repositories from GitHub...</p>
                    </div>
                  ) : (
                    <div className="max-h-60 overflow-y-auto space-y-2 border border-surface-border rounded-xl p-2 bg-surface-ground">
                      {availableRepos.map((repo) => (
                        <div
                          key={repo.id}
                          onClick={() => setSelectedAvailableRepoId(repo.id)}
                          className={`p-3 rounded-lg border text-xs cursor-pointer transition-all flex items-center justify-between ${
                            selectedAvailableRepoId === repo.id
                              ? 'bg-brand-blue/15 border-brand-cyan text-white'
                              : 'bg-surface border-surface-border text-slate-300 hover:border-slate-700'
                          }`}
                        >
                          <div className="space-y-0.5">
                            <span className="font-semibold flex items-center gap-1.5">
                              {repo.is_private ? (
                                <Lock className="w-3.5 h-3.5 text-amber-400" />
                              ) : (
                                <Globe className="w-3.5 h-3.5 text-emerald-400" />
                              )}
                              {repo.full_name}
                            </span>
                            <span className="text-[10px] text-slate-400 font-mono">
                              default: {repo.default_branch}
                            </span>
                          </div>
                          {selectedAvailableRepoId === repo.id && (
                            <Check className="w-4 h-4 text-brand-cyan shrink-0" />
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex items-center justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setShowConnectModal(false)}
                      className="px-4 py-2 rounded-lg text-xs text-slate-400 hover:text-white"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleConnectSelectedRepo}
                      disabled={!selectedAvailableRepoId || connectingRepo}
                      className="px-4 py-2 rounded-lg bg-brand-blue hover:bg-brand-blue/90 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1.5"
                    >
                      {connectingRepo ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                      Link to Project
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Add Context Node Modal */}
            {showAddNodeModal && (
              <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
                <div className="max-w-md w-full bg-surface border border-surface-border p-6 rounded-2xl shadow-2xl space-y-4">
                  <h3 className="text-sm font-semibold text-white">Add Business Context Node</h3>
                  <form onSubmit={handleCreateNode} className="space-y-3">
                    <div className="space-y-1">
                      <label className="text-xs text-slate-300">Node Type</label>
                      <select
                        value={newNodeType}
                        onChange={(e) => setNewNodeType(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg bg-surface-muted border border-surface-border text-white text-xs"
                      >
                        <option value="requirement">Requirement</option>
                        <option value="goal">Goal</option>
                        <option value="constraint">Constraint</option>
                        <option value="decision">Decision</option>
                        <option value="launch_criterion">Launch Criterion</option>
                        <option value="integration_requirement">Integration Requirement</option>
                      </select>
                    </div>

                    <div className="space-y-1">
                      <label className="text-xs text-slate-300">Identifier Key *</label>
                      <input
                        type="text"
                        required
                        value={newNodeKey}
                        onChange={(e) => setNewNodeKey(e.target.value)}
                        placeholder="e.g. stripe_webhook_secret"
                        className="w-full px-3 py-2 rounded-lg bg-surface-muted border border-surface-border text-white text-xs font-mono"
                      />
                    </div>

                    <div className="space-y-1">
                      <label className="text-xs text-slate-300">Description / Title</label>
                      <input
                        type="text"
                        value={newNodeTitle}
                        onChange={(e) => setNewNodeTitle(e.target.value)}
                        placeholder="e.g. Webhook signature for recurring invoice events"
                        className="w-full px-3 py-2 rounded-lg bg-surface-muted border border-surface-border text-white text-xs"
                      />
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-3 border-t border-surface-border">
                      <button
                        type="button"
                        onClick={() => setShowAddNodeModal(false)}
                        className="px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-white"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-3.5 py-1.5 rounded-lg bg-brand-blue hover:bg-blue-600 text-white text-xs font-medium"
                      >
                        Save Node
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
