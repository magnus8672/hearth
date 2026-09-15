import { useCallback, useEffect, useRef, useState } from 'react';
import { api, mutation, type Identity } from './api';
import recorderUrl from './audio-recorder-worklet.js?url&no-inline';

type Transcript = { id: string; status: string; cancel_requested: boolean; reason: string | null; transcript: string; model_id: string };

function wavFile(parts: Float32Array[], sampleRate: number) {
  const length = parts.reduce((sum, part) => sum + part.length, 0);
  const bytes = new ArrayBuffer(44 + length * 2), view = new DataView(bytes);
  const tag = (offset: number, value: string) => [...value].forEach((letter, i) => view.setUint8(offset + i, letter.charCodeAt(0)));
  tag(0, 'RIFF'); view.setUint32(4, 36 + length * 2, true); tag(8, 'WAVE'); tag(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true); tag(36, 'data'); view.setUint32(40, length * 2, true);
  let offset = 44;
  parts.forEach(part => part.forEach(value => { view.setInt16(offset, Math.round(Math.max(-1, Math.min(1, value)) * 32767), true); offset += 2; }));
  return new File([bytes], 'hearth-recording.wav', { type: 'audio/wav' });
}

function TranscriptDraft({ item, disabled, onUse, dismiss, onDirty }: { item: Transcript; disabled: boolean; onUse: (value: string) => boolean; dismiss: () => Promise<void>; onDirty: (id: string, dirty: boolean) => void }) {
  const [value, setValue] = useState(item.transcript), [used, setUsed] = useState(false);
  useEffect(() => { onDirty(item.id, value !== item.transcript); return () => onDirty(item.id, false); }, [item.id, item.transcript, value, onDirty]);
  return <div className="transcript-draft"><label>Review transcript<textarea value={value} maxLength={6000} onChange={event => setValue(event.target.value)} /></label><p className="small-copy">{item.model_id} · Check names and details before using this text. It has not been sent.</p><div className="speech-actions"><button type="button" className="quiet-button" disabled={disabled || used || !value.trim()} onClick={() => { if (onUse(value)) { setUsed(true); void dismiss(); } }}>Use in message</button><button type="button" className="quiet-button" disabled={disabled} onClick={() => void dismiss()}>Dismiss transcript</button></div>{used && <p className="small-copy">Added to your message. Review it there before sending.</p>}</div>;
}

export function AudioInput({ identity, chatId, ensureChat, onUse, onDirty }: { identity: Identity; chatId: string; ensureChat: () => Promise<string>; onUse: (value: string) => boolean; onDirty: (dirty: boolean) => void }) {
  const [file, setFile] = useState<File | null>(null), [preview, setPreview] = useState('');
  const [phase, setPhase] = useState(''), [seconds, setSeconds] = useState(0), [level, setLevel] = useState(0);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [items, setItems] = useState<Transcript[]>([]);
  const [edited, setEdited] = useState<Record<string, boolean>>({});
  const draftDirty = useCallback((id: string, dirty: boolean) => setEdited(previous => previous[id] === dirty ? previous : { ...previous, [id]: dirty }), []);
  const input = useRef<HTMLInputElement>(null), recording = useRef<{ context: AudioContext; stream: MediaStream; node: AudioWorkletNode; parts: Float32Array[]; frames: number } | null>(null);
  const version = useRef(0), mounted = useRef(true), pending = useRef<{ file: File; id: string; chat: string } | null>(null), currentChat = useRef(chatId), previousChat = useRef(chatId);
  currentChat.current = chatId;
  const active = items.find(item => item.status === 'running');
  const capturing = phase !== '';
  useEffect(() => { onDirty(!!file || capturing || busy || Object.values(edited).some(Boolean)); return () => onDirty(false); }, [file, capturing, busy, edited, onDirty]);
  useEffect(() => { if (!file) { setPreview(''); return; } const url = URL.createObjectURL(file); setPreview(url); return () => URL.revokeObjectURL(url); }, [file]);
  function release() {
    ++version.current;
    const state = recording.current;
    recording.current = null;
    if (state) { state.node.disconnect(); state.stream.getTracks().forEach(track => track.stop()); void state.context.close(); }
    return state;
  }
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; release(); }; }, []);
  useEffect(() => {
    if (previousChat.current && previousChat.current !== chatId) { release(); setFile(null); setPhase(''); setError(''); pending.current = null; }
    previousChat.current = chatId;
    setItems([]);
    if (!chatId) return;
    let disposed = false;
    const poll = async () => { try { const result = await api<{ items: Transcript[] }>(`/api/v1/chats/${chatId}/transcriptions`); if (!disposed) setItems(result.items); } catch (reason) { if (!disposed) setError((reason as Error).message); } };
    void poll(); const timer = setInterval(() => void poll(), 1200);
    return () => { disposed = true; clearInterval(timer); };
  }, [chatId]);
  async function refresh(id = chatId) { const result = await api<{ items: Transcript[] }>(`/api/v1/chats/${id}/transcriptions`); if (mounted.current && currentChat.current === id) setItems(result.items); }
  function stop(keep: boolean) {
    const state = release(); setPhase(''); setLevel(0);
    if (keep && state) { setFile(wavFile(state.parts, state.context.sampleRate)); pending.current = null; }
  }
  async function record() {
    const token = ++version.current;
    setError(''); setPhase('permission'); setSeconds(0);
    let stream: MediaStream | null = null, context: AudioContext | null = null;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone recording needs a supported browser and HTTPS. You can upload a WAV file instead.');
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      if (token !== version.current || !mounted.current) { stream.getTracks().forEach(track => track.stop()); return; }
      context = new AudioContext({ sampleRate: 16000 });
      await context.audioWorklet.addModule(recorderUrl);
      if (token !== version.current || !mounted.current) { stream.getTracks().forEach(track => track.stop()); await context.close(); return; }
      const node = new AudioWorkletNode(context, 'hearth-recorder');
      const state = { stream, context, node, parts: [] as Float32Array[], frames: 0 };
      recording.current = state;
      node.port.onmessage = (event: MessageEvent<Float32Array>) => {
        if (recording.current !== state) return;
        const samples = event.data.slice(0, Math.max(0, 120 * context!.sampleRate - state.frames));
        const before = state.frames;
        state.parts.push(samples); state.frames += samples.length;
        if (Math.floor(before / 2048) !== Math.floor(state.frames / 2048)) {
          setSeconds(Math.floor(state.frames / context!.sampleRate));
          setLevel(Math.min(1, Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / Math.max(1, samples.length)) * 5));
        }
        if (state.frames >= 120 * context!.sampleRate) stop(true);
      };
      context.createMediaStreamSource(stream).connect(node); node.connect(context.destination);
      await context.resume(); if (mounted.current && token === version.current) setPhase('recording');
    } catch (reason) {
      stream?.getTracks().forEach(track => track.stop()); if (context && context.state !== 'closed') void context.close();
      if (mounted.current && token === version.current) { setPhase(''); setError((reason as Error).name === 'NotAllowedError' ? 'Microphone permission was denied. Allow access in your browser or upload a WAV file.' : (reason as Error).message); }
    }
  }
  async function transcribe() {
    if (!file || busy) return;
    setBusy(true); setError('');
    try {
      const id = chatId || await ensureChat();
      if (!pending.current || pending.current.file !== file || pending.current.chat !== id) pending.current = { id: crypto.randomUUID(), file, chat: id };
      await api(`/api/v1/chats/${id}/transcriptions?request_id=${pending.current.id}`, { method: 'POST', headers: { 'Content-Type': 'audio/wav', 'X-Hearth-CSRF': identity.csrf_token }, body: file });
      pending.current = null; if (mounted.current && currentChat.current === id) { setFile(current => current === file ? null : current); await refresh(id); }
    } catch (reason) { if (mounted.current) setError((reason as Error).message); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function action(id: string, cancel = false) {
    setBusy(true); setError('');
    try { await api(`/api/v1/chats/${chatId}/transcriptions/${id}${cancel ? '/cancel' : ''}`, mutation(identity, cancel ? {} : undefined, cancel ? 'POST' : 'DELETE')); await refresh(); }
    catch (reason) { if (mounted.current) setError((reason as Error).message); }
    finally { if (mounted.current) setBusy(false); }
  }
  return <section className="audio-input" aria-label="Voice input"><div className="speech-actions"><button type="button" className="quiet-button" disabled={busy || !!active || capturing || !!file} onClick={() => void record()}>Record voice</button><button type="button" className="quiet-button" disabled={busy || !!active || capturing} onClick={() => input.current?.click()}>Upload WAV</button><input ref={input} type="file" accept=".wav,audio/wav,audio/x-wav" className="sr-only" aria-label="Upload WAV recording" onChange={event => { const selected = event.target.files?.[0]; if (selected) { if (selected.size > 8 * 1024 * 1024) setError('Choose a WAV recording smaller than 8 MB.'); else { setFile(selected); pending.current = null; setError(''); } } event.target.value = ''; }} /></div><p className="small-copy">English · up to 2 minutes · local transcription · review before sending</p>
    {capturing && <div><p role="status">{phase === 'permission' ? 'Waiting for microphone permission…' : `Recording · ${seconds}s / 120s`}</p><meter aria-label="Microphone level" value={level} min={0} max={1} /><div className="speech-actions"><button type="button" className="quiet-button" disabled={phase !== 'recording'} onClick={() => stop(true)}>Stop recording</button><button type="button" className="quiet-button" onClick={() => stop(false)}>Discard recording</button></div></div>}
    {file && <div><p>{file.name}</p>{preview && <audio controls preload="metadata" src={preview} aria-label="Recording preview" />}<div className="speech-actions"><button type="button" className="primary-button" disabled={busy || !!active} onClick={() => void transcribe()}>{busy ? 'Uploading…' : 'Transcribe recording'}</button><button type="button" className="quiet-button" disabled={busy} onClick={() => { setFile(null); pending.current = null; }}>Discard recording</button></div></div>}
    {items.map(item => <div key={item.id}>{item.status === 'running' ? <><p role="status">{item.cancel_requested ? 'Stopping transcription. Waiting for the current segment to finish…' : 'Transcribing your recording locally…'}</p><button type="button" className="quiet-button" disabled={busy || item.cancel_requested} onClick={() => void action(item.id, true)}>Stop transcription</button></> : item.status === 'completed' ? <TranscriptDraft item={item} onDirty={draftDirty} disabled={busy} onUse={onUse} dismiss={() => action(item.id)} /> : <><p className="small-copy">{item.reason || 'Transcription did not complete.'}</p><button type="button" className="quiet-button" disabled={busy} onClick={() => void action(item.id)}>Dismiss transcript</button></>}</div>)}
    {error && <p className="error-notice" role="alert">{error}</p>}
  </section>;
}
