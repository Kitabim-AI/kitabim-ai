import React, { useEffect, useState } from 'react';
import { PersistenceService } from '../../services/persistenceService';

interface ProverbDisplayProps {
  fontSize?: number;
  size?: 'xs' | 'sm' | 'base' | 'lg' | 'xl';
  keywords?: string | string[];
  className?: string;
  defaultText?: string;
}

const sizeClasses = {
  xs: 'text-xs sm:text-sm md:text-base',
  sm: 'text-sm sm:text-base md:text-lg',
  base: 'text-base sm:text-lg md:text-xl',
  lg: 'text-lg sm:text-xl md:text-2xl',
  xl: 'text-xl sm:text-2xl md:text-3xl lg:text-4xl',
};

export const ProverbDisplay: React.FC<ProverbDisplayProps> = ({
  fontSize,
  size,
  keywords,
  className = "",
  defaultText
}) => {
  const [proverb, setProverb] = useState<{ text: string; volume: number; pageNumber: number } | null>(null);

  useEffect(() => {
    const fetchProverb = async () => {
      try {
        const data = await PersistenceService.getRandomProverb(keywords);
        setProverb(data);
      } catch (e) {
        console.error('Error fetching proverb:', e);
      }
    };
    fetchProverb();
  }, []);

  if (!proverb && !defaultText) return null;

  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <p
        className={`uyghur-text font-normal text-[#1a1a1a] leading-relaxed italic transition-all duration-700
          ${size ? sizeClasses[size] : (!fontSize ? sizeClasses.sm : '')}
        `}
        style={fontSize ? { fontSize: `${fontSize}px` } : {}}
      >
        {proverb?.text || defaultText}
      </p>
    </div>
  );
};
