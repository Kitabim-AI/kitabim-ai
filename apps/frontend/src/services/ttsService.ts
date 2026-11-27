import { TtsUsageStatus } from '@shared/types';
import { authFetch } from './authService';

const API_BASE = '/api/tts';

export class TtsApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'TtsApiError';
    this.status = status;
  }
}

export interface AnswerTtsParams {
  messageId?: string;
  evalId?: number;
  signal?: AbortSignal;
}

export interface TtsCostInfo {
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
}

export function parseTtsCostFromHeaders(headers: Headers): TtsCostInfo | null {
  const rawCost = headers.get('X-TTS-Cost-Usd');
  const rawIn = headers.get('X-TTS-Input-Tokens');
  const rawOut = headers.get('X-TTS-Output-Tokens');
  if (rawCost === null && rawIn === null && rawOut === null) {
    return null;
  }
  const costUsd = Number(rawCost) || 0;
  const inputTokens = Number(rawIn) || 0;
  const outputTokens = Number(rawOut) || 0;
  if (costUsd <= 0 && inputTokens <= 0 && outputTokens <= 0) {
    return null;
  }
  return { inputTokens, outputTokens, costUsd };
}

/**
 * Poll GET /api/tts/cache/{contentHash}/cost briefly after PCM streaming ends
 * so the background MP3 finalizer has committed exact TTS token/USD metrics.
 */
export async function fetchTtsCacheCost(
  contentHash: string,
  signal?: AbortSignal,
): Promise<TtsCostInfo | null> {
  if (!contentHash) return null;
  const delays = [300, 500, 800, 1200, 1500, 2000, 2500];
  for (let i = 0; i < delays.length; i++) {
    if (signal?.aborted) return null;
    try {
      const res = await authFetch(`${API_BASE}/cache/${contentHash}/cost`, { signal });
      if (res.ok) {
        const data = await res.json();
        if (data?.ready) {
          return {
            inputTokens: Number(data.inputTokens) || 0,
            outputTokens: Number(data.outputTokens) || 0,
            costUsd: Number(data.costUsd) || 0,
          };
        }
      }
    } catch {
      return null;
    }
    if (i < delays.length - 1) {
      await new Promise((resolve) => setTimeout(resolve, delays[i]));
    }
  }
  return null;
}

/**
 * Request TTS audio for a Global or Reader chat question answer.
 * Returns the raw fetch Response so the caller can branch on Content-Type:
 * - `audio/mpeg`: cached 64 kbps MP3 (X-TTS-Cache: hit)
 * - `audio/pcm`: streaming 24 kHz 16-bit LE mono PCM (X-TTS-Cache: miss)
 */
export async function requestAnswerTts(params: AnswerTtsParams): Promise<Response> {
  const { messageId, evalId, signal } = params;
  const body: Record<string, string | number> = {};
  if (messageId) {
    body.messageId = messageId;
  }
  if (typeof evalId === 'number') {
    body.evalId = evalId;
  }

  const response = await authFetch(`${API_BASE}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    let detail = `TTS request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data?.detail === 'string' && data.detail.trim()) {
        detail = data.detail;
      }
    } catch {
      // ignore non-JSON error bodies
    }
    throw new TtsApiError(response.status, detail);
  }

  return response;
}

/**
 * Admin-only, strictly cache-only MP3 fetch for reviewing answers ($0 cost).
 * Never triggers Gemini TTS synthesis; throws 404 TtsApiError if uncached.
 */
export async function requestAdminCachedTts(
  evalId: number,
  signal?: AbortSignal,
): Promise<Response> {
  const response = await authFetch(`${API_BASE}/admin/eval/${evalId}/audio`, {
    method: 'GET',
    signal,
  });

  if (!response.ok) {
    let detail = `Cached TTS audio unavailable (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data?.detail === 'string' && data.detail.trim()) {
        detail = data.detail;
      }
    } catch {
      // ignore non-JSON error bodies
    }
    throw new TtsApiError(response.status, detail);
  }

  return response;
}

export async function getTtsUsage(): Promise<TtsUsageStatus> {
  try {
    const response = await authFetch(`${API_BASE}/usage`);
    if (!response.ok) {
      return { usage: 0, limit: null, hasReachedLimit: false };
    }
    return await response.json();
  } catch {
    return { usage: 0, limit: null, hasReachedLimit: false };
  }
}

/**
 * Wrap raw 16-bit signed little-endian mono PCM chunks in a 44-byte RIFF/WAV header
 * so completed streamed audio can be replayed & scrubbed instantaneously in-browser.
 */
export function encodePcm16ToWavBlob(
  pcmChunks: Uint8Array[],
  sampleRate = 24000,
  numChannels = 1,
): Blob {
  let dataLength = 0;
  for (const chunk of pcmChunks) {
    dataLength += chunk.byteLength;
  }
  // Ensure even byte count (16-bit samples)
  dataLength = dataLength - (dataLength % 2);

  const header = new ArrayBuffer(44);
  const view = new DataView(header);
  const writeAscii = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  const bitsPerSample = 16;
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  const blockAlign = numChannels * (bitsPerSample / 8);

  writeAscii(0, 'RIFF');
  view.setUint32(4, 36 + dataLength, true);
  writeAscii(8, 'WAVE');
  writeAscii(12, 'fmt ');
  view.setUint32(16, 16, true); // PCM subchunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeAscii(36, 'data');
  view.setUint32(40, dataLength, true);

  const parts: BlobPart[] = [header];
  let remaining = dataLength;
  for (const chunk of pcmChunks) {
    if (remaining <= 0) break;
    if (chunk.byteLength <= remaining) {
      parts.push(chunk as unknown as BlobPart);
      remaining -= chunk.byteLength;
    } else {
      parts.push(chunk.subarray(0, remaining) as unknown as BlobPart);
      remaining = 0;
    }
  }

  return new Blob(parts, { type: 'audio/wav' });
}
