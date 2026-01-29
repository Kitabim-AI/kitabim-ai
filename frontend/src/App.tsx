import React, { useState, useEffect } from 'react';
import { Navbar } from './components/layout/Navbar';
import { LibraryView } from './components/library/LibraryView';
import { AdminView } from './components/admin/AdminView';
import { ReaderView } from './components/reader/ReaderView';
import { ChatInterface } from './components/chat/ChatInterface';
import { Modal } from './components/common/Modal';

import { useBooks } from './hooks/useBooks';
import { useChat } from './hooks/useChat';
import { useBookActions } from './hooks/useBookActions';
import { Book } from './types';

const App: React.FC = () => {
  const [view, setView] = useState<'library' | 'admin' | 'reader' | 'global-chat'>('library');
  const [searchQuery, setSearchQuery] = useState('');
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

  const [modal, setModal] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    type: 'alert' | 'confirm';
    confirmText?: string;
    onConfirm?: () => void;
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
  } = useBooks(view, searchQuery, pageSize, page);

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
    handleReprocess,
    handleReProcessPage,
    handleUpdatePage,
    openReader,
    saveCorrections,
    handleDeleteBook,
    handleSaveCategories,
    handleSaveAuthor,
    handleSaveTitle,
    handleSaveVolume,
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
            content: prev.content || updated.content,
            results: (prev.results && prev.results.some(r => r.text)) ? prev.results : updated.results
          };
        });
      }
    }
  }, [books, selectedBook]);

  // Sync global edit content with latest page results
  useEffect(() => {
    if (selectedBook && !isEditing) {
      const combinedText = [...selectedBook.results]
        .sort((a, b) => Number(a.pageNumber) - Number(b.pageNumber))
        .map(r => r.text || '')
        .join('\n\n');

      if (combinedText !== editContent) {
        setEditContent(combinedText);
      }
    }
  }, [selectedBook?.results, isEditing, editContent]);

  useEffect(() => {
    refreshLibrary();
  }, [refreshLibrary]);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <Navbar
        view={view}
        setView={setView}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        onFileUpload={handleFileUpload}
        clearChat={clearChat}
      />

      <main className="flex-grow p-6 max-w-7xl mx-auto w-full relative">
        {isLoading && view !== 'reader' && (
          <div className="absolute inset-0 bg-slate-50/50 backdrop-blur-[2px] z-40 flex items-center justify-center min-h-[400px]">
            <div className="flex flex-col items-center gap-3">
              <div className="w-10 h-10 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin"></div>
              <span className="text-sm font-bold text-indigo-600 uppercase tracking-widest animate-pulse">Loading Library</span>
            </div>
          </div>
        )}

        {view === 'library' && (
          <LibraryView
            books={sortedBooks}
            isLoadingMore={isLoadingMoreShelf}
            hasMore={hasMoreShelf}
            searchQuery={searchQuery}
            onBookClick={(book) => openReader(book, setEditContent, setChatMessages, setCurrentPage)}
            loaderRef={loaderRef}
            loadMore={loadMoreShelf}
          />
        )}

        {view === 'admin' && (
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
            onReprocess={handleReprocess}
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
            onReprocess={handleReprocess}
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
          onClose={() => setModal(prev => ({ ...prev, isOpen: false }))}
        />
      </main>
    </div>
  );
};

export default App;
