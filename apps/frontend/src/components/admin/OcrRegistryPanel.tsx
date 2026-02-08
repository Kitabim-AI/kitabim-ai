import React, { useState, useEffect } from 'react';
import {
  ScanSearch,
  Settings,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  BrainCircuit,
  ArrowRightLeft,
  ChevronRight,
  ShieldCheck,
  Activity,
  Zap,
  Eye,
  BookOpenText,
  Loader2
} from 'lucide-react';
import { OcrSuspect, OcrRegistryStats, OcrContext, Book } from '@shared/types';
import { RegistryService } from '../../services/registryService';
import { PersistenceService } from '../../services/persistenceService';
import { MarkdownContent } from '../common/MarkdownContent';
import { X as CloseIcon } from 'lucide-react';

interface ContextViewerProps {
  token: string;
  onOpenBook: (bookId: string, pageNumber: number, title: string, volume?: number | null) => void;
}

const ContextViewer: React.FC<ContextViewerProps> = ({ token, onOpenBook }) => {
  const [contexts, setContexts] = useState<OcrContext[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await RegistryService.getTokenContext(token);
        setContexts(data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [token]);

  if (loading) return (
    <div className="flex items-center gap-2 p-4 bg-slate-50 rounded-lg text-slate-400 text-xs italic animate-pulse">
      <Loader2 size={12} className="animate-spin" />
      Searching corpus for occurrences...
    </div>
  );

  if (contexts.length === 0) return (
    <div className="p-4 bg-slate-50 rounded-lg text-slate-400 text-xs italic">
      No context snippets found for this token.
    </div>
  );

  return (
    <div className="p-4 bg-indigo-50/50 rounded-xl space-y-3 border border-indigo-100/50">
      <div className="flex items-center gap-2 text-[10px] font-black text-indigo-400 uppercase tracking-widest">
        <BookOpenText size={12} />
        Corpus Occurrences
      </div>
      {contexts.map((ctx, i) => (
        <div key={i} className="flex flex-col gap-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400 font-bold">
            <div className="flex items-center gap-2">
              <span>{ctx.bookTitle}</span>
              {ctx.volume && (
                <span className="px-1.5 py-0.5 bg-slate-100 rounded text-slate-500">Vol {ctx.volume}</span>
              )}
            </div>
            <div
              className="flex items-center gap-1 cursor-pointer hover:text-indigo-600 transition-colors group/link"
              onClick={() => onOpenBook(ctx.bookId, ctx.pageNumber, ctx.bookTitle, ctx.volume)}
              title="Click to open this page in Reader"
            >
              <span className="group-hover/link:underline">Page {ctx.pageNumber}</span>
              <Eye size={10} className="opacity-0 group-hover/link:opacity-100 transition-opacity" />
            </div>
          </div>
          <div
            className="p-3 bg-white rounded-lg border border-indigo-100 text-sm leading-relaxed text-slate-700 shadow-sm relative group/snippet"
            dir="rtl"
          >
            <div className="flex flex-wrap items-center">
              {ctx.snippet.split(ctx.matchedToken || token).map((part, pi, arr) => (
                <React.Fragment key={pi}>
                  {part}
                  {pi < arr.length - 1 && (
                    <span className="bg-amber-200 text-amber-900 font-bold px-1 rounded mx-0.5">
                      {ctx.matchedToken || token}
                    </span>
                  )}
                </React.Fragment>
              ))}
            </div>

            <button
              onClick={() => {
                const target = ctx.matchedToken || token;
                const fix = prompt(`Apply Global Fix for "${target}"?`, target);
                if (fix && fix !== target) {
                  (window as any)._applyGlobalCorrection?.(target, fix);
                }
              }}
              className="absolute left-2 top-2 opacity-0 group-hover/snippet:opacity-100 p-1.5 bg-indigo-600 text-white rounded-md text-[9px] font-black uppercase transition-all hover:bg-indigo-700 shadow-lg"
              title="Fix this variant everywhere"
            >
              Fix Globally
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

interface OcrRegistryPanelProps {
  onOpenReader?: (book: Book, startPage?: number) => void;
  books?: Book[];
}

export const OcrRegistryPanel: React.FC<OcrRegistryPanelProps> = ({ onOpenReader, books = [] }) => {
  const [stats, setStats] = useState<OcrRegistryStats | null>(null);
  const [candidates, setCandidates] = useState<OcrSuspect[]>([]);
  const [tokens, setTokens] = useState<OcrSuspect[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRebuilding, setIsRebuilding] = useState(false);
  const [activeTab, setActiveTab] = useState<'candidates' | 'verified' | 'suspects'>('candidates');
  const [expandedToken, setExpandedToken] = useState<string | null>(null);
  const [limit, setLimit] = useState(50);
  const [showRebuildModal, setShowRebuildModal] = useState(false);

  const [previewPage, setPreviewPage] = useState<{ bookId: string; pageNumber: number; text: string; title: string; volume?: number | null } | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  const handleOpenBook = async (bookId: string, pageNumber: number, title: string, volume?: number | null) => {
    setIsPreviewLoading(true);
    try {
      const page = await PersistenceService.getPage(bookId, pageNumber);
      if (page) {
        setPreviewPage({
          bookId,
          pageNumber,
          text: page.text,
          title: title,
          volume: volume
        });
      } else {
        alert("Could not load page content.");
      }
    } catch (err) {
      console.error(err);
      alert("Error loading page.");
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const data = await RegistryService.getStats();
      setStats(data);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchCandidates = async (currentLimit?: number) => {
    setIsLoading(true);
    try {
      const data = await RegistryService.getCandidates(currentLimit || limit, 0.6);
      setCandidates(data);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchTokens = async (type: 'verified' | 'suspects') => {
    setIsLoading(true);
    try {
      const status = type === 'suspects' ? 'suspect' : 'verified';
      const data = await RegistryService.getTokens(status, 100);
      setTokens(data);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    if (activeTab === 'candidates') {
      fetchCandidates(limit);
    } else {
      fetchTokens(activeTab);
    }
  }, [activeTab, limit]);

  const handleRebuild = async () => {
    setShowRebuildModal(false);
    setIsRebuilding(true);
    try {
      await RegistryService.rebuildRegistry();
      await fetchStats();
      if (activeTab === 'candidates') fetchCandidates();
      else fetchTokens(activeTab);
    } catch (err) {
      console.error(err);
    } finally {
      setIsRebuilding(false);
    }
  };

  const handleGenerate = async () => {
    setIsLoading(true);
    try {
      await RegistryService.generateCandidates(100);
      setLimit(50);
      await fetchCandidates(50);
      setActiveTab('candidates');
    } catch (err) {
      alert('Failed to generate candidates');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRefresh = () => {
    fetchStats();
    if (activeTab === 'candidates') fetchCandidates(limit);
    else fetchTokens(activeTab);
  };

  const handleVerify = async (token: string) => {
    if (activeTab === 'candidates') {
      setCandidates(prev => prev.filter(c => c.token !== token));
    } else {
      setTokens(prev => prev.filter(t => t.token !== token));
    }

    try {
      await RegistryService.verifyToken(token);
      fetchStats();
      if (activeTab === 'candidates') fetchCandidates();
      else fetchTokens(activeTab);
    } catch (err) {
      alert('Failed to verify token');
      if (activeTab === 'candidates') fetchCandidates();
      else fetchTokens(activeTab);
    }
  };

  const handleApplyCorrection = async (target: string, replacement: string) => {
    if (!target || !replacement || target === replacement) return;

    if (!confirm(`This will find ALL occurrences of "${target}" and replace them with "${replacement}" across every book in your library. Continue?`)) return;

    setIsLoading(true);
    try {
      const result = await RegistryService.applyGlobalCorrection(target, replacement);
      alert(`Successfully updated ${result.pages_updated} pages.`);
      fetchStats();
      if (activeTab === 'candidates') fetchCandidates();
      else fetchTokens(activeTab);
    } catch (err) {
      alert('Failed to apply correction');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    (window as any)._applyGlobalCorrection = handleApplyCorrection;
    return () => { delete (window as any)._applyGlobalCorrection; };
  }, [handleApplyCorrection]);

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
              <ScanSearch size={20} />
            </div>
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Total Tokens</span>
          </div>
          <p className="text-2xl font-black text-slate-800">{stats?.total_tokens.toLocaleString() || '---'}</p>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-emerald-50 text-emerald-600 rounded-lg">
              <CheckCircle2 size={20} />
            </div>
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Verified</span>
          </div>
          <p className="text-2xl font-black text-slate-800">{stats?.verified_tokens.toLocaleString() || '---'}</p>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-amber-50 text-amber-600 rounded-lg">
              <AlertCircle size={20} />
            </div>
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Suspects</span>
          </div>
          <p className="text-2xl font-black text-slate-800">{stats?.suspect_tokens.toLocaleString() || '---'}</p>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
              <ShieldCheck size={20} />
            </div>
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Health Score</span>
          </div>
          <div className="flex items-end gap-2">
            <p className="text-2xl font-black text-slate-800">{stats?.health_score || 0}%</p>
            <div className="flex-grow bg-slate-100 h-2 rounded-full mb-2 overflow-hidden">
              <div
                className="bg-indigo-600 h-full transition-all duration-1000"
                style={{ width: `${stats?.health_score || 0}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between bg-slate-800 p-4 rounded-xl text-white shadow-lg">
        <div className="flex items-center gap-4">
          <div className="flex flex-col">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em]">Corpus Engine</span>
            <span className="text-sm font-bold flex items-center gap-2">
              <Activity size={14} className="text-emerald-400" />
              Kitabim Statistical Consensus v3.0
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowRebuildModal(true)}
            disabled={isRebuilding}
            className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-xs font-bold transition-all active:scale-95 disabled:opacity-50"
          >
            <RotateCcw size={14} className={isRebuilding ? 'animate-spin' : ''} />
            {isRebuilding ? 'Rebuilding...' : 'Rebuild Registry'}
          </button>
          <button
            onClick={handleGenerate}
            disabled={isLoading}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-bold transition-all shadow-lg shadow-indigo-500/20 active:scale-95 disabled:opacity-50"
          >
            <BrainCircuit size={14} className={isLoading ? 'animate-pulse' : ''} />
            Generate Candidates
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <div className="border-b border-slate-100 p-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            {[
              { id: 'candidates', label: 'Analysis Results', icon: <Zap size={14} /> },
              { id: 'suspects', label: 'Suspect Pool', icon: <AlertCircle size={14} /> },
              { id: 'verified', label: 'Verified Lexicon', icon: <CheckCircle2 size={14} /> },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id as any)}
                className={`flex items-center gap-2 text-xs font-black uppercase tracking-widest pb-1 border-b-2 transition-all ${activeTab === t.id
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-slate-400 hover:text-slate-600'
                  }`}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={handleRefresh}
              disabled={isLoading}
              className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-all"
              title="Refresh List"
            >
              <RotateCcw size={14} className={isLoading ? 'animate-spin' : ''} />
            </button>
            <div className="text-[10px] font-bold text-slate-400 uppercase">
              Showing {activeTab === 'candidates' ? candidates.length : tokens.length} top items
            </div>
          </div>
        </div>

        <div className="p-0">
          {isLoading ? (
            <div className="p-20 flex flex-col items-center justify-center gap-4">
              <div className="w-12 h-12 border-4 border-slate-100 border-t-indigo-600 rounded-full animate-spin" />
              <span className="text-xs font-bold text-slate-500 animate-pulse">
                {activeTab === 'candidates' ? 'Running Statistical Matcher...' : 'Retrieving Lexicon Data...'}
              </span>
            </div>
          ) : (
            <>
              {activeTab === 'candidates' ? (
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-50 text-[10px] font-black text-slate-400 uppercase tracking-widest border-b border-slate-100">
                      <th className="px-6 py-3">Suspected Word</th>
                      <th className="px-6 py-3 text-center">Stats</th>
                      <th className="px-6 py-3">Correction Candidates</th>
                      <th className="px-6 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {candidates.map((suspect, idx) => (
                      <React.Fragment key={idx}>
                        <tr className="hover:bg-slate-50/50 transition-colors group">
                          <td className="px-6 py-4">
                            <div className="flex flex-col">
                              <span className="text-lg font-bold text-slate-900 leading-tight tracking-wide" dir="rtl">
                                {suspect.token}
                              </span>
                              <div className="flex items-center gap-2 mt-1">
                                <span className="px-1.5 py-0.5 bg-amber-50 text-amber-700 text-[9px] font-bold rounded uppercase">Suspect</span>
                                {suspect.candidates[0]?.distance === 1 && (
                                  <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 text-[9px] font-bold rounded uppercase">High Confidence</span>
                                )}
                              </div>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex flex-col items-center gap-1">
                              <span className="text-xs font-bold text-slate-700">{suspect.frequency} hits</span>
                              <span className="text-[10px] text-slate-400">{suspect.bookSpan} books</span>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex flex-wrap gap-2">
                              {suspect.candidates.map((cand, ci) => (
                                <div
                                  key={ci}
                                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all ${ci === 0
                                    ? 'bg-indigo-50 border-indigo-200 text-indigo-900 shadow-sm'
                                    : 'bg-white border-slate-100 text-slate-600'
                                    }`}
                                >
                                  <span className="font-bold text-base" dir="rtl">{cand.token}</span>
                                  <div className="flex flex-col items-start border-l border-current/10 pl-2 ml-1">
                                    <span className="text-[9px] font-black opacity-60">{(cand.confidence * 100).toFixed(0)}%</span>
                                    <span className="text-[8px] opacity-40">{cand.frequency}x</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </td>
                          <td className="px-6 py-4 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <button
                                onClick={() => setExpandedToken(expandedToken === suspect.token ? null : suspect.token)}
                                className={`p-2.5 rounded-xl transition-all ${expandedToken === suspect.token
                                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-200'
                                  : 'bg-white border border-slate-200 text-slate-400 hover:border-indigo-200 hover:text-indigo-600'
                                  }`}
                                title="View Context"
                              >
                                <Eye size={16} />
                              </button>
                              <button
                                onClick={() => handleVerify(suspect.token)}
                                className="p-2.5 bg-white border border-slate-200 text-slate-400 rounded-xl hover:border-emerald-200 hover:text-emerald-600 transition-all"
                                title="Mark as Correct (Verify)"
                              >
                                <CheckCircle2 size={16} />
                              </button>
                              <button
                                onClick={() => {
                                  const fix = prompt(`Correct all occurrences of "${suspect.token}" across the library?`, suspect.candidates[0]?.token || suspect.token);
                                  if (fix && fix !== suspect.token) handleApplyCorrection(suspect.token, fix);
                                }}
                                className="p-2.5 bg-white border border-slate-200 text-slate-400 rounded-xl hover:border-indigo-200 hover:text-indigo-600 transition-all"
                                title="Apply Global Correction"
                              >
                                <ArrowRightLeft size={16} />
                              </button>
                            </div>
                          </td>
                        </tr>
                        {expandedToken === suspect.token && (
                          <tr className="bg-slate-50/80">
                            <td colSpan={4} className="px-6 py-4">
                              <ContextViewer token={suspect.token} onOpenBook={handleOpenBook} />
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              ) : (
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-50 text-[10px] font-black text-slate-400 uppercase tracking-widest border-b border-slate-100">
                      <th className="px-6 py-3">Token</th>
                      <th className="px-6 py-3">Frequency</th>
                      <th className="px-6 py-3">Book Span</th>
                      <th className="px-6 py-3">Last Seen</th>
                      <th className="px-6 py-3 text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {tokens.map((token, idx) => (
                      <React.Fragment key={idx}>
                        <tr className="hover:bg-slate-50/50 transition-colors group">
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-3">
                              <button
                                onClick={() => setExpandedToken(expandedToken === token.token ? null : token.token)}
                                className={`p-1.5 rounded-lg transition-all ${expandedToken === token.token
                                  ? 'bg-indigo-600 text-white'
                                  : 'text-slate-300 hover:text-indigo-600 hover:bg-indigo-50'
                                  }`}
                              >
                                <Eye size={14} />
                              </button>
                              <span className="text-lg font-bold text-slate-900 tracking-wide" dir="rtl">
                                {token.token}
                              </span>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <span className="text-xs font-medium text-slate-600">{token.frequency.toLocaleString()} hits</span>
                          </td>
                          <td className="px-6 py-4">
                            <span className="text-xs font-medium text-slate-600">{token.bookSpan} books</span>
                          </td>
                          <td className="px-6 py-4">
                            <span className="text-[10px] text-slate-400 font-mono">
                              {token.lastSeenAt ? new Date(token.lastSeenAt).toLocaleString() : '---'}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right">
                            <div className="flex items-center justify-end gap-2">
                              {activeTab === 'suspects' && (
                                <button
                                  onClick={() => handleVerify(token.token)}
                                  className="p-1.5 text-slate-300 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-all"
                                  title="Mark as Correct"
                                >
                                  <CheckCircle2 size={14} />
                                </button>
                              )}
                              <span className={`px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-tighter ${activeTab === 'verified' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                                }`}>
                                {activeTab === 'verified' ? 'Verified' : 'Suspect'}
                              </span>
                            </div>
                          </td>
                        </tr>
                        {expandedToken === token.token && (
                          <tr className="bg-slate-50/80">
                            <td colSpan={5} className="px-6 py-4">
                              <ContextViewer token={token.token} onOpenBook={handleOpenBook} />
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}

          {activeTab === 'candidates' && candidates.length > 0 && candidates.length === limit && (
            <div className="p-8 border-t border-slate-50 flex justify-center bg-slate-50/30">
              <button
                onClick={() => setLimit(prev => prev + 50)}
                className="px-8 py-3 bg-white border border-slate-200 text-slate-700 rounded-xl text-xs font-black uppercase tracking-widest hover:border-indigo-200 hover:text-indigo-600 hover:shadow-lg hover:shadow-indigo-500/5 transition-all active:scale-95 flex items-center gap-2"
              >
                <Zap size={14} className="text-amber-500" />
                Load More Suspects
              </button>
            </div>
          )}

          {!isLoading && (activeTab === 'candidates' ? candidates.length : tokens.length) === 0 && (
            <div className="p-20 flex flex-col items-center justify-center text-center">
              <ShieldCheck size={48} className="text-slate-200 mb-4" />
              <h3 className="font-bold text-slate-700">No data found</h3>
              <p className="text-slate-400 text-xs">Run "Generate Candidates" or "Rebuild Registry" to populate this view.</p>
            </div>
          )}
        </div>
      </div>

      {/* Quick Preview Modal */}
      {previewPage && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white w-full max-w-4xl max-h-[90vh] rounded-3xl shadow-2xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
            <header className="px-8 py-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <div>
                <h3 className="text-lg font-bold text-slate-900 line-clamp-1">{previewPage.title}</h3>
                <div className="flex items-center gap-2 mt-1">
                  {previewPage.volume && (
                    <span className="text-[10px] font-black text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full uppercase tracking-widest">
                      Vol {previewPage.volume}
                    </span>
                  )}
                  <span className="text-[10px] font-black text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full uppercase tracking-widest">
                    Page {previewPage.pageNumber}
                  </span>
                </div>
              </div>
              <button
                onClick={() => setPreviewPage(null)}
                className="p-2.5 text-slate-400 hover:bg-red-50 hover:text-red-500 rounded-xl transition-all active:scale-95"
              >
                <CloseIcon size={20} />
              </button>
            </header>

            <div className="flex-grow p-10 overflow-y-auto bg-[url('https://www.transparenttextures.com/patterns/paper-fibers.png')]">
              <div className="max-w-3xl mx-auto">
                <MarkdownContent
                  content={previewPage.text}
                  className="uyghur-text text-slate-800 text-xl leading-[1.8]"
                />
              </div>
            </div>

            <footer className="px-8 py-5 border-t border-slate-100 flex justify-end bg-slate-50/50">
              <button
                onClick={() => setPreviewPage(null)}
                className="px-6 py-2.5 bg-slate-900 text-white rounded-xl text-xs font-black hover:bg-slate-800 transition-all active:scale-95 shadow-lg shadow-slate-200"
              >
                CLOSE PREVIEW
              </button>
            </footer>
          </div>
        </div>
      )}

      {isPreviewLoading && (
        <div className="fixed inset-0 z-[101] flex items-center justify-center pointer-events-none">
          <div className="bg-white/90 backdrop-blur-md px-6 py-4 rounded-2xl shadow-xl flex items-center gap-3 border border-indigo-100">
            <Loader2 size={18} className="text-indigo-600 animate-spin" />
            <span className="text-sm font-bold text-indigo-900 uppercase tracking-widest">Loading Content...</span>
          </div>
        </div>
      )}

      {/* Rebuild Confirmation/Progress Modal */}
      {(showRebuildModal || isRebuilding) && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center p-6 bg-slate-900/60 backdrop-blur-md animate-in fade-in duration-300">
          <div className="bg-white w-full max-w-md rounded-3xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
            <div className="p-8 text-center">
              <div className={`mx-auto w-16 h-16 rounded-2xl flex items-center justify-center mb-6 ${isRebuilding ? 'bg-indigo-50 text-indigo-600' : 'bg-amber-50 text-amber-600'}`}>
                <RotateCcw size={32} className={isRebuilding ? 'animate-spin' : ''} />
              </div>

              <h3 className="text-xl font-black text-slate-800 mb-2">
                {isRebuilding ? 'Rebuilding Catalog' : 'Rebuild Registry?'}
              </h3>

              <p className="text-slate-500 text-sm leading-relaxed mb-8">
                {isRebuilding
                  ? 'Performing full corpus analysis. This compares every word across all books to build a high-precision vocabulary. This may take a few moments.'
                  : 'This will trigger a full scan of all processed books to identifying common words and potential errors. This is required to refresh the suspect list.'}
              </p>

              {isRebuilding ? (
                <div className="space-y-4">
                  <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                    <div className="bg-indigo-600 h-full w-full animate-progress-indefinite" />
                  </div>
                  <div className="flex items-center justify-center gap-2 text-indigo-600 font-black text-[10px] uppercase tracking-widest animate-pulse">
                    <Activity size={12} />
                    Processing Corpus...
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  <button
                    onClick={handleRebuild}
                    className="w-full py-4 bg-indigo-600 text-white rounded-2xl font-black text-xs uppercase tracking-widest hover:bg-indigo-500 shadow-xl shadow-indigo-200 transition-all active:scale-[0.98]"
                  >
                    START FULL REBUILD
                  </button>
                  <button
                    onClick={() => setShowRebuildModal(false)}
                    className="w-full py-4 bg-slate-50 text-slate-400 rounded-2xl font-black text-xs uppercase tracking-widest hover:bg-slate-100 transition-all"
                  >
                    CANCEL
                  </button>
                </div>
              )}
            </div>

            <div className="bg-slate-50 p-4 border-t border-slate-100 flex items-center justify-center gap-2">
              <ShieldCheck size={14} className="text-slate-400" />
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                System Health Analysis v3.0
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
