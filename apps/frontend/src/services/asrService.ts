import { authFetch } from './authService';

export interface TranscribeResponse {
  text_uey: string;
  text_uly: string;
  raw_pred: string;
}

export const transcribeAudioBlob = async (audioBlob: Blob): Promise<TranscribeResponse> => {
  const formData = new FormData();
  formData.append('file', audioBlob, 'voice_recording.webm');

  const response = await authFetch('/api/asr/transcribe', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`ASR transcription failed (${response.status}): ${errorText}`);
  }

  return await response.json();
};
