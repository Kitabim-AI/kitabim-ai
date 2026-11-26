import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AnswerAudioPlayer } from '@/src/components/chat/AnswerAudioPlayer';

vi.mock('@/src/i18n/I18nContext', () => ({
  useI18n: () => ({
    language: 'en',
    t: (key: string) => key,
  }),
}));

describe('AnswerAudioPlayer', () => {
  const baseProps = {
    status: 'playing' as const,
    currentTime: 12,
    duration: 65,
    playbackRate: 1,
    canSeek: true,
    truncated: false,
    errorMessage: null,
    onTogglePauseResume: vi.fn(),
    onSeek: vi.fn(),
    onCycleSpeed: vi.fn(),
    onStop: vi.fn(),
  };

  it('renders nothing when idle', () => {
    const { container } = render(<AnswerAudioPlayer {...baseProps} status="idle" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders time, seek slider, speed pill, and invokes controls', () => {
    const onTogglePauseResume = vi.fn();
    const onSeek = vi.fn();
    const onCycleSpeed = vi.fn();
    const onStop = vi.fn();

    render(
      <AnswerAudioPlayer
        {...baseProps}
        onTogglePauseResume={onTogglePauseResume}
        onSeek={onSeek}
        onCycleSpeed={onCycleSpeed}
        onStop={onStop}
      />,
    );

    expect(screen.getByText('0:12 / 1:05')).toBeTruthy();

    fireEvent.click(screen.getByLabelText('chat.tts.pause'));
    expect(onTogglePauseResume).toHaveBeenCalledOnce();

    fireEvent.change(screen.getByLabelText('chat.tts.seek'), {
      target: { value: '30' },
    });
    expect(onSeek).toHaveBeenCalledWith(30);

    fireEvent.click(screen.getByLabelText('chat.tts.speed'));
    expect(onCycleSpeed).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByLabelText('chat.tts.close'));
    expect(onStop).toHaveBeenCalledOnce();
  });

  it('shows streaming indicator without seek slider while streaming', () => {
    render(
      <AnswerAudioPlayer {...baseProps} status="streaming" canSeek={false} />,
    );
    expect(screen.queryByLabelText('chat.tts.seek')).toBeNull();
    expect(screen.getByText('chat.tts.streaming')).toBeTruthy();
  });

  it('renders error alert and dismiss button on error', () => {
    const onStop = vi.fn();
    render(
      <AnswerAudioPlayer
        {...baseProps}
        status="error"
        errorMessage="Daily limit reached"
        onStop={onStop}
      />,
    );
    expect(screen.getByRole('alert')).toBeTruthy();
    expect(screen.getByText('Daily limit reached')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('chat.tts.close'));
    expect(onStop).toHaveBeenCalledOnce();
  });
});
