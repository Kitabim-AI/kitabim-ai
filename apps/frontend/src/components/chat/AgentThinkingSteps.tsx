import { BookOpen, Check, FileSearch, FileText, Filter, Layers, Library, Loader2, Network, RefreshCw, Search, SplitSquareHorizontal, User, Users } from 'lucide-react';
import React from 'react';
import { AgentStep } from '../../hooks/useChat';
import { useI18n } from '../../i18n/I18nContext';

function stepIcon(step: AgentStep): React.ReactNode {
  const s = 11;
  const w = 2;
  if (step.status === 'done') return <Check size={s} strokeWidth={2.5} />;
  if (step.type === 'thinking' || step.type === 'generating') return <Loader2 size={s} strokeWidth={w} className="animate-spin" />;
  if (step.type === 'decomposing') return <SplitSquareHorizontal size={s} strokeWidth={w} />;
  if (step.type === 'grading') return <Filter size={s} strokeWidth={w} />;
  if (step.type === 'tool') {
    switch (step.tool) {
      case 'search_chunks': return <FileSearch size={s} strokeWidth={w} />;
      case 'search_books_by_summary': return <BookOpen size={s} strokeWidth={w} />;
      case 'find_books_by_title': return <BookOpen size={s} strokeWidth={w} />;
      case 'rewrite_query': return <RefreshCw size={s} strokeWidth={w} />;
      case 'get_book_author': return <User size={s} strokeWidth={w} />;
      case 'get_books_by_author': return <Users size={s} strokeWidth={w} />;
      case 'search_catalog': return <Library size={s} strokeWidth={w} />;
      case 'get_book_summary': return <FileText size={s} strokeWidth={w} />;
      case 'get_sister_volumes': return <Layers size={s} strokeWidth={w} />;
      case 'get_current_page': return <FileText size={s} strokeWidth={w} />;
      case 'query_knowledge_graph': return <Network size={s} strokeWidth={w} />;
      default: return <Search size={s} strokeWidth={w} />;
    }
  }
  return <Search size={s} strokeWidth={w} />;
}

function getStepLabel(step: AgentStep, t: (key: string, params?: Record<string, any>) => string): string {
  switch (step.type) {
    case 'decomposing': return t('chat.agent.decomposing', { count: step.count ?? 2 });
    case 'planning': return t('chat.agent.analyzing');
    case 'thinking': return t('chat.agent.thinking');
    case 'grading': return t('chat.agent.grading');
    case 'generating': return t('chat.agent.generatingAnswer');
    case 'tool':
      switch (step.tool) {
        case 'search_chunks': return t('chat.agent.searchingContent');
        case 'search_books_by_summary': return t('chat.agent.searchingBooks');
        case 'find_books_by_title': return t('chat.agent.findingByTitle');
        case 'rewrite_query': return t('chat.agent.rewritingQuery');
        case 'get_book_author': return t('chat.agent.lookingUpAuthor');
        case 'get_books_by_author': return t('chat.agent.findingByAuthor');
        case 'search_catalog': return t('chat.agent.searchingCatalog');
        case 'get_book_summary': return t('chat.agent.readingSummary');
        case 'get_sister_volumes': return t('chat.agent.findingVolumes');
        case 'get_current_page': return t('chat.agent.readingPage');
        case 'query_knowledge_graph': return t('chat.agent.queryingGraph');
        default: return t('chat.agent.searchingContent');
      }
    default: return '';
  }
}

function getStepSublabel(
  step: AgentStep,
  t: (key: string, params?: Record<string, any>) => string,
  allSteps: AgentStep[]
): string | null {
  if (step.type === 'tool' && step.status === 'done' && step.found !== undefined) {
    if (step.tool === 'query_knowledge_graph') {
      return step.found === 0
        ? t('chat.agent.noRelationsFound')
        : t('chat.agent.foundRelations', { count: step.found });
    }

    const isUtilityTool = [
      'rewrite_query',
      'get_current_page',
    ].includes(step.tool ?? '');

    if (isUtilityTool) {
      return null;
    }

    const isBookTool = [
      'find_books_by_title',
      'search_books_by_summary',
      'get_books_by_author',
      'get_sister_volumes',
      'search_catalog',
    ].includes(step.tool ?? '');

    if (isBookTool) {
      return step.found === 0
        ? t('chat.agent.noBooksFound')
        : t('chat.agent.foundBooks', { count: step.found });
    }
    if (step.tool === 'get_book_author') {
      return step.found === 0
        ? t('chat.agent.noRecordFound')
        : t('chat.agent.foundRecord', { count: step.found });
    }
    return step.found === 0
      ? t('chat.agent.noContentFound')
      : t('chat.agent.foundContent', { count: step.found });
  }
  if (step.type === 'grading' && step.kept !== undefined && step.total !== undefined) {
    const currentIndex = allSteps.findIndex(s => s.id === step.id);
    let isBookGrading = false;

    if (currentIndex !== -1) {
      for (let i = currentIndex - 1; i >= 0; i--) {
        if (allSteps[i].type === 'tool') {
          const isBookTool = [
            'find_books_by_title',
            'search_books_by_summary',
            'get_books_by_author',
            'get_sister_volumes',
            'search_catalog',
          ].includes(allSteps[i].tool ?? '');
          if (isBookTool) {
            isBookGrading = true;
          }
          break;
        }
      }
    }

    if (isBookGrading) {
      return t('chat.agent.keptBooks', { kept: step.kept, total: step.total });
    }
    return t('chat.agent.keptContent', { kept: step.kept, total: step.total });
  }
  return null;
}

interface AgentThinkingStepsProps {
  steps: AgentStep[];
  fontSize?: number;
  compact?: boolean;
}

export const AgentThinkingSteps: React.FC<AgentThinkingStepsProps> = ({ steps, fontSize, compact = false }) => {
  const { t } = useI18n();
  const textSize = fontSize ? Math.max(fontSize - 2, 11) : 12;

  return (
    <div
      className={`bg-[#0369a1]/10 border border-[#0369a1]/10 shadow-sm flex flex-col w-full ${
        compact ? 'gap-1 px-3 py-2.5 rounded-2xl rounded-tl-none' : 'gap-1.5 px-5 py-4 rounded-[28px] rounded-tl-none'
      }`}
    >
      {steps.map(step => {
        const isActive = step.status === 'active';
        const label = getStepLabel(step, t);
        const sublabel = getStepSublabel(step, t, steps);

        return (
          <div
            key={step.id}
            dir="rtl"
            className={`flex items-center gap-2 uyghur-text transition-opacity duration-300 ${isActive ? 'opacity-100' : 'opacity-50'}`}
          >
            <span
              className={`shrink-0 w-4 h-4 rounded-full flex items-center justify-center ${
                isActive ? 'bg-[#0369a1] text-white' : 'bg-[#0369a1]/20 text-[#0369a1]'
              }`}
            >
              {stepIcon(step)}
            </span>
            <span className="text-[#0369a1] font-normal" style={{ fontSize: `${textSize}px` }}>
              {label}{isActive ? '...' : ''}
              {sublabel && <span className="opacity-60 mx-1">— {sublabel}</span>}
            </span>
          </div>
        );
      })}
    </div>
  );
};
