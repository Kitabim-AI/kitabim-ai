import React, { createContext, useContext, useState, ReactNode, useRef } from 'react';
import { Book } from '@shared/types';
import { useBooks } from '../hooks/useBooks';
import { useChat } from '../hooks/useChat';
import { useBookActions } from '../hooks/useBookActions';

interface AppContextType {
  view: 'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us';
  setView: (view: 'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us') => void;
  previousView: 'home' | 'library' | 'admin' | 'global-chat' | 'join-us';
  setPreviousView: (view: 'home' | 'library' | 'admin' | 'global-chat' | 'join-us') => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  homeSearchQuery: string;
  setHomeSearchQuery: (query: string) => void;
  selectedBook: Book | null;
  setSelectedBook: React.Dispatch<React.SetStateAction<Book | null>>;
  books: Book[];
  totalBooks: number;
  totalReady: number;
  sortedBooks: Book[];
  sortConfig: { key: string; direction: 'asc' | 'desc' };
  refreshLibrary: () => void;
  isLoading: boolean;
  page: number;
  setPage: (page: number) => void;
  pageSize: number;
  setPageSize: (size: number) => void;
  modal: any;
  setModal: (modal: any) => void;
  bookActions: any;
  chat: any;
  loadMoreShelf: () => void;
  hasMoreShelf: boolean;
  isLoadingMoreShelf: boolean;
  loaderRef: React.RefObject<HTMLDivElement | null>;
  isReaderFullscreen: boolean;
  setIsReaderFullscreen: (v: boolean) => void;
  fontSize: number;
  setFontSize: React.Dispatch<React.SetStateAction<number>>;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [view, setViewInternal] = useState<'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us'>('home');
  const [previousView, setPreviousView] = useState<'home' | 'library' | 'admin' | 'global-chat' | 'join-us'>('home');

  const setView = (newView: 'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us') => {
    if (newView !== view) {
      // Only set previousView if the current view is not 'reader'
      // This ensures we always return to a main navigation view
      if (view !== 'reader') {
        setPreviousView(view);
      }
      setViewInternal(newView);
    }
  };
  const [searchQuery, setSearchQuery] = useState('');
  const [homeSearchQuery, setHomeSearchQuery] = useState('');
  const [selectedBook, setSelectedBook] = useState<Book | null>(null);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [currentPage, setCurrentPage] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [isReaderFullscreen, setIsReaderFullscreen] = useState(false);
  const [fontSize, setFontSize] = useState(18);
  const loaderRef = useRef<HTMLDivElement>(null);

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
    refreshLibrary,
    loadMoreShelf,
    isLoading,
    isLoadingMoreShelf,
    hasMoreShelf,
  } = useBooks(view, view === 'home' ? homeSearchQuery : searchQuery, pageSize, page, view === 'home' ? selectedCategory : undefined);

  const chat = useChat(view, selectedBook, currentPage);

  const bookActions = useBookActions(
    refreshLibrary,
    setBooks,
    setSelectedBook,
    setView,
    setModal,
    chat.setChatMessages,
    setCurrentPage
  );

  const value = {
    view,
    setView,
    previousView,
    setPreviousView,
    searchQuery,
    setSearchQuery,
    homeSearchQuery,
    setHomeSearchQuery,
    selectedCategory,
    setSelectedCategory,
    currentPage,
    setCurrentPage,
    selectedBook,
    setSelectedBook,
    books,
    totalBooks,
    totalReady,
    sortedBooks,
    sortConfig,
    refreshLibrary,
    isLoading,
    page,
    setPage,
    pageSize,
    setPageSize,
    modal,
    setModal,
    bookActions,
    chat,
    loadMoreShelf,
    hasMoreShelf,
    isLoadingMoreShelf,
    loaderRef,
    isReaderFullscreen,
    setIsReaderFullscreen,
    fontSize,
    setFontSize,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

export const useAppContext = () => {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error('useAppContext must be used within an AppProvider');
  }
  return context;
};
