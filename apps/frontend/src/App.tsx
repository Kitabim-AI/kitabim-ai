import React, { useEffect } from 'react';
import { Shell } from './components/layout/Shell';
import { HomeView } from './components/library/HomeView';
import { LibraryView } from './components/library/LibraryView';
import { AdminView } from './components/admin/AdminView';
import { AdminTabs } from './components/admin/AdminTabs';
import { ReaderView } from './components/reader/ReaderView';
import { ChatInterface } from './components/chat/ChatInterface';
import JoinUsView from './components/pages/JoinUsView';
import { SpellCheckView } from './components/spell-check';
import { AppProvider, useAppContext } from './context/AppContext';
import { PersistenceService } from './services/persistenceService';
import { useAuth, useIsEditor } from './hooks/useAuth';
import { useUyghurInput } from './hooks/useUyghurInput';

const AppContent: React.FC = () => {
  const {
    view,
    selectedBook,
    setSelectedBook,
    books,
    totalReady,
    chat,
    refreshLibrary,
    setView,
    previousView
  } = useAppContext();

  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const isEditor = useIsEditor();

  useUyghurInput();

  // Unified Route Guard
  useEffect(() => {
    const handleGuard = () => {
      if (authLoading) return;
      const protectedViews = ['admin', 'spell-check'];
      if (protectedViews.includes(view) && !isEditor) {
        console.warn(`Unauthorized access attempt to ${view}. Redirecting to home.`);
        setView('home');
      }
    };
    handleGuard();
    // Return nothing explicitly
    return undefined;
  }, [view, isEditor, authLoading, setView]);

  // Polling for processing books
  useEffect(() => {
    const runPolling = () => {
      const isProcessing = (s?: string) => s === 'ocr_processing' || s === 'indexing' || s === 'ocr_done';
      const hasProcessing = selectedBook?.pages?.some(
        r => r.status === 'pending' || isProcessing(r.status)
      );
      const shouldPoll = view === 'admin' && selectedBook && (isProcessing(selectedBook.status) || hasProcessing);

      if (!shouldPoll) return null;

      let cancelled = false;
      const interval = setInterval(async () => {
        try {
          const fresh = await PersistenceService.getBookById(selectedBook.id);
          if (!cancelled && fresh) setSelectedBook(fresh);
        } catch (e) {
          console.error("Polling failed", e);
        }
      }, 30000);

      return () => {
        cancelled = true;
        clearInterval(interval);
      };
    };

    const cleanup = runPolling();
    return cleanup || undefined;
  }, [view, selectedBook?.id, selectedBook?.status, setSelectedBook]);

  // Auth Loading Shield
  if (authLoading && (view === 'admin' || view === 'spell-check')) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-white z-[999]">
        <div className="w-12 h-12 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
      </div>
    );
  }

  // Determine authorized content
  const isAuthorizedToView = !(['admin', 'spell-check'].includes(view)) || isEditor;

  return (
    <Shell>
      {view === 'home' && <HomeView />}
      {view === 'library' && <LibraryView />}
      
      {/* Protected Views - Strictly Conditional */}
      {view === 'admin' && isAuthorizedToView && (
        <AdminTabs bookManagementPanel={<AdminView />} />
      )}
      {view === 'spell-check' && isAuthorizedToView && (
        <SpellCheckView />
      )}

      {view === 'reader' && selectedBook && <ReaderView />}
      {view === 'global-chat' && (
        <ChatInterface
          type="global"
          books={books}
          totalReady={totalReady}
          chatMessages={chat.chatMessages}
          chatInput={chat.chatInput}
          setChatInput={chat.setChatInput}
          onSendMessage={chat.handleSendMessage}
          isChatting={chat.isChatting}
          streamingMessage={chat.streamingMessage}
          usageStatus={chat.usageStatus}
          onClose={() => setView(previousView)}
          chatContainerRef={chat.chatContainerRef}
          selectedCharacterId={chat.selectedCharacterId}
          setSelectedCharacterId={chat.setSelectedCharacterId}
        />
      )}
      {view === 'join-us' && <JoinUsView />}
    </Shell>
  );
};

const App: React.FC = () => {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
};

export default App;
