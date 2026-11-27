import { AlertCircle, Loader2, Pause, Play, Volume2, X } from 'lucide-react';
import React from 'react';
import { TtsPlayerStatus } from '../../hooks/useAnswerTts';
import { useI18n } from '../../i18n/I18nContext';

interface AnswerAudioPlayerProps {
  status: TtsPlayerStatus;
  currentTime: number;
  duration: number;
  playbackRate: number;
  canSeek: boolean;
  truncated: boolean;
  errorMessage: string | null;
  onTogglePauseResume: () => void;
  onSeek: (seconds: number) => void;
  onCycleSpeed: () => void;
  onStop: () => void;
}

function formatTime(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '0:00';
  const total = Math.floor(sec);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export const AnswerAudioPlayer: React.FC<AnswerAudioPlayerProps> = ({
  status,
  currentTime,
  duration,
  playbackRate,
  canSeek,
  truncated,
  errorMessage,
  onTogglePauseResume,
  onSeek,
  onCycleSpeed,
  onStop,
}) => {
  const { t } = useI18n();

  if (status === 'idle') return null;

  if (status === 'error') {
    return (
      <div
        className="w-full mt-1.5 px-3 py-2 rounded-2xl bg-red-50/90 dark:bg-red-950/40 border border-red-200/80 dark:border-red-900/50 flex items-center justify-between gap-2 text-xs text-red-700 dark:text-red-300 shadow-xs animate-in fade-in"
        role="alert"
      >
        <div className="flex items-center gap-2 min-w-0">
          <AlertCircle size={15} className="shrink-0" />
          <span className="uyghur-text truncate">
            {errorMessage || t('chat.tts.errorGeneric')}
          </span>
        </div>
        <button
          onClick={onStop}
          title={t('chat.tts.close')}
          aria-label={t('chat.tts.close')}
          className="p-1 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors shrink-0"
        >
          <X size={14} />
        </button>
      </div>
    );
  }

  const isLoading = status === 'loading';
  const isPlaying = status === 'playing' || status === 'streaming';
  const progressMax = duration > 0 ? duration : 1;

  return (
    <div
      className="w-full mt-1.5 px-3 py-2 rounded-2xl bg-white/85 dark:bg-slate-800/90 border border-[#0369a1]/20 dark:border-[#38bdf8]/20 shadow-sm flex flex-col gap-1 animate-in fade-in"
      aria-label={t('chat.tts.playerLabel')}
    >
      <div dir="ltr" className="flex items-center gap-2 sm:gap-2.5">
        <button
          type="button"
          onClick={onTogglePauseResume}
          disabled={isLoading}
          title={isPlaying ? t('chat.tts.pause') : t('chat.tts.play')}
          aria-label={isPlaying ? t('chat.tts.pause') : t('chat.tts.play')}
          className="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 flex items-center justify-center shrink-0 hover:opacity-90 active:scale-95 transition-all disabled:opacity-60 shadow-xs"
        >
          {isLoading ? (
            <Loader2 size={14} className="animate-spin" />
          ) : isPlaying ? (
            <Pause size={14} fill="currentColor" />
          ) : (
            <Play size={14} fill="currentColor" className="ml-0.5" />
          )}
        </button>

        <div className="flex-1 min-w-0 flex flex-col justify-center">
          {isLoading ? (
            <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
              <Volume2 size={13} className="text-[#0369a1] dark:text-[#38bdf8] animate-pulse shrink-0" />
              <span className="uyghur-text truncate">{t('chat.tts.generating')}</span>
            </div>
          ) : canSeek ? (
            <input
              type="range"
              min={0}
              max={progressMax}
              step={0.1}
              value={Math.min(currentTime, progressMax)}
              onChange={(e) => onSeek(Number(e.target.value))}
              aria-label={t('chat.tts.seek')}
              className="w-full h-1.5 accent-[#0369a1] dark:accent-[#38bdf8] cursor-pointer rounded-lg"
            />
          ) : (
            <div className="flex items-center gap-2">
              <div className="flex items-end gap-0.5 h-3.5 shrink-0" aria-hidden="true">
                <span className="w-0.5 bg-[#0369a1] dark:bg-[#38bdf8] rounded-full animate-pulse h-2" />
                <span className="w-0.5 bg-[#0369a1] dark:bg-[#38bdf8] rounded-full animate-pulse h-3.5" style={{ animationDelay: '120ms' }} />
                <span className="w-0.5 bg-[#0369a1] dark:bg-[#38bdf8] rounded-full animate-pulse h-2.5" style={{ animationDelay: '240ms' }} />
                <span className="w-0.5 bg-[#0369a1] dark:bg-[#38bdf8] rounded-full animate-pulse h-3" style={{ animationDelay: '360ms' }} />
              </div>
              <span className="text-[11px] text-slate-500 dark:text-slate-400 uyghur-text truncate">
                {t('chat.tts.streaming')}
              </span>
            </div>
          )}
        </div>

        <span className="text-[11px] font-mono text-slate-500 dark:text-slate-400 tabular-nums shrink-0">
          {formatTime(currentTime)}
          {duration > 0 ? ` / ${formatTime(duration)}` : ''}
        </span>

        <button
          type="button"
          onClick={onCycleSpeed}
          title={t('chat.tts.speed')}
          aria-label={t('chat.tts.speed')}
          className="px-1.5 py-0.5 rounded-lg text-[11px] font-semibold font-mono bg-slate-100 dark:bg-slate-700/80 text-slate-600 dark:text-slate-200 hover:bg-[#0369a1]/15 hover:text-[#0369a1] dark:hover:bg-[#38bdf8]/20 dark:hover:text-[#38bdf8] transition-colors shrink-0"
        >
          {playbackRate}×
        </button>

        <button
          type="button"
          onClick={onStop}
          title={t('chat.tts.close')}
          aria-label={t('chat.tts.close')}
          className="p-1 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700/60 transition-colors shrink-0"
        >
          <X size={14} />
        </button>
      </div>

      {truncated && (
        <p className="text-[10px] text-amber-600 dark:text-amber-400 uyghur-text px-1">
          {t('chat.tts.truncatedNotice')}
        </p>
      )}
    </div>
  );
};
