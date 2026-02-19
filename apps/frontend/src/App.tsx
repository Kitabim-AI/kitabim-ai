import React, { useEffect } from 'react';
import { Shell } from './components/layout/Shell';
import { HomeView } from './components/library/HomeView';
import { LibraryView } from './components/library/LibraryView';
import { AdminView } from './components/admin/AdminView';
import { AdminTabs } from './components/admin/AdminTabs';
import { ReaderView } from './components/reader/ReaderView';
import { ChatInterface } from './components/chat/ChatInterface';
import { AppProvider, useAppContext } from './context/AppContext';
import { PersistenceService } from './services/persistenceService';

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

  // Polling for processing books
  useEffect(() => {
    const hasProcessing = selectedBook?.pages?.some(
      r => r.status === 'pending' || r.status === 'processing'
    );
    // Poll only on admin page to show real-time OCR progress
    const shouldPoll = view === 'admin' && selectedBook && (selectedBook.status === 'processing' || hasProcessing);

    if (!shouldPoll) return;

    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | null = null;

    const pollSelectedBook = async () => {
      try {
        const fresh = await PersistenceService.getBookById(selectedBook.id);
        if (!cancelled && fresh) {
          setSelectedBook(fresh);
        }
      } catch (e) {
        console.error("Polling failed", e);
      }
    };

    pollSelectedBook();
    interval = setInterval(pollSelectedBook, 30000); // Poll every 30 seconds

    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [view, selectedBook?.id, selectedBook?.status, setSelectedBook]);

  useEffect(() => {
    refreshLibrary();
  }, [refreshLibrary]);

  return (
    <Shell>
      {view === 'home' && <HomeView />}
      {view === 'library' && <LibraryView />}
      {view === 'admin' && (
        <AdminTabs
          bookManagementPanel={<AdminView />}
        />
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
        />
      )}
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
