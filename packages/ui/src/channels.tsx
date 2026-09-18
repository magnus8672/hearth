import { useEffect, useRef, useState } from 'react';
import { Workspace } from './workspace';
import { useTranscript } from './use-transcript';
import { api, mutation, type Identity } from './api';
import { Icon } from './index';
import { ReplyHeading } from './reply-heading';
import { ConversationMedia, type ConversationImage } from './conversation-image';
import { ChannelPictures } from './channel-pictures';
import type { ChatAttachment } from './chat-pictures';
import { submitsOnEnter } from './side-notes';

type Channel = { id: string; name: string; joined: boolean };
type Room = { unused_attachments?: ChatAttachment[]; id: string; name: string; revision: number; messages: { attachments?: ChatAttachment[]; id: string; role: string; display_name: string; model_id?: string | null; content: string; status: string; reason: string | null; image?: ConversationImage | null; images?: ConversationImage[]; can_stop?: boolean; request_id?: string }[] };

export function Channels({ identity, onDirty }: { identity: Identity; onDirty: (dirty: boolean) => void }) {
  const [items, setItems] = useState<Channel[]>([]);
  const [selected, setSelected] = useState('');
  const [room, setRoom] = useState<Room | null>(null);
  const [name, setName] = useState('');
  const [content, setContent] = useState('');
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const restoreFocus = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const sending = useRef(false);
  const pending = useRef<{ request_id: string; content: string; channel: string; attachments: string } | null>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const { transcript, atBottom, followLatest } = useTranscript(selected, room);
  const dirty = !!content.trim() || !!name.trim() || !!attachments.length;
  useEffect(() => { if (!busy && restoreFocus.current) { restoreFocus.current = false; composer.current?.focus(); } }, [busy]);
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  useEffect(() => {
    const listener = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', listener);
    return () => window.removeEventListener('beforeunload', listener);
  }, [dirty]);
  async function list() { setItems((await api<{ items: Channel[] }>('/api/v1/channels')).items); }
  useEffect(() => { void list().catch(reason => setError(reason.message)); }, []);
  useEffect(() => {
    setRoom(null);
    if (!selected) return;
    let disposed = false; let firstRead = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const value = await api<Room>(`/api/v1/channels/${selected}`, { signal: controller.signal });
        if (!disposed) { setRoom(value); if (firstRead) { setAttachments(value.unused_attachments || []); firstRead = false; } timer = setTimeout(() => void poll(), 1000); }
      } catch (reason) { if (!disposed) setError((reason as Error).message); }
    }
    void poll();
    return () => { disposed = true; controller.abort(); clearTimeout(timer); };
  }, [selected]);

  async function enter(channel: Channel) {
    if (channel.id === selected || busy) return;
    if ((content.trim() || attachments.length) && !window.confirm('Leave this unsent channel message?')) return;
    setBusy(true); setError('');
    try {
      if (!channel.joined) await api(`/api/v1/channels/${channel.id}/join`, mutation(identity));
      setContent(''); setAttachments([]); pending.current = null; setSelected(channel.id); await list();
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  async function send() {
    if (!selected || !room || (!content.trim() && !attachments.length) || busy || sending.current) return;
    sending.current = true; setBusy(true); setError('');
    try {
      if (pending.current?.content !== content || pending.current.channel !== selected || pending.current.attachments !== attachments.map(item => item.id).join(',')) pending.current = { request_id: crypto.randomUUID(), content, channel: selected, attachments: attachments.map(item => item.id).join(',') };
      await api(`/api/v1/channels/${selected}/messages`, mutation(identity, { request_id: pending.current.request_id, content, attachment_ids: attachments.map(item => item.id) }));
      setContent(''); setAttachments([]); pending.current = null;
      followLatest(); setRoom(await api<Room>(`/api/v1/channels/${selected}`));
    } catch (reason) { setError((reason as Error).message); } finally { sending.current = false; restoreFocus.current = true; setBusy(false); }
  }
  async function upload(files: File[]) {
    if (!selected || !room || busy || sending.current || !files.length) return;
    if (attachments.length + files.length > 4) { setError('Attach up to four images.'); return; }
    if (files.some(file => file.size > 8 * 1024 * 1024)) { setError('Choose images smaller than 8 MB each.'); return; }
    sending.current = true; setBusy(true); setError('');
    try {
      for (const file of files) {
        const result = await api<ChatAttachment>(`/api/v1/channels/${selected}/attachments`, { method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream', 'X-Hearth-CSRF': identity.csrf_token }, body: file });
        setAttachments(previous => [...previous.filter(item => item.id !== result.id), result]);
      }
    } catch (reason) { setError((reason as Error).message); }
    finally { sending.current = false; restoreFocus.current = true; setBusy(false); if (fileInput.current) fileInput.current.value = ''; }
  }
  async function removeAttachment(id: string) {
    if (busy || sending.current) return;
    setBusy(true); setError('');
    try { await api(`/api/v1/channels/${selected}/attachments/${id}`, mutation(identity, undefined, 'DELETE')); setAttachments(previous => previous.filter(item => item.id !== id)); }
    catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  return <><div className="info-banner"><Icon name="users" /><p>Channels are shared with people who join them on this farm, including their earlier messages. Mention <strong>@hearth</strong> to invite a reply using the recent channel conversation. Your private chats and notes stay separate.</p></div>
    <Workspace name="channels" owner={identity.id} leftLabel="channels" conversation><section className="panel draft-list"><div className="section-heading"><h2>Gather around</h2><button className="quiet-button" onClick={() => void list().catch(reason => setError(reason.message))}>Refresh</button></div>
      {items.map(channel => <button key={channel.id} className={`draft-item ${selected === channel.id ? 'selected' : ''}`} disabled={busy} onClick={() => void enter(channel)}><span># {channel.name}</span><small>{channel.joined ? 'Joined' : 'Join'}</small></button>)}
      <form className="channel-create" onSubmit={async event => { event.preventDefault(); if (!name.trim() || busy) return; setBusy(true); setError(''); try { const channel = await api<Channel>('/api/v1/channels', mutation(identity, { name })); setName(''); await list(); if (!content.trim() && !attachments.length) setSelected(channel.id); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }}><label htmlFor="channel-name">Start a channel</label><input id="channel-name" placeholder="Kitchen table" value={name} maxLength={80} onChange={event => setName(event.target.value)} /><button className="quiet-button" disabled={busy || !name.trim()}>Create channel</button></form>
    </section><section className="panel chat-panel" aria-label="Shared channel">{room ? <><div className="section-heading"><h2># {room.name}</h2><button className="quiet-button" disabled={busy} onClick={async () => { if ((content.trim() || attachments.length) && !window.confirm('Leave this unsent channel message?')) return; setBusy(true); try { await api(`/api/v1/channels/${selected}/leave`, mutation(identity)); setSelected(''); setContent(''); setAttachments([]); await list(); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }}>Leave channel</button></div><div className="chat-transcript" ref={transcript} aria-label="Channel messages"><div className="transcript-content">{room.messages.map(message => <article className={`chat-message ${message.role}`} key={message.id}>{message.role === 'assistant' ? <ReplyHeading model={message.model_id} image={message.image} images={message.images} /> : <strong>{message.display_name}</strong>}<ChannelPictures channelId={selected} attachments={message.attachments} canMakeModel={identity.permissions.includes('capability.geometry.generate')} unsaved={dirty} /><ConversationMedia canMakeModel={identity.permissions.includes('capability.geometry.generate')} unsaved={dirty} image={message.image} images={message.images} content={message.content || (message.status === 'running' ? 'Thinking…' : '')} />{message.can_stop && <button className="quiet-button" disabled={busy} onClick={async () => { setBusy(true); try { await api(`/api/v1/channels/${selected}/runs/${message.request_id}/stop`, mutation(identity)); setRoom(await api<Room>(`/api/v1/channels/${selected}`)); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }}>Stop response</button>}{message.reason && <p className="small-copy">{message.reason}</p>}</article>)}{!room.messages.length && <p className="small-copy">Pull up a chair. Start with a hello.</p>}</div></div>{!atBottom && <button className="quiet-button latest-messages" onClick={followLatest}>Jump to latest</button>}<form className="chat-composer" onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }} onDrop={event => { if (event.dataTransfer.files.length) { event.preventDefault(); void upload(Array.from(event.dataTransfer.files)); } }} onSubmit={event => { event.preventDefault(); void send(); }}><ChannelPictures channelId={selected} attachments={attachments} disabled={busy} onRemove={id => void removeAttachment(id)} /><input ref={fileInput} className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" multiple aria-label="Attach channel images" disabled={busy || attachments.length >= 4} onChange={event => void upload(Array.from(event.target.files || []))} /><label className="sr-only" htmlFor="channel-message">Channel message</label><textarea ref={composer} id="channel-message" value={content} maxLength={4000} readOnly={busy} onPaste={event => { const files = Array.from(event.clipboardData.files); if (files.length) { event.preventDefault(); void upload(files); } }} placeholder="Talk together, or ask @hearth…" onChange={event => setContent(event.target.value)} onKeyDown={event => { if (submitsOnEnter(event)) { event.preventDefault(); void send(); } }} /><p className="small-copy">Enter to send · Shift+Enter for a new line · @hearth to ask your assistant · Paste or attach up to four images. Images are shared when you send.</p><div className="editor-actions"><button type="button" className="quiet-button" disabled={busy || attachments.length >= 4} onClick={() => fileInput.current?.click()}>Attach image</button><button className="primary-button" disabled={busy || (!content.trim() && !attachments.length)}>{busy ? 'Sending…' : 'Send to channel'}</button></div></form></> : <div className="chat-empty"><Icon name="users" /><h2>A place to think together.</h2><p>Join a channel to read its history and take part. hearth listens for its name before replying.</p></div>}</section></Workspace>{error && <p className="error-notice" role="alert">{error}</p>}</>;
}
