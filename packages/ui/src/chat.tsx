import { useEffect, useRef, useState } from 'react';
import { api, mutation, type Identity } from './api';
import { Icon } from './index';
import { AudioInput } from './audio-input';
import { ReadAloud, type SavedSpeech } from './read-aloud';
import { MemoryUsed, type MemoryReceipt } from './memory';
import { ToolActivity, type Invocation } from './tools';
import { Thinking } from './thinking';
import { ReplyHeading } from './reply-heading';
import { ChatPictures, type ChatAttachment } from './chat-pictures';
import { textChoices } from './capability-route';
import { ConversationMedia, type ConversationImage } from './conversation-image';
import { SideNotes, submitsOnEnter, type SideNote } from './side-notes';

type Summary = { id: string; title: string; revision: number };
type Run = { tool_phase?: boolean; tool_invocations?: Invocation[]; reasoning_text?: string; reasoning_truncated?: boolean; stream_phase?: 'waiting' | 'reasoning' | 'answer'; memory_receipt?: MemoryReceipt; assistant_message_id?: string; capability_id?: string; id: string; status: string; cancel_requested: boolean; reason: string | null; finish_reason: string | null; model_id: string | null; protocol?: string };
type Conversation = Summary & { unused_attachments?: ChatAttachment[]; messages: { memory_revision?: number; id: string; role: string; content: string; status: string; attachments?: ChatAttachment[]; speech?: SavedSpeech | null; image?: ConversationImage | null; images?: ConversationImage[]; generation_phase?: string }[]; runs: Run[]; pending?: { id: string; content: string; state: string; reason: string | null }[] };

export function Chat({ identity, onDirty }: { identity: Identity; onDirty: (dirty: boolean) => void }) {
  const [items, setItems] = useState<Summary[]>([]);
  const [selected, setSelected] = useState(() => sessionStorage.getItem(`hearth.chat.${identity.id}`) || '');
  const [chat, setChat] = useState<Conversation | null>(null);
  const [content, setContent] = useState('');
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const [capability, setCapability] = useState('auto');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notesDirty, setNotesDirty] = useState(false);
  const [audioDirty, setAudioDirty] = useState(false);
  const pending = useRef<{ id: string; content: string; chat: string; capability: string; attachments: string } | null>(null);
  const sending = useRef(false);
  const composer = useRef<HTMLTextAreaElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const run = chat?.runs.at(-1);
  const running = run?.status === 'running';
  const makingImage = running && run?.protocol === 'hearth.image.v1';
  const planningImage = running && ['image_planning', 'image_handoff'].includes(chat?.messages.at(-1)?.generation_phase || '');
  const endedEarly = !!run && run.status !== 'completed' && !running;
  const queued = chat?.pending?.[0];
  const dirty = !!content.trim() || !!attachments.length || notesDirty || audioDirty;
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);
  async function refreshList() { setItems((await api<{ items: Summary[] }>('/api/v1/chats')).items); }
  useEffect(() => { void refreshList().catch(reason => setError(reason.message)); }, []);
  useEffect(() => {
    sessionStorage.setItem(`hearth.chat.${identity.id}`, selected);
    setChat(null); setAttachments([]);
    if (!selected) return;
    let disposed = false, firstRead = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const result = await api<Conversation>(`/api/v1/chats/${selected}`, { signal: controller.signal });
        if (disposed) return;
        setChat(result);
        if (firstRead) { setAttachments(previous => previous.length ? previous : result.unused_attachments || []); firstRead = false; }
        // Poll persisted stream text with a fresh audience/session check each time.
        timer = setTimeout(() => void poll(), result.runs.at(-1)?.status === 'running' || result.pending?.length || result.messages.some(message => message.speech?.status === 'running') ? 700 : 3000);
      } catch (reason) { if (!disposed) setError((reason as Error).message); }
    }
    void poll();
    return () => { disposed = true; controller.abort(); clearTimeout(timer); };
  }, [selected, identity.id]);
  useEffect(() => {
    const element = transcript.current;
    if (element && element.scrollHeight - element.scrollTop - element.clientHeight < 180) element.scrollTop = element.scrollHeight;
  }, [chat]);
  function open(id: string) {
    if ((content.trim() || attachments.length || audioDirty) && !window.confirm('Leave this unsent message? Attached images stay saved with this conversation.')) return;
    setContent(''); setError(''); pending.current = null; setSelected(id);
  }
  async function send(text = content, note?: SideNote, replyCapability = capability): Promise<boolean> {
    const pictures = note ? [] : attachments;
    if (!text.trim() && pictures.length) text = 'Describe these images.';
    if (!text.trim() || sending.current || queued) return false;
    sending.current = true;
    setBusy(true); setError('');
    try {
      let current = chat;
      if (!selected) {
        current = await api<Conversation>('/api/v1/chats', mutation(identity, {}));
        setSelected(current.id); setChat(current);
      }
      if (!current) throw new Error('Wait for the saved conversation to open.');
      if (pending.current?.content !== text || pending.current?.chat !== current.id || pending.current?.capability !== replyCapability || pending.current?.attachments !== pictures.map(item => item.id).join(',')) pending.current = { id: crypto.randomUUID(), content: text, chat: current.id, capability: replyCapability, attachments: pictures.map(item => item.id).join(',') };
      const active = current.runs.at(-1);
      await api(`/api/v1/chats/${current.id}/turns`, mutation(identity, { request_id: pending.current.id, revision: current.revision, content: text, capability: replyCapability, attachment_ids: pictures.map(item => item.id), ...(active?.status === 'running' ? { interrupt_run_id: active.id } : {}), ...(note ? { note_id: note.id, note_revision: note.revision } : {}) }));
      if (!note) { setContent(''); setAttachments([]); } pending.current = null;
      setChat(await api<Conversation>(`/api/v1/chats/${current.id}`));
      await refreshList();
      return true;
    } catch (reason) { setError((reason as Error).message); return false; } finally { sending.current = false; setBusy(false); composer.current?.focus(); }
  }
  async function upload(files: File[]) {
    if (busy || sending.current || queued || !files.length) return;
    if (attachments.length + files.length > 4) { setError('Attach up to four images.'); return; }
    if (files.some(file => file.size > 8 * 1024 * 1024)) { setError('Choose images smaller than 8 MB each.'); return; }
    setBusy(true); setError('');
    try {
      let current = chat;
      if (!selected) { current = await api<Conversation>('/api/v1/chats', mutation(identity, {})); setSelected(current.id); setChat(current); await refreshList(); }
      if (!current) throw new Error('Wait for this conversation to open.');
      for (const file of files) {
        const result = await api<ChatAttachment>(`/api/v1/chats/${current.id}/attachments`, { method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream', 'X-Hearth-CSRF': identity.csrf_token }, body: file });
        setAttachments(previous => [...previous.filter(item => item.id !== result.id), result]);
      }
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); if (fileInput.current) fileInput.current.value = ''; }
  }
  return <><div className="info-banner"><Icon name="lock" /><p>Only your account can open these conversations. Messages are sent to the local model server selected by your farm administrator.</p></div><div className="draft-layout chat-layout"><section className="draft-list panel" aria-label="Saved conversations"><div className="section-heading"><h2>Your conversations</h2><button className="quiet-button" disabled={busy} onClick={() => open('')}>+ New</button></div><p className="small-copy">Saved here as replies arrive.</p>{items.map(item => <button className={`draft-item ${item.id === selected ? 'selected' : ''}`} key={item.id} disabled={busy} onClick={() => open(item.id)}><Icon name="writing" /><span>{item.title}</span></button>)}{items.length === 0 && <p className="small-copy">Your first conversation will appear here.</p>}</section>
    <section className="panel chat-panel" aria-label="Private chat"><div className="section-heading"><span className="privacy-label"><Icon name="hearth" />{run?.model_id || 'Your local assistant'}{run?.capability_id && ` · ${textChoices.find(item => item[0] === run.capability_id)?.[1] || 'Images'}`}</span>{selected && <button className="quiet-button" disabled={busy || running || !chat} onClick={async () => { if (!window.confirm('Archive this conversation?')) return; try { await api(`/api/v1/chats/${selected}`, mutation(identity, undefined, 'DELETE')); open(''); await refreshList(); } catch (reason) { setError((reason as Error).message); } }}>Archive</button>}</div>
      <label className="specialist-choice">Reply with<select value={capability} disabled={busy || !!queued} onChange={event => setCapability(event.target.value)}>{textChoices.filter(([id]) => id === 'auto' || identity.permissions.includes('capability.'+id)).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select><span className="small-copy">Automatic routes direct requests to a specialist or images. Choose a text specialist to keep this turn in text. Attached images route to Vision and stay in this private conversation.</span></label>
      <div className="chat-transcript" ref={transcript} aria-label="Conversation messages">{!chat?.messages.length && <div className="chat-empty"><Icon name="hearth" /><h2>What’s on your mind?</h2><p>Ask a question, attach a picture, or ask for an image.</p><p className="small-copy">Try “Make an image of a little fox beside a fireplace.”</p></div>}{chat?.messages.map(message => { const reply = chat.runs.find(item => item.assistant_message_id === message.id); return <article className={`chat-message ${message.role}`} key={message.id}>{message.role === 'user' ? <strong>You</strong> : <ReplyHeading model={reply?.model_id} image={message.image} images={message.images} /> }<ChatPictures chatId={selected} attachments={message.attachments} />{reply && <Thinking text={reply.reasoning_text} streaming={reply.status === 'running' && reply.stream_phase === 'reasoning' && !reply.cancel_requested} stopped={!!reply.cancel_requested || ['cancelled', 'interrupted', 'failed'].includes(reply.status)} truncated={reply.reasoning_truncated} />}<ConversationMedia canMakeModel={identity.permissions.includes('capability.geometry.generate')} unsaved={dirty} image={message.image} images={message.images} content={message.content || (message.status === 'running' && !reply?.reasoning_text ? 'Waiting for the model…' : '')} />{message.role === 'assistant' && message.status === 'completed' && !!message.content.trim() && identity.permissions.includes('capability.audio.speak') && <ReadAloud identity={identity} chatId={selected} messageId={message.id} speech={message.speech} onChange={async () => { const refreshed = await api<Conversation>(`/api/v1/chats/${selected}`); setChat(current => current?.id === refreshed.id ? refreshed : current); }} />}{(message.memory_revision ?? 1) > 1 && <p className="small-copy">Edited by you · revision {message.memory_revision} · <a href={`#memory/message/${message.id}`}>View history</a></p>}{reply?.tool_phase && <p role="status" className="small-copy">Working with tools. Requests needing your approval appear below.</p>}{!!reply?.tool_invocations?.length && <ToolActivity items={reply.tool_invocations} identity={identity} />}{reply && <MemoryUsed receipt={reply.memory_receipt} unsaved={!!content.trim() || !!attachments.length} />}{reply?.finish_reason === 'length' && <div className="reply-limit"><p className="small-copy">This reply reached the model output limit and may be incomplete.</p>{reply.id === run?.id && !running && <button className="quiet-button" disabled={busy || !!queued || !!content.trim() || !!attachments.length} onClick={() => void send('Continue your previous reply from where it stopped. Finish the answer without repeating the beginning.', undefined, reply.capability_id || 'chat.general')}>Continue reply</button>}</div>}</article>; })}</div>
      <div className="chat-status" role="status">{running ? (run?.cancel_requested ? (makingImage ? 'Stopping your image. Waiting for the provider to finish cancelling…' : 'Response stopped. Waiting for the model to finish processing…') : (planningImage ? 'Planning your image locally. You can stop it or give a new direction below.' : makingImage ? 'Making an image. You can stop it or give a new direction below.' : 'Receiving a reply. Type a correction below or keep a note for later.')) : run?.reason || ''}</div>
      {endedEarly && !queued && <p className="small-copy">The partial reply stays saved. Your next turn receives your messages and completed replies.</p>}
      {queued && <div className="queued-message"><strong>{queued.state === 'blocked' ? 'Steering needs attention' : 'Your next direction'}</strong><p>{queued.content}</p><span className="small-copy">{queued.reason || 'Saved. This starts as soon as the previous model request finishes.'}</span><button className="quiet-button" disabled={busy} onClick={async () => { setBusy(true); try { await api(`/api/v1/chats/${selected}/pending/${queued.id}/cancel`, mutation(identity)); setContent(previous => previous || queued.content); const restored = await api<Conversation>(`/api/v1/chats/${selected}`); setChat(restored); setAttachments(restored.unused_attachments || []); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }}>Return to composer</button></div>}
      <form className="chat-composer" onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }} onDrop={event => { if (event.dataTransfer.files.length) { event.preventDefault(); void upload(Array.from(event.dataTransfer.files)); } }} onSubmit={event => { event.preventDefault(); void send(); }}><ChatPictures chatId={selected} attachments={attachments} disabled={busy} onRemove={id => { void api(`/api/v1/chats/${selected}/attachments/${id}`, mutation(identity, undefined, 'DELETE')).then(() => setAttachments(previous => previous.filter(item => item.id !== id))).catch(reason => setError(reason.message)); }} /><input ref={fileInput} className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" multiple aria-label="Attach images" disabled={busy || !!queued || attachments.length >= 4} onChange={event => void upload(Array.from(event.target.files || []))} /><label className="sr-only" htmlFor="chat-message">Your message</label><textarea ref={composer} id="chat-message" onPaste={event => { const files = Array.from(event.clipboardData.files); if (files.length) { event.preventDefault(); void upload(files); } }} placeholder={running ? 'Give a new direction…' : 'Ask your hearth…'} value={content} maxLength={4000} disabled={busy || (!!selected && !chat)} onChange={event => setContent(event.target.value)} onKeyDown={event => { if (submitsOnEnter(event)) { event.preventDefault(); void send(); } }} /><p className="small-copy">Enter to {running ? 'steer' : 'send'} · Shift+Enter for a new line</p><div className="editor-actions"><span className="small-copy">Local only · {content.length.toLocaleString()} / 4,000</span>{identity.permissions.includes('capability.vision.describe') && <button type="button" className="quiet-button" disabled={busy || !!queued || attachments.length >= 4} onClick={() => fileInput.current?.click()}>Attach image</button>}{running && <button type="button" className="quiet-button" disabled={busy || run?.cancel_requested} onClick={() => void api(`/api/v1/chats/${selected}/stop`, mutation(identity)).then(async () => setChat(await api<Conversation>(`/api/v1/chats/${selected}`))).catch(reason => setError(reason.message))}>Stop response</button>}<button className="primary-button" disabled={busy || !!queued || (!content.trim() && !attachments.length) || (!!selected && !chat)}>{busy ? 'Sending…' : running ? 'Steer response' : 'Send message'}</button></div></form>
      {identity.permissions.includes('capability.audio.transcribe') && <AudioInput identity={identity} chatId={selected} onDirty={setAudioDirty} ensureChat={async () => { if (selected) return selected; const current = await api<Conversation>('/api/v1/chats', mutation(identity, {})); setSelected(current.id); setChat(current); await refreshList(); return current.id; }} onUse={value => { const combined = content.trim() ? `${content}\n\n${value}` : value; if (combined.length > 4000) { setError('This message would exceed 4,000 characters. Shorten the transcript or your existing text first.'); return false; } setContent(combined); composer.current?.focus(); return true; }} />}
      {error && <p className="error-notice" role="alert">{error}</p>}
    </section><SideNotes identity={identity} running={running} disabled={busy || !!queued || (!!selected && !chat)} onSend={send} onDirty={setNotesDirty} onUse={value => { const combined = content.trim() ? `${content}\n\n${value}` : value; if (combined.length > 4000) setError('This message would exceed 4,000 characters. Send or shorten the current text first.'); else { setContent(combined); composer.current?.focus(); } }} /></div></>;
}
