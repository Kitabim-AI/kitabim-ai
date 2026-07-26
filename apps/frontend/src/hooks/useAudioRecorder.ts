import { useCallback, useEffect, useRef, useState } from 'react';

export interface UseAudioRecorderOptions {
  maxDurationSeconds?: number;
  onAutoStop?: (blob: Blob | null) => void;
}

export interface UseAudioRecorderReturn {
  isRecording: boolean;
  recordingTime: number;
  audioBlob: Blob | null;
  error: string | null;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<Blob | null>;
  cancelRecording: () => void;
}

export function useAudioRecorder(options: UseAudioRecorderOptions = {}): UseAudioRecorderReturn {
  const { maxDurationSeconds = 60, onAutoStop } = options;
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stopTracks = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch {
          // ignore
        }
      });
      streamRef.current = null;
    }
  }, []);

  const cancelRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.onstop = null;
      try {
        recorder.stop();
      } catch {
        // ignore
      }
    }
    stopTracks();
    mediaRecorderRef.current = null;
    setIsRecording(false);
    setRecordingTime(0);
    setAudioBlob(null);
    audioChunksRef.current = [];
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, [stopTracks]);

  const stopRecording = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === 'inactive') {
        stopTracks();
        setIsRecording(false);
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
        resolve(null);
        return;
      }

      recorder.onstop = () => {
        const mimeType = recorder.mimeType || 'audio/webm';
        const blob = new Blob(audioChunksRef.current, { type: mimeType });
        setAudioBlob(blob);
        setIsRecording(false);

        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }

        stopTracks();
        mediaRecorderRef.current = null;
        resolve(blob);
      };

      try {
        recorder.stop();
      } catch {
        stopTracks();
        setIsRecording(false);
        stopTracks();
        resolve(null);
      }
    });
  }, [stopTracks]);

  const startRecording = useCallback(async () => {
    setError(null);
    setAudioBlob(null);
    audioChunksRef.current = [];

    try {
      if (
        typeof window !== 'undefined' &&
        window.isSecureContext === false &&
        window.location.hostname &&
        !['localhost', '127.0.0.1', '', '::1'].includes(window.location.hostname)
      ) {
        throw new Error('Microphone access requires a secure connection (HTTPS).');
      }

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Microphone access is not supported in this browser.');
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Determine best supported MIME type
      let mimeType = '';
      const types = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/mp4',
        'audio/wav',
      ];
      for (const type of types) {
        if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type)) {
          mimeType = type;
          break;
        }
      }

      const options = mimeType ? { mimeType } : undefined;
      const recorder = new MediaRecorder(stream, options);

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorderRef.current = recorder;
      recorder.start(200);

      setIsRecording(true);
      setRecordingTime(0);

      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => {
          const next = prev + 1;
          if (maxDurationSeconds > 0 && next >= maxDurationSeconds) {
            stopRecording().then((blob) => {
              if (onAutoStop) onAutoStop(blob);
            });
          }
          return next;
        });
      }, 1000);
    } catch (err: any) {
      stopTracks();
      let msg = 'Could not access microphone.';
      if (err?.name === 'NotAllowedError' || err?.name === 'PermissionDeniedError') {
        msg = 'Microphone permission denied. Please allow microphone access.';
      } else if (err?.message) {
        msg = err.message;
      }
      setError(msg);
      setIsRecording(false);
    }
  }, [maxDurationSeconds, onAutoStop, stopRecording, stopTracks]);

  const isRecordingRef = useRef(isRecording);
  isRecordingRef.current = isRecording;

  // Release microphone if tab is hidden or component unmounts mid-recording
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden && isRecordingRef.current) {
        cancelRecording();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [cancelRecording]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (isRecordingRef.current) {
        cancelRecording();
      }
    };
  }, [cancelRecording]);

  return {
    isRecording,
    recordingTime,
    audioBlob,
    error,
    startRecording,
    stopRecording,
    cancelRecording,
  };
}

