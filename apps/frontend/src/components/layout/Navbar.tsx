import React, { useRef } from 'react';
import { BookOpen, Globe, MessageSquare, LayoutDashboard, Search, Upload } from 'lucide-react';
import { AuthButton } from '../auth';
import { useAuth, useIsEditor } from '../../hooks/useAuth';

interface NavbarProps {
  view: 'library' | 'admin' | 'reader' | 'global-chat';
  setView: (view: 'library' | 'admin' | 'reader' | 'global-chat') => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  onFileUpload: (event: React.ChangeEvent<HTMLInputElement>) => void;
  clearChat: () => void;
  setPage: (page: number) => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  view,
  setView,
  searchQuery,
  setSearchQuery,
  onFileUpload,
  clearChat,
  setPage,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { isAuthenticated } = useAuth();
  const isEditor = useIsEditor();

  return (
    <nav className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between sticky top-0 z-50">
      <div className="flex items-center gap-8">
        <div className="flex items-center gap-2 cursor-pointer" onClick={() => setView('library')}>
          <div className="bg-indigo-600 p-1.5 rounded-lg shadow-sm shadow-indigo-100">
            <BookOpen className="text-white w-5 h-5" />
          </div>
          <span className="font-bold text-slate-900 tracking-tight text-xl">
            Kitabim<span className="text-indigo-600">.AI</span>
          </span>
        </div>
        <div className="hidden md:flex items-center gap-1">
          <button
            onClick={() => setView('library')}
            className={`px-4 py-2 rounded-md text-sm font-semibold transition-colors flex items-center gap-2 ${view === 'library' ? 'bg-indigo-50 text-indigo-700' : 'text-slate-500 hover:bg-slate-50'}`}
          >
            <Globe size={18} /> Global Library
          </button>
          {isAuthenticated && (
            <button
              onClick={() => { setView('global-chat'); clearChat(); }}
              className={`px-4 py-2 rounded-md text-sm font-semibold transition-colors flex items-center gap-2 ${view === 'global-chat' ? 'bg-indigo-50 text-indigo-700' : 'text-slate-500 hover:bg-slate-50'}`}
            >
              <MessageSquare size={18} /> Global Assistant
            </button>
          )}
          {isEditor && (
            <button
              onClick={() => { setView('admin'); setPage(1); }}
              className={`px-4 py-2 rounded-md text-sm font-semibold transition-colors flex items-center gap-2 ${view === 'admin' ? 'bg-indigo-50 text-indigo-700' : 'text-slate-500 hover:bg-slate-50'}`}
            >
              <LayoutDashboard size={18} /> Management
            </button>
          )}
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative hidden sm:block">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 w-4 h-4" />
          <input
            type="text"
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 pr-4 py-1.5 bg-slate-100 border-none rounded-full text-sm focus:ring-2 focus:ring-indigo-500 transition-all w-64"
          />
        </div>
        {isEditor && (
          <>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="bg-indigo-600 text-white px-4 py-1.5 rounded-lg text-sm font-semibold shadow-md shadow-indigo-100 flex items-center gap-2 hover:bg-indigo-700 active:scale-95 transition-transform"
            >
              <Upload size={16} /> ADD BOOK
            </button>
            <input
              type="file"
              ref={fileInputRef}
              onChange={onFileUpload}
              accept="application/pdf"
              className="hidden"
            />
          </>
        )}
        <AuthButton />
      </div>
    </nav>
  );
};
