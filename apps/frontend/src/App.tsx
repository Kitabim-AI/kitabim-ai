import React, { useState, useEffect } from 'react';
import { Navbar } from './components/layout/Navbar';
import { HomeView } from './components/library/HomeView';
import { LibraryView } from './components/library/LibraryView';
import { AdminView } from './components/admin/AdminView';
import { AdminTabs } from './components/admin/AdminTabs';
import { ReaderView } from './components/reader/ReaderView';
import { ChatInterface } from './components/chat/ChatInterface';
import { Modal } from './components/common/Modal';
import { RefreshCw } from 'lucide-react';
import { useI18n } from './i18n/I18nContext';

import { useBooks } from './hooks/useBooks';
import { useChat } from './hooks/useChat';
import { useBookActions } from './hooks/useBookActions';
import { PersistenceService } from './services/persistenceService';
import { Book } from '@shared/types';

const App: React.FC = () => {
  const { t } = useI18n();
  const [view, setView] = useState<'home' | 'library' | 'admin' | 'reader' | 'global-chat'>('home');
  const [searchQuery, setSearchQuery] = useState('');
  const [homeSearchQuery, setHomeSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [selectedBook, setSelectedBook] = useState<Book | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [currentPage, setCurrentPage] = useState<number | null>(null);
  const [editingPageNum, setEditingPageNum] = useState<number | null>(null);
  const [tempPageText, setTempPageText] = useState('');
  const [fontSize, setFontSize] = useState(20);

  const [editingBookCategoriesId, setEditingBookCategoriesId] = useState<string | null>(null);
  const [editingCategoriesList, setEditingCategoriesList] = useState<string[]>([]);
  const [tempCategories, setTempCategories] = useState('');

  const [editingBookAuthorId, setEditingBookAuthorId] = useState<string | null>(null);
  const [tempAuthor, setTempAuthor] = useState('');
  const [editingBookVolumeId, setEditingBookVolumeId] = useState<string | null>(null);
  const [tempVolume, setTempVolume] = useState('');
  const [editingBookTitleId, setEditingBookTitleId] = useState<string | null>(null);
  const [tempTitle, setTempTitle] = useState('');
  const loaderRef = React.useRef<HTMLDivElement>(null);
  const isPollingSelectedRef = React.useRef(false);

  const [modal, setModal] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    type: 'alert' | 'confirm';
    confirmText?: string;
    onConfirm?: () => void;
    destructive?: boolean;
  }>({
    isOpen: false,
    title: '',
    message: '',
    type: 'alert',
  });

  const {
    books,
    setBooks,
    totalBooks,
    totalReady,
    sortedBooks,
    sortConfig,
    toggleSort,
    refreshLibrary,
    loadMoreShelf,
    isLoading,
    isLoadingMoreShelf,
    hasMoreShelf,
  } = useBooks(view, view === 'home' ? homeSearchQuery : searchQuery, pageSize, page, view === 'home' ? selectedCategory : undefined);

  const {
    chatMessages,
    setChatMessages,
    chatInput,
    setChatInput,
    isChatting,
    handleSendMessage,
    clearChat,
    chatContainerRef,
  } = useChat(view, selectedBook, currentPage);

  const {
    isCheckingGlobal,
    handleFileUpload,
    handleStartOcr,
    handleRetryFailedOcr,
    handleReProcessPage,
    handleReindexBook,
    handleUpdatePage,
    openReader,
    saveCorrections,
    handleDeleteBook,
    handleSaveCategories,
    handleSaveAuthor,
    handleSaveTitle,
    handleSaveVolume,
    handleToggleVisibility,
  } = useBookActions(refreshLibrary, setBooks, setSelectedBook, setView, setModal);

  // Sync selectedBook with fresh data from the books list
  useEffect(() => {
    if (selectedBook) {
      const updated = books.find(b => b.id === selectedBook.id);
      if (updated && (updated.status !== selectedBook.status || updated.lastUpdated !== selectedBook.lastUpdated)) {
        setSelectedBook(prev => {
          if (!prev) return updated;
          return {
            ...updated,
            pages: (prev.pages && prev.pages.some(r => r.text)) ? prev.pages : updated.pages
          };
        });
      }
    }
  }, [books, selectedBook]);

  // Sync global edit content with latest page data
  // Sync global edit content with latest page data - REMOVED to prevent overwriting full content with partial initial load
  // useEffect(() => {
  //   if (selectedBook && !isEditing) {
  //     const combinedText = [...selectedBook.pages]
  //       .sort((a, b) => Number(a.pageNumber) - Number(b.pageNumber))
  //       .map(r => r.text || '')
  //       .join('\n\n');

  //     if (combinedText !== editContent) {
  //       setEditContent(combinedText);
  //     }
  //   }
  // }, [selectedBook?.pages, isEditing, editContent]);

  useEffect(() => {
    refreshLibrary();
  }, [refreshLibrary]);

  useEffect(() => {
    const hasProcessingPage = selectedBook?.pages?.some(
      r => r.status === 'pending' || r.status === 'processing'
    );
    // Poll only on admin page to show real-time OCR progress
    // Disabled on reader page to prevent overwriting manual edits
    const shouldPoll = view === 'admin' && selectedBook && (selectedBook.status === 'processing' || hasProcessingPage);

    if (!shouldPoll) return;

    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | null = null;

    const shouldDelayInitialPoll = () => {
      if (!selectedBook?.lastUpdated) return false;
      const updatedAt = selectedBook.lastUpdated instanceof Date
        ? selectedBook.lastUpdated.getTime()
        : new Date(selectedBook.lastUpdated).getTime();
      if (Number.isNaN(updatedAt)) return false;
      const recentlyUpdated = Date.now() - updatedAt < 1500;
      const hasPendingEmpty = selectedBook.pages?.some(
        r => (r.status === 'pending' || r.status === 'processing') && !r.text
      );
      return recentlyUpdated && hasPendingEmpty;
    };

    const pollSelectedBook = async () => {
      if (isPollingSelectedRef.current || !selectedBook) return;
      isPollingSelectedRef.current = true;
      try {
        const fresh = await PersistenceService.getBookById(selectedBook.id);
        if (!cancelled && fresh) {
          setSelectedBook(prev => {
            if (!prev || prev.id !== fresh.id) return prev;
            return {
              ...fresh,
            };
          });
        }
      } finally {
        isPollingSelectedRef.current = false;
      }
    };

    const delay = shouldDelayInitialPoll() ? 1500 : 0;
    const timeout = setTimeout(() => {
      pollSelectedBook();
      interval = setInterval(pollSelectedBook, 60000); // Poll every 60 seconds
    }, delay);

    return () => {
      cancelled = true;
      clearTimeout(timeout);
      if (interval) clearInterval(interval);
    };
  }, [view, selectedBook?.id, selectedBook?.status, selectedBook?.pages]);

  return (
    <div className="min-h-screen bg-transparent flex flex-col font-sans relative overflow-hidden">
      <Navbar
        view={view}
        setView={setView}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        onFileUpload={handleFileUpload}
        clearChat={clearChat}
        setPage={setPage}
      />

      <main className="flex-grow p-8 max-w-[1600px] mx-auto w-full relative z-10">
        {isLoading && view !== 'reader' && (
          <div className="absolute inset-0 bg-white/40 backdrop-blur-md z-40 flex items-center justify-center min-h-[400px] rounded-[40px]">
            <div className="flex flex-col items-center gap-6">
              <div className="relative">
                <div className="w-16 h-16 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
                <div className="absolute inset-0 flex items-center justify-center text-[#0369a1]">
                  <RefreshCw size={24} className="animate-pulse" />
                </div>
              </div>
              <span className="text-sm font-black text-[#0369a1] uppercase tracking-[0.3em] animate-pulse">{t('common.loadingApp')}</span>
            </div>
          </div>
        )}

        {view === 'home' && (
          <HomeView
            books={sortedBooks}
            isInitialLoading={isLoading}
            isLoadingMore={isLoadingMoreShelf}
            hasMore={hasMoreShelf}
            searchQuery={homeSearchQuery}
            setSearchQuery={setHomeSearchQuery}
            selectedCategory={selectedCategory}
            setSelectedCategory={setSelectedCategory}
            onBookClick={(book) => openReader(book, setEditContent, setChatMessages, setCurrentPage)}
            loaderRef={loaderRef}
            loadMore={loadMoreShelf}
          />
        )}

        {view === 'library' && (
          <LibraryView
            books={sortedBooks}
            isInitialLoading={isLoading}
            isLoadingMore={isLoadingMoreShelf}
            hasMore={hasMoreShelf}
            searchQuery={searchQuery}
            onBookClick={(book) => openReader(book, setEditContent, setChatMessages, setCurrentPage)}
            loaderRef={loaderRef}
            loadMore={loadMoreShelf}
          />
        )}

        {view === 'admin' && (
          <AdminTabs
            bookManagementPanel={
              <AdminView
                books={sortedBooks}
                isCheckingGlobal={isCheckingGlobal}
                sortConfig={sortConfig}
                toggleSort={toggleSort}
                page={page}
                pageSize={pageSize}
                totalBooks={totalBooks}
                onPageChange={setPage}
                onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
                onOpenReader={(book) => openReader(book, setEditContent, setChatMessages, setCurrentPage)}
                onStartOcr={handleStartOcr}
                onRetryFailedOcr={handleRetryFailedOcr}

                onReindex={handleReindexBook}
                onDeleteBook={(id) => handleDeleteBook(id, selectedBook?.id)}
                editingBookCategoriesId={editingBookCategoriesId}
                setEditingBookCategoriesId={setEditingBookCategoriesId}
                editingCategoriesList={editingCategoriesList}
                setEditingCategoriesList={setEditingCategoriesList}
                tempCategories={tempCategories}
                setTempCategories={setTempCategories}
                handleSaveCategories={(id, cats) => handleSaveCategories(id, cats, setEditingBookCategoriesId, setEditingCategoriesList)}

                editingBookAuthorId={editingBookAuthorId}
                setEditingBookAuthorId={setEditingBookAuthorId}
                tempAuthor={tempAuthor}
                setTempAuthor={setTempAuthor}
                handleSaveAuthor={(id, author) => handleSaveAuthor(id, author, setEditingBookAuthorId, setTempAuthor)}

                editingBookTitleId={editingBookTitleId}
                setEditingBookTitleId={setEditingBookTitleId}
                tempTitle={tempTitle}
                setTempTitle={setTempTitle}
                handleSaveTitle={(id, title) => handleSaveTitle(id, title, setEditingBookTitleId, setTempTitle)}

                editingBookVolumeId={editingBookVolumeId}
                setEditingBookVolumeId={setEditingBookVolumeId}
                tempVolume={tempVolume}
                setTempVolume={setTempVolume}
                handleSaveVolume={(id, volume) => handleSaveVolume(id, volume, setEditingBookVolumeId, setTempVolume)}
                onToggleVisibility={handleToggleVisibility}
              />
            }
          />
        )}

        {view === 'reader' && selectedBook && (
          <ReaderView
            selectedBook={selectedBook}
            isEditing={isEditing}
            setIsEditing={setIsEditing}
            editContent={editContent}
            setEditContent={setEditContent}
            onSaveCorrections={() => saveCorrections(selectedBook, editContent, setIsEditing)}
            fontSize={fontSize}
            setFontSize={setFontSize}
            onClose={() => setView('library')}
            onReProcessPage={handleReProcessPage}
            onUpdatePage={(id, num, text) => handleUpdatePage(id, num, text, setEditingPageNum)}
            currentPage={currentPage}
            setCurrentPage={setCurrentPage}
            editingPageNum={editingPageNum}
            setEditingPageNum={setEditingPageNum}
            tempPageText={tempPageText}
            setTempPageText={setTempPageText}
            chatMessages={chatMessages}
            chatInput={chatInput}
            setChatInput={setChatInput}
            onSendMessage={handleSendMessage}
            isChatting={isChatting}
            chatContainerRef={chatContainerRef}
            setModal={setModal}
          />
        )}

        {view === 'global-chat' && (
          <ChatInterface
            type="global"
            books={books}
            totalReady={totalReady}
            chatMessages={chatMessages}
            chatInput={chatInput}
            setChatInput={setChatInput}
            onSendMessage={handleSendMessage}
            isChatting={isChatting}
            onClose={() => setView('library')}
            chatContainerRef={chatContainerRef}
          />
        )}

        <Modal
          isOpen={modal.isOpen}
          title={modal.title}
          message={modal.message}
          type={modal.type}
          confirmText={modal.confirmText}
          onConfirm={modal.onConfirm}
          destructive={modal.destructive}
          onClose={() => setModal(prev => ({ ...prev, isOpen: false }))}
        />
      </main>
    </div>
  );
};

export default App;
