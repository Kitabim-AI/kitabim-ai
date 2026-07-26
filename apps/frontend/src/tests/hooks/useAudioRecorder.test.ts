import { useAudioRecorder } from '@/src/hooks/useAudioRecorder';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

let recorderInstances: MockMediaRecorder[] = [];

class MockMediaRecorder {
  static isTypeSupported = vi.fn(() => true);
  state: 'inactive' | 'recording' = 'inactive';
  ondataavailable: ((e: any) => void) | null = null;
  onstop: (() => void) | null = null;
  stream: any;
  mimeType = 'audio/webm';

  constructor(stream: any) {
    this.stream = stream;
    recorderInstances.push(this);
  }

  start = vi.fn(() => {
    this.state = 'recording';
  });

  stop = vi.fn(() => {
    this.state = 'inactive';
    if (this.onstop) this.onstop();
  });
}

function makeStream() {
  const track = { stop: vi.fn() };
  return { getTracks: () => [track] };
}

beforeEach(() => {
  recorderInstances = [];
  (global as any).MediaRecorder = MockMediaRecorder;
  Object.defineProperty(global.navigator, 'mediaDevices', {
    value: { getUserMedia: vi.fn().mockResolvedValue(makeStream()) },
    configurable: true,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

test('startRecording requests mic access and flips isRecording on', async () => {
  const { result } = renderHook(() => useAudioRecorder());

  await act(async () => {
    await result.current.startRecording();
  });

  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ audio: true });
  expect(result.current.isRecording).toBe(true);
});

test('startRecording surfaces an error when the microphone is unavailable', async () => {
  (navigator.mediaDevices.getUserMedia as any).mockRejectedValueOnce(new Error('Permission denied'));
  const { result } = renderHook(() => useAudioRecorder());

  await act(async () => {
    await result.current.startRecording();
  });

  expect(result.current.isRecording).toBe(false);
  expect(result.current.error).toBe('Permission denied');
});

test('stopRecording resolves a blob and releases the mic', async () => {
  const { result } = renderHook(() => useAudioRecorder());

  await act(async () => {
    await result.current.startRecording();
  });

  let blob: Blob | null = null;
  await act(async () => {
    blob = await result.current.stopRecording();
  });

  expect(blob).toBeInstanceOf(Blob);
  expect(result.current.isRecording).toBe(false);
  const recorder = recorderInstances[recorderInstances.length - 1];
  expect(recorder.stream.getTracks()[0].stop).toHaveBeenCalled();
});

test('cancelRecording stops the recorder and resets state without producing a blob', async () => {
  const { result } = renderHook(() => useAudioRecorder());

  await act(async () => {
    await result.current.startRecording();
  });

  act(() => {
    result.current.cancelRecording();
  });

  expect(result.current.isRecording).toBe(false);
  expect(result.current.audioBlob).toBeNull();
  const recorder = recorderInstances[recorderInstances.length - 1];
  expect(recorder.stream.getTracks()[0].stop).toHaveBeenCalled();
});

test('unmounting mid-recording stops the recorder and releases the mic stream', async () => {
  const { result, unmount } = renderHook(() => useAudioRecorder());

  await act(async () => {
    await result.current.startRecording();
  });

  const recorder = recorderInstances[recorderInstances.length - 1];
  const track = recorder.stream.getTracks()[0];

  unmount();

  expect(recorder.stop).toHaveBeenCalled();
  expect(track.stop).toHaveBeenCalled();
});

test('cancels recording and releases mic stream when tab is hidden', async () => {
  const { result } = renderHook(() => useAudioRecorder());

  await act(async () => {
    await result.current.startRecording();
  });

  expect(result.current.isRecording).toBe(true);

  act(() => {
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });

  expect(result.current.isRecording).toBe(false);
  Object.defineProperty(document, 'hidden', { value: false, configurable: true });
});

test('maps NotAllowedError to user friendly permission denied error', async () => {
  const err = new Error('Permission denied');
  err.name = 'NotAllowedError';
  (navigator.mediaDevices.getUserMedia as any).mockRejectedValueOnce(err);

  const { result } = renderHook(() => useAudioRecorder());

  await act(async () => {
    await result.current.startRecording();
  });

  expect(result.current.isRecording).toBe(false);
  expect(result.current.error).toBe('Microphone permission denied. Please allow microphone access.');
});

