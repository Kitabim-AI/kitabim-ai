import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';

interface QuestionRotatorProps {
  className?: string;
  intervalMs?: number;
  onQuestionClick?: (question: string) => void;
}

export const QuestionRotator: React.FC<QuestionRotatorProps> = ({
  className = '',
  intervalMs = 3500,
  onQuestionClick,
}) => {
  const { t } = useI18n();
  const [questions, setQuestions] = useState<string[]>([]);
  const [current, setCurrent] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    PersistenceService.getFeaturedQuestions(20).then((featured) => {
      setQuestions(featured);
    });
  }, []);

  useEffect(() => {
    if (questions.length < 2) return;
    const timer = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setCurrent(prev => (prev + 1) % questions.length);
        setVisible(true);
      }, 400);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [questions, intervalMs]);

  const question = questions[current];
  if (!question) return null;

  return (
    <div className={`flex flex-col items-center gap-2 ${className}`}>
      <span className="text-xs sm:text-sm font-normal tracking-widest uppercase text-[#94a3b8] dark:text-slate-500">
        {t('home.recentQuestions')}
      </span>
      <p
        className="uyghur-text text-sm sm:text-base font-normal text-[#94a3b8] dark:text-slate-400 text-center transition-opacity duration-300 cursor-pointer hover:text-[#0369a1] dark:hover:text-[#38bdf8] px-4"
        style={{ opacity: visible ? 1 : 0 }}
        dir="rtl"
        onClick={() => onQuestionClick?.(question)}
      >
        {question}
      </p>
    </div>
  );
};
