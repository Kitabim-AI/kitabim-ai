import { useCallback, useEffect, useRef, useState } from 'react';
import {
  encodePcm16ToWavBlob,
  fetchTtsCacheCost,
  parseTtsCostFromHeaders,
  requestAdminCachedTts,
  requestAnswerTts,
  TtsApiError,
  TtsCostInfo,
} from '../services/ttsService';

export type TtsPlayerStatus =
  | 'idle'
  | 'loading'
  | 'streaming'
  | 'playing'
  | 'paused'
  | 'error';

export const TTS_PLAYBACK_RATES = [1, 1.25, 1.5] as const;

export interface AnswerTtsTarget {
  key: string;
  messageId?: string;
  evalId?: number;
  /** When true, fetches exclusively from admin cache-only endpoint ($0 cost). */
  adminCachedOnly?: boolean;
}

export interface UseAnswerTtsResult {
  activeKey: string | null;
  status: TtsPlayerStatus;
  currentTime: number;
  duration: number;
  playbackRate: number;
  canSeek: boolean;
  truncated: boolean;
  errorMessage: string | null;
  ttsCostsByKey: Record<string, TtsCostInfo>;
  playOrToggle: (target: AnswerTtsTarget) => void;
  togglePauseResume: () => void;
  seek: (seconds: number) => void;
  cyclePlaybackRate: () => void;
  stop: () => void;
}

const DEFAULT_SAMPLE_RATE = 24000;
const INITIAL_JITTER_SEC = 0.12;

interface CachedAudioEntry {
  url: string;
  duration?: number;
  truncated: boolean;
}

export function useAnswerTts(resetDep?: string): UseAnswerTtsResult {
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [status, setStatus] = useState<TtsPlayerStatus>('idle');
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState<number>(1);
  const [canSeek, setCanSeek] = useState(false);
  const [truncated, setTruncated] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [ttsCostsByKey, setTtsCostsByKey] = useState<Record<string, TtsCostInfo>>({});

  // Refs for active playback resources
  const abortControllerRef = useRef<AbortController | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const activeSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const streamTimerRef = useRef<number | null>(null);
  const streamStartCtxTimeRef = useRef<number>(0);
  const streamTotalAudioSecRef = useRef<number>(0);
  const playbackRateRef = useRef<number>(1);
  const runIdRef = useRef<number>(0);

  // Session cache of local blob URLs (MP3 from cache hits or WAV wrapped after PCM stream)
  const blobCacheRef = useRef<Map<string, CachedAudioEntry>>(new Map());

  const clearStreamTimer = useCallback(() => {
    if (streamTimerRef.current !== null) {
      window.clearInterval(streamTimerRef.current);
      streamTimerRef.current = null;
    }
  }, []);

  const teardownPlayback = useCallback(() => {
    runIdRef.current += 1;
    clearStreamTimer();

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    if (audioElRef.current) {
      try {
        audioElRef.current.pause();
        audioElRef.current.removeAttribute('src');
        audioElRef.current.load();
      } catch {
        // ignore cleanup errors
      }
      audioElRef.current = null;
    }

    for (const src of activeSourcesRef.current) {
      try {
        src.onended = null;
        src.stop();
        src.disconnect();
      } catch {
        // ignore already-stopped sources
      }
    }
    activeSourcesRef.current.clear();

    if (audioCtxRef.current) {
      const ctx = audioCtxRef.current;
      audioCtxRef.current = null;
      ctx.close().catch(() => {});
    }
  }, [clearStreamTimer]);

  const stop = useCallback(() => {
    teardownPlayback();
    setActiveKey(null);
    setStatus('idle');
    setCurrentTime(0);
    setDuration(0);
    setCanSeek(false);
    setTruncated(false);
    setErrorMessage(null);
  }, [teardownPlayback]);

  // Stop playback when switching conversations/books
  useEffect(() => {
    stop();
  }, [resetDep, stop]);

  // Cleanup all playback and blob URLs on unmount
  useEffect(() => {
    return () => {
      teardownPlayback();
      for (const entry of blobCacheRef.current.values()) {
        URL.revokeObjectURL(entry.url);
      }
      blobCacheRef.current.clear();
    };
  }, [teardownPlayback]);

  const attachBlobAudio = useCallback(
    (entry: CachedAudioEntry, runId: number, autoPlay: boolean) => {
      if (runId !== runIdRef.current) return;

      clearStreamTimer();
      const audio = new Audio(entry.url);
      audio.playbackRate = playbackRateRef.current;
      audioElRef.current = audio;

      setCanSeek(true);
      setTruncated(entry.truncated);
      if (entry.duration && Number.isFinite(entry.duration)) {
        setDuration(entry.duration);
      }
      setCurrentTime(0);

      const syncTime = () => {
        if (runId !== runIdRef.current) return;
        setCurrentTime(audio.currentTime);
        if (Number.isFinite(audio.duration) && audio.duration > 0) {
          setDuration(audio.duration);
        }
      };

      audio.onloadedmetadata = syncTime;
      audio.ontimeupdate = syncTime;

      audio.onplay = () => {
        if (runId !== runIdRef.current) return;
        setStatus('playing');
        clearStreamTimer();
        streamTimerRef.current = window.setInterval(syncTime, 100);
      };

      audio.onpause = () => {
        if (runId !== runIdRef.current) return;
        clearStreamTimer();
        syncTime();
        if (!audio.ended) {
          setStatus('paused');
        }
      };

      audio.onended = () => {
        if (runId !== runIdRef.current) return;
        clearStreamTimer();
        setStatus('paused');
        setCurrentTime(0);
        audio.currentTime = 0;
      };

      audio.onerror = () => {
        if (runId !== runIdRef.current) return;
        clearStreamTimer();
        setStatus('error');
        setErrorMessage('Audio playback failed');
      };

      if (autoPlay) {
        audio.play().catch(() => {
          if (runId !== runIdRef.current) return;
          clearStreamTimer();
          setStatus('paused');
        });
      } else {
        setStatus('paused');
      }
    },
    [clearStreamTimer],
  );

  const streamPcmResponse = useCallback(
    async (
      key: string,
      response: Response,
      audioCtx: AudioContext,
      runId: number,
    ) => {
      const sampleRateHeader = Number(response.headers.get('X-TTS-Sample-Rate'));
      const sampleRate =
        Number.isFinite(sampleRateHeader) && sampleRateHeader > 0
          ? sampleRateHeader
          : DEFAULT_SAMPLE_RATE;
      const wasTruncated = response.headers.get('X-TTS-Truncated') === 'true';
      setTruncated(wasTruncated);
      setCanSeek(false);
      setCurrentTime(0);
      setDuration(0);

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Streaming response body unavailable');
      }

      if (audioCtx.state === 'suspended') {
        await audioCtx.resume().catch(() => {});
      }

      const pcmChunks: Uint8Array[] = [];
      let leftoverByte: Uint8Array | null = null;
      let nextPlayTime = 0;
      let hasStartedPlayback = false;
      let streamFinished = false;
      streamTotalAudioSecRef.current = 0;

      const scheduleChunk = (evenBytes: Uint8Array) => {
        if (runId !== runIdRef.current || evenBytes.byteLength < 2) return;

        const sampleCount = evenBytes.byteLength / 2;
        const floatData = new Float32Array(sampleCount);
        const view = new DataView(
          evenBytes.buffer,
          evenBytes.byteOffset,
          evenBytes.byteLength,
        );
        for (let i = 0; i < sampleCount; i++) {
          floatData[i] = view.getInt16(i * 2, true) / 32768.0;
        }

        const audioBuffer = audioCtx.createBuffer(1, sampleCount, sampleRate);
        audioBuffer.getChannelData(0).set(floatData);

        const source = audioCtx.createBufferSource();
        source.buffer = audioBuffer;
        source.playbackRate.value = playbackRateRef.current;
        source.connect(audioCtx.destination);

        const now = audioCtx.currentTime;
        if (!hasStartedPlayback) {
          hasStartedPlayback = true;
          nextPlayTime = now + INITIAL_JITTER_SEC;
          streamStartCtxTimeRef.current = nextPlayTime;
          setStatus('streaming');

          streamTimerRef.current = window.setInterval(() => {
            if (runId !== runIdRef.current) return;
            const ctx = audioCtxRef.current;
            if (!ctx || ctx.state !== 'running') return;
            const elapsed = Math.max(0, ctx.currentTime - streamStartCtxTimeRef.current);
            setCurrentTime(Math.min(elapsed, streamTotalAudioSecRef.current));
          }, 200);
        } else if (nextPlayTime < now + 0.02) {
          nextPlayTime = now + 0.02;
        }

        const scaledDuration = audioBuffer.duration / playbackRateRef.current;
        source.start(nextPlayTime);
        nextPlayTime += scaledDuration;
        streamTotalAudioSecRef.current += audioBuffer.duration;
        setDuration(streamTotalAudioSecRef.current);

        activeSourcesRef.current.add(source);
        source.onended = () => {
          activeSourcesRef.current.delete(source);
          if (
            runId === runIdRef.current &&
            streamFinished &&
            activeSourcesRef.current.size === 0
          ) {
            clearStreamTimer();
            const cachedEntry = blobCacheRef.current.get(key);
            if (cachedEntry) {
              // Transition to local WAV-backed audio element with full event listeners for seeking/replay
              attachBlobAudio(cachedEntry, runId, false);
            } else {
              setStatus('idle');
            }
          }
        };
      };

      while (true) {
        const { done, value } = await reader.read();
        if (runId !== runIdRef.current) {
          await reader.cancel().catch(() => {});
          return;
        }
        if (done) {
          break;
        }
        if (!value || value.byteLength === 0) continue;

        let combined: Uint8Array;
        if (leftoverByte) {
          combined = new Uint8Array(leftoverByte.byteLength + value.byteLength);
          combined.set(leftoverByte, 0);
          combined.set(value, leftoverByte.byteLength);
          leftoverByte = null;
        } else {
          combined = value;
        }

        if (combined.byteLength % 2 === 1) {
          leftoverByte = combined.slice(combined.byteLength - 1);
          combined = combined.subarray(0, combined.byteLength - 1);
        }

        if (combined.byteLength > 0) {
          // Store copy for WAV wrapping once stream completes
          pcmChunks.push(new Uint8Array(combined));
          scheduleChunk(combined);
        }
      }

      if (runId !== runIdRef.current) return;
      streamFinished = true;

      if (pcmChunks.length === 0) {
        throw new Error('No audio received');
      }

      // Wrap accumulated PCM into local WAV Blob for zero-cost replay & scrubbing
      const wavBlob = encodePcm16ToWavBlob(pcmChunks, sampleRate, 1);
      const prevCached = blobCacheRef.current.get(key);
      if (prevCached) {
        URL.revokeObjectURL(prevCached.url);
      }
      const wavUrl = URL.createObjectURL(wavBlob);
      const totalDur = streamTotalAudioSecRef.current;
      const wavEntry: CachedAudioEntry = {
        url: wavUrl,
        duration: totalDur,
        truncated: wasTruncated,
      };
      blobCacheRef.current.set(key, wavEntry);

      // Fetch exact persisted TTS generation cost once backend background task finishes
      const contentHash = response.headers.get('X-TTS-Content-Hash') || '';
      if (contentHash) {
        fetchTtsCacheCost(contentHash).then((costInfo) => {
          if (costInfo) {
            setTtsCostsByKey((prev) => ({ ...prev, [key]: costInfo }));
          }
        });
      }

      if (activeSourcesRef.current.size === 0) {
        attachBlobAudio(wavEntry, runId, false);
      }
    },
    [attachBlobAudio, clearStreamTimer],
  );

  const playOrToggle = useCallback(
    (target: AnswerTtsTarget) => {
      // Clicking the already active answer toggles pause/resume (unless errored -> retry)
      if (activeKey === target.key && status !== 'idle' && status !== 'error') {
        if (status === 'loading') {
          stop();
          return;
        }
        if (audioElRef.current) {
          if (audioElRef.current.paused) {
            audioElRef.current.play().catch(() => {});
          } else {
            audioElRef.current.pause();
          }
          return;
        }
        if (audioCtxRef.current) {
          if (audioCtxRef.current.state === 'running') {
            audioCtxRef.current.suspend().then(() => setStatus('paused')).catch(() => {});
          } else if (audioCtxRef.current.state === 'suspended') {
            audioCtxRef.current.resume().then(() => setStatus('streaming')).catch(() => {});
          }
          return;
        }
      }

      // Starting a new answer (or retrying): tear down any active playback first
      teardownPlayback();
      const myRunId = runIdRef.current;

      setActiveKey(target.key);
      setErrorMessage(null);
      setCurrentTime(0);
      setDuration(0);
      setCanSeek(false);
      setTruncated(false);

      // Fast path: already cached in browser memory during this session
      const sessionCached = blobCacheRef.current.get(target.key);
      if (sessionCached) {
        setStatus('loading');
        attachBlobAudio(sessionCached, myRunId, true);
        return;
      }

      // Synchronously unlock AudioContext inside user gesture for iOS Safari
      const AudioCtxCtor =
        typeof window !== 'undefined'
          ? window.AudioContext || (window as any).webkitAudioContext
          : undefined;
      let audioCtx: AudioContext | null = null;
      if (AudioCtxCtor) {
        try {
          audioCtx = new AudioCtxCtor();
          audioCtxRef.current = audioCtx;
          audioCtx.resume().catch(() => {});
        } catch {
          audioCtx = null;
        }
      }

      const controller = new AbortController();
      abortControllerRef.current = controller;
      setStatus('loading');

      (async () => {
        try {
          const response =
            target.adminCachedOnly && typeof target.evalId === 'number'
              ? await requestAdminCachedTts(target.evalId, controller.signal)
              : await requestAnswerTts({
                  messageId: target.messageId,
                  evalId: target.evalId,
                  signal: controller.signal,
                });
          if (myRunId !== runIdRef.current) return;

          const contentType = (response.headers.get('Content-Type') || '').toLowerCase();
          const wasTruncated = response.headers.get('X-TTS-Truncated') === 'true';

          if (contentType.includes('audio/pcm') && audioCtx) {
            await streamPcmResponse(target.key, response, audioCtx, myRunId);
            return;
          }

          // Cache hit (audio/mpeg) or fallback when AudioContext unavailable
          const headerCost = parseTtsCostFromHeaders(response.headers);
          if (headerCost) {
            setTtsCostsByKey((prev) => ({ ...prev, [target.key]: headerCost }));
          }

          if (audioCtxRef.current === audioCtx && audioCtx) {
            audioCtxRef.current = null;
            audioCtx.close().catch(() => {});
          }

          const blob = await response.blob();
          if (myRunId !== runIdRef.current) return;

          const durationHeader = Number(response.headers.get('X-TTS-Duration-Sec'));
          const knownDuration =
            Number.isFinite(durationHeader) && durationHeader > 0
              ? durationHeader
              : undefined;

          const url = URL.createObjectURL(blob);
          const entry: CachedAudioEntry = {
            url,
            duration: knownDuration,
            truncated: wasTruncated,
          };
          blobCacheRef.current.set(target.key, entry);
          attachBlobAudio(entry, myRunId, true);
        } catch (err: any) {
          if (myRunId !== runIdRef.current || err?.name === 'AbortError') return;
          teardownPlayback();
          setStatus('error');
          if (err instanceof TtsApiError) {
            setErrorMessage(err.message);
          } else {
            setErrorMessage(err?.message || 'Audio playback failed');
          }
        }
      })();
    },
    [activeKey, status, stop, teardownPlayback, attachBlobAudio, streamPcmResponse],
  );

  const togglePauseResume = useCallback(() => {
    if (!activeKey) return;
    if (audioElRef.current) {
      if (audioElRef.current.paused) {
        audioElRef.current.play().catch(() => {});
      } else {
        audioElRef.current.pause();
      }
      return;
    }
    if (audioCtxRef.current) {
      if (audioCtxRef.current.state === 'running') {
        audioCtxRef.current.suspend().then(() => setStatus('paused')).catch(() => {});
      } else if (audioCtxRef.current.state === 'suspended') {
        audioCtxRef.current.resume().then(() => setStatus('streaming')).catch(() => {});
      }
    }
  }, [activeKey]);

  const seek = useCallback((seconds: number) => {
    const audio = audioElRef.current;
    if (!audio || !Number.isFinite(seconds)) return;
    const clamped = Math.max(0, Math.min(seconds, audio.duration || seconds));
    audio.currentTime = clamped;
    setCurrentTime(clamped);
  }, []);

  const cyclePlaybackRate = useCallback(() => {
    setPlaybackRate(prev => {
      const idx = TTS_PLAYBACK_RATES.indexOf(prev as (typeof TTS_PLAYBACK_RATES)[number]);
      const next = TTS_PLAYBACK_RATES[(idx + 1) % TTS_PLAYBACK_RATES.length];
      playbackRateRef.current = next;
      if (audioElRef.current) {
        audioElRef.current.playbackRate = next;
      }
      for (const src of activeSourcesRef.current) {
        try {
          src.playbackRate.value = next;
        } catch {
          // ignore
        }
      }
      return next;
    });
  }, []);

  return {
    activeKey,
    status,
    currentTime,
    duration,
    playbackRate,
    canSeek,
    truncated,
    errorMessage,
    ttsCostsByKey,
    playOrToggle,
    togglePauseResume,
    seek,
    cyclePlaybackRate,
    stop,
  };
}
