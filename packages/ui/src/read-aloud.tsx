import { useEffect, useRef, useState } from 'react';
import { api, mutation, type Identity } from './api';

export type SavedSpeech = { id: string; status: string; cancel_requested: boolean; reason: string | null; model_id: string; voice: string; metadata?: { frames: number; sample_rate: number } | null };

export function ReadAloud({ identity, chatId, messageId, speech, onChange }: { identity: Identity; chatId: string; messageId: string; speech?: SavedSpeech | null; onChange: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [playing, setPlaying] = useState(false);
  const player = useRef<HTMLAudioElement>(null);
  const requestId = useRef<string | null>(null);
  const playWhenReady = useRef(false);
  const mounted = useRef(true);
  const running = speech?.status === 'running';
  const completed = speech?.status === 'completed';
  const url = speech ? `/api/v1/chats/${chatId}/speech/${speech.id}/audio` : '';
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (completed && playWhenReady.current && player.current) {
      playWhenReady.current = false;
      void player.current.play().catch(() => { if (mounted.current) setError('Audio is ready. Press Play to listen.'); });
    }
  }, [completed]);
  async function generate() {
    setBusy(true); setError(''); playWhenReady.current = true;
    requestId.current ??= crypto.randomUUID();
    try {
      const result = await api<{ status: string }>(`/api/v1/chats/${chatId}/messages/${messageId}/speech`, mutation(identity, { request_id: requestId.current }));
      requestId.current = null;
      if (result.status !== 'running' && result.status !== 'completed') playWhenReady.current = false;
      if (mounted.current) await onChange();
    } catch (reason) { if (mounted.current) setError((reason as Error).message); }
    finally { if (mounted.current) setBusy(false); }
  }
  function stopPlayback() { if (player.current) { player.current.pause(); player.current.currentTime = 0; } }
  return <div className="read-aloud" aria-label="Read this reply aloud">
    {!running && !completed && <button className="quiet-button" disabled={busy} onClick={() => void generate()}>{busy ? 'Preparing speech…' : 'Read aloud'}</button>}
    {running && <><p className="small-copy" role="status">{speech.cancel_requested ? 'Stopping speech. Waiting for the current phrase to finish…' : 'Making a spoken version of this reply…'}</p><button className="quiet-button" disabled={busy || speech.cancel_requested} onClick={async () => { playWhenReady.current = false; setBusy(true); setError(''); try { await api(`/api/v1/chats/${chatId}/speech/${speech.id}/cancel`, mutation(identity, {})); if (mounted.current) await onChange(); } catch (reason) { if (mounted.current) setError((reason as Error).message); } finally { if (mounted.current) setBusy(false); } }}>Stop generating speech</button></>}
    {completed && <><audio ref={player} controls preload="none" src={url} aria-label="Spoken reply" onPlay={() => { document.querySelectorAll('audio').forEach(audio => { if (audio !== player.current) audio.pause(); }); setPlaying(true); setError(''); }} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onError={() => setError('This saved audio could not be opened. Check your session and try again.')} /><div className="speech-actions"><button className="quiet-button" disabled={!playing} onClick={stopPlayback}>Stop playback</button><a className="quiet-button" href={url} download={`hearth-${speech.id}.wav`}>Save WAV</a></div></>}
    {speech && <p className="small-copy">Voice · {speech.model_id} · {speech.voice}</p>}
    {speech?.reason && !running && <p className="small-copy">{speech.reason}</p>}
    {error && <p className="error-notice" role="status">{error}</p>}
  </div>;
}
