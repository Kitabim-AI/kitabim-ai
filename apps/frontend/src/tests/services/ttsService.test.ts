import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  encodePcm16ToWavBlob,
  fetchTtsCacheCost,
  parseTtsCostFromHeaders,
  requestAnswerTts,
  TtsApiError,
} from '@/src/services/ttsService';

vi.mock('@/src/services/authService', () => ({
  authFetch: vi.fn(),
}));

import { authFetch } from '@/src/services/authService';

describe('ttsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('encodes raw 16-bit mono PCM chunks into a valid 44-byte RIFF/WAV blob', async () => {
    const chunk1 = new Uint8Array([0x00, 0x01, 0x02, 0x03]);
    const chunk2 = new Uint8Array([0x04, 0x05]);
    const blob = encodePcm16ToWavBlob([chunk1, chunk2], 24000, 1);

    expect(blob.type).toBe('audio/wav');
    expect(blob.size).toBe(44 + 6);

    const buf = await new Promise<ArrayBuffer>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as ArrayBuffer);
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(blob);
    });
    const view = new DataView(buf);
    const ascii = (offset: number, len: number) =>
      String.fromCharCode(...new Uint8Array(buf, offset, len));

    expect(ascii(0, 4)).toBe('RIFF');
    expect(view.getUint32(4, true)).toBe(36 + 6);
    expect(ascii(8, 4)).toBe('WAVE');
    expect(ascii(12, 4)).toBe('fmt ');
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(24000); // sample rate
    expect(view.getUint16(34, true)).toBe(16); // bits per sample
    expect(ascii(36, 4)).toBe('data');
    expect(view.getUint32(40, true)).toBe(6);
  });

  it('sends messageId/evalId to /api/tts/answer and returns response on 200', async () => {
    const fakeResponse = new Response(new Uint8Array([1, 2, 3]), {
      status: 200,
      headers: { 'Content-Type': 'audio/mpeg' },
    });
    vi.mocked(authFetch).mockResolvedValue(fakeResponse);

    const res = await requestAnswerTts({ messageId: 'msg-42', evalId: 7 });

    expect(res.status).toBe(200);
    expect(authFetch).toHaveBeenCalledWith(
      '/api/tts/answer',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ messageId: 'msg-42', evalId: 7 }),
      }),
    );
  });

  it('throws TtsApiError with backend detail on 429 / 503', async () => {
    const errResponse = new Response(
      JSON.stringify({ detail: 'Daily TTS limit reached' }),
      { status: 429, headers: { 'Content-Type': 'application/json' } },
    );
    vi.mocked(authFetch).mockResolvedValue(errResponse);

    await expect(requestAnswerTts({ messageId: 'msg-1' })).rejects.toEqual(
      expect.objectContaining({
        name: 'TtsApiError',
        status: 429,
        message: 'Daily TTS limit reached',
      }),
    );

    vi.mocked(authFetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Disabled' }), { status: 503 }),
    );
    await expect(requestAnswerTts({ messageId: 'msg-1' })).rejects.toBeInstanceOf(
      TtsApiError,
    );
  });

  it('parses TTS generation cost from cache-hit headers', () => {
    const headers = new Headers({
      'X-TTS-Cost-Usd': '0.002708',
      'X-TTS-Input-Tokens': '106',
      'X-TTS-Output-Tokens': '295',
    });
    expect(parseTtsCostFromHeaders(headers)).toEqual({
      inputTokens: 106,
      outputTokens: 295,
      costUsd: 0.002708,
    });
    expect(parseTtsCostFromHeaders(new Headers())).toBeNull();
  });

  it('fetches TTS cache cost metadata after streaming completes', async () => {
    vi.mocked(authFetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          ready: true,
          inputTokens: 106,
          outputTokens: 295,
          costUsd: 0.002708,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const info = await fetchTtsCacheCost('a'.repeat(64));
    expect(info).toEqual({
      inputTokens: 106,
      outputTokens: 295,
      costUsd: 0.002708,
    });
  });
});
