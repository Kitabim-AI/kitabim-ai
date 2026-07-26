import React, { useState } from 'react';
import { Mic, Square, Loader2 } from 'lucide-react';
import { useAudioRecorder } from '../../hooks/useAudioRecorder';
import { transcribeAudioBlob } from '../../services/asrService';
import { useI18n } from '../../i18n/I18nContext';

interface VoiceInputButtonProps {
  onTranscribed: (text: string) => void;
  onError?: (error: string) => void;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  title?: string;
}

export const VoiceInputButton: React.FC<VoiceInputButtonProps> = ({
  onTranscribed,
  onError,
  className = '',
  size = 'md',
  title,
}) => {
  const { t } = useI18n();
  const resolvedTitle = title ?? t('voice.inputTitle');
  const {
    isRecording,
    error: recorderError,
    startRecording,
    stopRecording,
  } = useAudioRecorder();

  const [isTranscribing, setIsTranscribing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleStart = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setErrorMessage(null);
    await startRecording();
  };

  const handleStop = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setErrorMessage(null);

    try {
      setIsTranscribing(true);
      const blob = await stopRecording();
      if (blob && blob.size > 0) {
        const res = await transcribeAudioBlob(blob);
        const recognizedText = res?.text_uey || res?.text_uly;
        if (recognizedText) {
          onTranscribed(recognizedText);
        } else {
          const userErr = t('voice.notRecognized');
          setErrorMessage(userErr);
          if (onError) onError(userErr);
        }
      }
    } catch (err) {
      console.error('ASR error:', err instanceof Error ? err.message : err);
      const userErr = t('voice.unavailable');
      setErrorMessage(userErr);
      if (onError) onError(userErr);
    } finally {
      setIsTranscribing(false);
    }
  };

  const iconSizes = {
    sm: 18,
    md: 20,
    lg: 22,
  }[size];

  const sizeClasses = {
    sm: 'p-1.5 h-8 w-8',
    md: 'p-2 h-9 w-9 sm:h-10 sm:w-10',
    lg: 'p-2.5 h-11 w-11 sm:h-12 sm:w-12',
  }[size];

  const activeError = errorMessage || recorderError;

  if (isTranscribing) {
    return (
      <div className="relative inline-flex items-center">
        <button
          type="button"
          disabled
          title={t('voice.transcribing')}
          className={`flex items-center justify-center rounded-xl sm:rounded-2xl bg-amber-500/10 text-amber-500 border border-amber-500/30 ${sizeClasses} ${className}`}
        >
          <Loader2 size={iconSizes} strokeWidth={2.5} className="animate-spin" />
        </button>
      </div>
    );
  }

  if (isRecording) {
    return (
      <div className="relative inline-flex items-center">
        <button
          type="button"
          onClick={handleStop}
          title={t('voice.stopAndTranscribe')}
          aria-label={t('voice.stopRecording')}
          className={`flex items-center justify-center rounded-xl sm:rounded-2xl bg-rose-500 text-white shadow-md shadow-rose-500/20 hover:bg-rose-600 animate-pulse transition-all duration-200 focus:outline-none active:scale-95 ${sizeClasses} ${className}`}
        >
          <Square size={iconSizes} strokeWidth={2.5} className="fill-current" />
        </button>
      </div>
    );
  }

  return (
    <div className="relative inline-flex items-center">
      <button
        type="button"
        onClick={handleStart}
        title={activeError || resolvedTitle}
        aria-label={t('voice.startRecording')}
        className={`flex items-center justify-center rounded-xl sm:rounded-2xl transition-all duration-200 focus:outline-none ${
          activeError
            ? 'text-rose-500 dark:text-rose-400 hover:bg-rose-500/10'
            : 'text-stone-500 hover:text-stone-800 dark:text-slate-400 dark:hover:text-slate-100 hover:bg-stone-200/50 dark:hover:bg-slate-800/80'
        } active:scale-95 ${sizeClasses} ${className}`}
      >
        <Mic size={iconSizes} strokeWidth={2.5} />
      </button>

      {activeError && (
        <span className="text-[11px] text-rose-500 dark:text-rose-400 font-normal mr-1.5 max-w-[160px] truncate animate-in fade-in" title={activeError}>
          {activeError}
        </span>
      )}
    </div>
  );
};
