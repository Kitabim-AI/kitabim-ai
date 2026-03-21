import React, { createContext, useContext, useState, ReactNode, useRef } from 'react';
import { Book } from '@shared/types';
import { useBooks } from '../hooks/useBooks';
import { useChat } from '../hooks/useChat';
import { useBookActions } from '../hooks/useBookActions';

interface AppContextType {
  view: 'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us' | 'spell-check';
  setView: (view: 'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us' | 'spell-check', updateHistory?: boolean) => void;
  previousView: 'home' | 'library' | 'admin' | 'global-chat' | 'join-us' | 'spell-check';
  setPreviousView: (view: 'home' | 'library' | 'admin' | 'global-chat' | 'join-us' | 'spell-check') => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  homeSearchQuery: string;
  setHomeSearchQuery: (query: string) => void;
  selectedCategory: string;
  setSelectedCategory: (category: string) => void;
  currentPage: number | null;
  setCurrentPage: React.Dispatch<React.SetStateAction<number | null>>;
  selectedBook: Book | null;
  setSelectedBook: React.Dispatch<React.SetStateAction<Book | null>>;
  books: Book[];
  totalBooks: number;
  totalReady: number;
  sortedBooks: Book[];
  sortConfig: { key: string; direction: 'asc' | 'desc' };
  refreshLibrary: () => Promise<void>;
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
  activeTab: string;
  setActiveTab: (tab: string, updateHistory?: boolean) => void;
  globalSearchQuery: string;
  setGlobalSearchQuery: (query: string) => void;
  isGlobalSearchOpen: boolean;
  setIsGlobalSearchOpen: (open: boolean) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const parsePath = (path: string): { view: 'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us' | 'spell-check', tab: string } => {
    const parts = path.toLowerCase().split('/').filter(Boolean);
    const viewPortion = parts[0] || 'home';
    
    let view: 'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us' | 'spell-check' = 'home';
    let tab = 'books';

    if (viewPortion === 'library') view = 'library';
    else if (viewPortion === 'admin') {
      view = 'admin';
      tab = parts[1] || 'books';
    }
    else if (viewPortion === 'chat') view = 'global-chat';
    else if (viewPortion === 'join-us') view = 'join-us';
    else if (viewPortion === 'spell-check') view = 'spell-check';
    else if (viewPortion === 'reader') view = 'reader';

    return { view, tab };
  };

  const initialRoute = parsePath(window.location.pathname);
  const [view, setViewInternal] = useState<'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us' | 'spell-check'>(initialRoute.view);
  const [activeTab, setActiveTabInternal] = useState<string>(initialRoute.tab);
  const [previousView, setPreviousView] = useState<'home' | 'library' | 'admin' | 'global-chat' | 'join-us' | 'spell-check'>('home');

  const getPathFromView = (v: string, t?: string) => {
    if (v === 'home') return '/';
    if (v === 'global-chat') return '/chat';
    if (v === 'admin' && t && t !== 'books') return `/admin/${t}`;
    return `/${v}`;
  };

  const setView = (newView: 'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us' | 'spell-check', updateHistory = true) => {
    if (newView !== view) {
      if (updateHistory && newView !== 'reader') {
        const path = getPathFromView(newView, newView === 'admin' ? activeTab : undefined);
        if (window.location.pathname !== path) {
          window.history.pushState({ view: newView, tab: activeTab }, '', path);
        }
      }

      // Logic: Only clear search if navigating directly BETWEEN main dashboard views.
      // If we are opening/closing a sub-view (reader, chat), do NOT clear search state.
      // Exception: If we are navigating TO library or admin, we might be coming from a search box,
      // so we let the caller handle clearing if needed.
      const mainViews = ['home', 'library', 'admin', 'join-us', 'spell-check'];
      if (mainViews.includes(view) && mainViews.includes(newView) && newView !== 'library' && newView !== 'admin') {
        setSearchQuery('');
        setHomeSearchQuery('');
        setSelectedCategory('');
      }

      if (view !== 'reader' && view !== 'global-chat') {
        setPreviousView(view);
      }
      setViewInternal(newView);
    }
  };

  const setActiveTab = (newTab: string, updateHistory = true) => {
    if (newTab !== activeTab) {
      if (updateHistory && view === 'admin') {
        const path = getPathFromView('admin', newTab);
        if (window.location.pathname !== path) {
          window.history.pushState({ view: 'admin', tab: newTab }, '', path);
        }
      }
      setActiveTabInternal(newTab);
    }
  };

  React.useEffect(() => {
    const handlePopState = (event: PopStateEvent) => {
      const { view: nextView, tab: nextTab } = parsePath(window.location.pathname);
      setView(nextView, false);
      setActiveTab(nextTab, false);
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [view, activeTab]);

  const [searchQuery, setSearchQuery] = useState('');
  const [globalSearchQuery, setGlobalSearchQuery] = useState('');
  const [isGlobalSearchOpen, setIsGlobalSearchOpen] = useState(false);
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
    view,
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
    activeTab,
    setActiveTab,
    globalSearchQuery,
    setGlobalSearchQuery,
    isGlobalSearchOpen,
    setIsGlobalSearchOpen,
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
