import { transcribeAudioBlob } from '@/src/services/asrService';
import { authFetch } from '@/src/services/authService';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/authService', () => ({
  authFetch: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test('transcribeAudioBlob posts the blob as multipart form data and returns the parsed result', async () => {
  const responseBody = { text_uey: 'سالام', text_uly: 'salam', raw_pred: 'salam' };
  (authFetch as any).mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue(responseBody),
  });

  const blob = new Blob(['audio-bytes'], { type: 'audio/webm' });
  const result = await transcribeAudioBlob(blob);

  expect(result).toEqual(responseBody);
  expect(authFetch).toHaveBeenCalledTimes(1);
  const [url, options] = (authFetch as any).mock.calls[0];
  expect(url).toBe('/api/asr/transcribe');
  expect(options.method).toBe('POST');
  expect(options.body).toBeInstanceOf(FormData);
  expect(options.body.get('file')).toBeInstanceOf(Blob);
});

test('transcribeAudioBlob throws with status and body text when the request fails', async () => {
  (authFetch as any).mockResolvedValue({
    ok: false,
    status: 413,
    text: vi.fn().mockResolvedValue('Audio file too large'),
  });

  const blob = new Blob(['audio-bytes'], { type: 'audio/webm' });

  await expect(transcribeAudioBlob(blob)).rejects.toThrow(/413/);
});
