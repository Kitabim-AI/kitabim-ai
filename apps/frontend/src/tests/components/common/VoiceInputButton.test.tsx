import { VoiceInputButton } from '@/src/components/common/VoiceInputButton';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { expect, test, vi, beforeEach } from 'vitest';

const mockUseAudioRecorder = vi.fn();

vi.mock('@/src/hooks/useAudioRecorder', () => ({
  useAudioRecorder: () => mockUseAudioRecorder(),
}));

vi.mock('@/src/services/asrService', () => ({
  transcribeAudioBlob: vi.fn(),
}));

import { transcribeAudioBlob } from '@/src/services/asrService';

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAudioRecorder.mockReturnValue({
    isRecording: false,
    error: null,
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
  });
});

test('idle state renders mic button with translated title and aria-label', () => {
  render(<VoiceInputButton onTranscribed={vi.fn()} />);

  const button = screen.getByLabelText('voice.startRecording');
  expect(button).toBeInTheDocument();
  expect(button).toHaveAttribute('title', 'voice.inputTitle');
});

test('clicking the mic button starts recording', () => {
  const startRecording = vi.fn();
  mockUseAudioRecorder.mockReturnValue({
    isRecording: false,
    error: null,
    startRecording,
    stopRecording: vi.fn(),
  });

  render(<VoiceInputButton onTranscribed={vi.fn()} />);
  fireEvent.click(screen.getByLabelText('voice.startRecording'));

  expect(startRecording).toHaveBeenCalled();
});

test('recording state renders stop button with translated title and aria-label', () => {
  mockUseAudioRecorder.mockReturnValue({
    isRecording: true,
    error: null,
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
  });

  render(<VoiceInputButton onTranscribed={vi.fn()} />);

  const button = screen.getByLabelText('voice.stopRecording');
  expect(button).toHaveAttribute('title', 'voice.stopAndTranscribe');
});

test('stopping a recording transcribes the blob and calls onTranscribed', async () => {
  const blob = new Blob(['audio'], { type: 'audio/webm' });
  const stopRecording = vi.fn().mockResolvedValue(blob);
  mockUseAudioRecorder.mockReturnValue({
    isRecording: true,
    error: null,
    startRecording: vi.fn(),
    stopRecording,
  });
  (transcribeAudioBlob as any).mockResolvedValue({ text_uey: 'سالام', text_uly: 'salam', raw_pred: 'salam' });

  const onTranscribed = vi.fn();
  render(<VoiceInputButton onTranscribed={onTranscribed} />);

  fireEvent.click(screen.getByLabelText('voice.stopRecording'));

  await waitFor(() => expect(onTranscribed).toHaveBeenCalledWith('سالام'));
});

test('unrecognized speech surfaces the notRecognized error via onError', async () => {
  const blob = new Blob(['audio'], { type: 'audio/webm' });
  const stopRecording = vi.fn().mockResolvedValue(blob);
  mockUseAudioRecorder.mockReturnValue({
    isRecording: true,
    error: null,
    startRecording: vi.fn(),
    stopRecording,
  });
  (transcribeAudioBlob as any).mockResolvedValue({ text_uey: '', text_uly: '', raw_pred: '' });

  const onError = vi.fn();
  render(<VoiceInputButton onTranscribed={vi.fn()} onError={onError} />);

  fireEvent.click(screen.getByLabelText('voice.stopRecording'));

  await waitFor(() => expect(onError).toHaveBeenCalledWith('voice.notRecognized'));
});

test('a failed transcription surfaces the unavailable error via onError', async () => {
  const blob = new Blob(['audio'], { type: 'audio/webm' });
  const stopRecording = vi.fn().mockResolvedValue(blob);
  mockUseAudioRecorder.mockReturnValue({
    isRecording: true,
    error: null,
    startRecording: vi.fn(),
    stopRecording,
  });
  (transcribeAudioBlob as any).mockRejectedValue(new Error('network error'));

  const onError = vi.fn();
  render(<VoiceInputButton onTranscribed={vi.fn()} onError={onError} />);

  fireEvent.click(screen.getByLabelText('voice.stopRecording'));

  await waitFor(() => expect(onError).toHaveBeenCalledWith('voice.unavailable'));
});
