import { useEffect, useRef, useState } from 'react';
import { api, mutation, type Identity } from './api';
import { Icon } from './index';
import { ReplyHeading } from './reply-heading';
import { ConversationMedia, type ConversationImage } from './conversation-image';
import { submitsOnEnter } from './side-notes';

type Channel = { id: string; name: string; joined: boolean };
type Room = { id: string; name: string; revision: number; messages: { id: string; role: string; display_name: string; model_id?: string | null; content: string; status: string; reason: string | null; image?: ConversationImage | null; images?: ConversationImage[]; can_stop?: boolean; request_id?: string }[] };

export function Channels({ identity, onDirty }: { identity: Identity; onDirty: (dirty: boolean) => void }) {
  const [items, setItems] = useState<Channel[]>([]);
  const [selected, setSelected] = useState('');
  const [room, setRoom] = useState<Room | null>(null);
  const [name, setName] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const sending = useRef(false);
  const pending = useRef<{ request_id: string; content: string; channel: string } | null>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const dirty = !!content.trim() || !!name.trim();
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
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const value = await api<Room>(`/api/v1/channels/${selected}`, { signal: controller.signal });
        if (!disposed) { setRoom(value); timer = setTimeout(() => void poll(), 1000); }
      } catch (reason) { if (!disposed) setError((reason as Error).message); }
    }
    void poll();
    return () => { disposed = true; controller.abort(); clearTimeout(timer); };
  }, [selected]);
  useEffect(() => {
    const element = transcript.current;
    if (element && element.scrollHeight - element.scrollTop - element.clientHeight < 180) element.scrollTop = element.scrollHeight;
  }, [room]);
  async function enter(channel: Channel) {
    if (content.trim() && !window.confirm('Leave this unsent channel message?')) return;
    setBusy(true); setError('');
    try {
      if (!channel.joined) await api(`/api/v1/channels/${channel.id}/join`, mutation(identity));
      setContent(''); pending.current = null; setSelected(channel.id); await list();
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  async function send() {
    if (!selected || !room || !content.trim() || sending.current) return;
    sending.current = true; setBusy(true); setError('');
    try {
      if (pending.current?.content !== content || pending.current.channel !== selected) pending.current = { request_id: crypto.randomUUID(), content, channel: selected };
      await api(`/api/v1/channels/${selected}/messages`, mutation(identity, { request_id: pending.current.request_id, content }));
      setContent(''); pending.current = null;
      setRoom(await api<Room>(`/api/v1/channels/${selected}`));
    } catch (reason) { setError((reason as Error).message); } finally { sending.current = false; setBusy(false); composer.current?.focus(); }
  }
  return <><div className="info-banner"><Icon name="users" /><p>Channels are shared with people who join them on this farm, including their earlier messages. Mention <strong>@hearth</strong> to invite a reply using the recent channel conversation. Your private chats and notes stay separate.</p></div>
    <div className="draft-layout channel-layout"><section className="panel draft-list"><div className="section-heading"><h2>Gather around</h2><button className="quiet-button" onClick={() => void list().catch(reason => setError(reason.message))}>Refresh</button></div>
      {items.map(channel => <button key={channel.id} className={`draft-item ${selected === channel.id ? 'selected' : ''}`} disabled={busy} onClick={() => void enter(channel)}><span># {channel.name}</span><small>{channel.joined ? 'Joined' : 'Join'}</small></button>)}
      <form className="channel-create" onSubmit={async event => { event.preventDefault(); if (!name.trim() || busy) return; setBusy(true); setError(''); try { const channel = await api<Channel>('/api/v1/channels', mutation(identity, { name })); setName(''); await list(); if (!content.trim()) setSelected(channel.id); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }}><label htmlFor="channel-name">Start a channel</label><input id="channel-name" placeholder="Kitchen table" value={name} maxLength={80} onChange={event => setName(event.target.value)} /><button className="quiet-button" disabled={busy || !name.trim()}>Create channel</button></form>
    </section><section className="panel chat-panel" aria-label="Shared channel">{room ? <><div className="section-heading"><h2># {room.name}</h2><button className="quiet-button" disabled={busy} onClick={async () => { if (content.trim() && !window.confirm('Leave this unsent channel message?')) return; setBusy(true); try { await api(`/api/v1/channels/${selected}/leave`, mutation(identity)); setSelected(''); setContent(''); await list(); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }}>Leave channel</button></div><div className="chat-transcript" ref={transcript} aria-label="Channel messages">{room.messages.map(message => <article className={`chat-message ${message.role}`} key={message.id}>{message.role === 'assistant' ? <ReplyHeading model={message.model_id} image={message.image} images={message.images} /> : <strong>{message.display_name}</strong>}<ConversationMedia unsaved={dirty} image={message.image} images={message.images} content={message.content || (message.status === 'running' ? 'Thinking…' : '')} />{message.can_stop && <button className="quiet-button" disabled={busy} onClick={async () => { setBusy(true); try { await api(`/api/v1/channels/${selected}/runs/${message.request_id}/stop`, mutation(identity)); setRoom(await api<Room>(`/api/v1/channels/${selected}`)); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }}>Stop response</button>}{message.reason && <p className="small-copy">{message.reason}</p>}</article>)}{!room.messages.length && <p className="small-copy">Pull up a chair. Start with a hello.</p>}</div><form className="chat-composer" onSubmit={event => { event.preventDefault(); void send(); }}><label className="sr-only" htmlFor="channel-message">Channel message</label><textarea ref={composer} id="channel-message" value={content} maxLength={4000} disabled={busy} placeholder="Talk together, or ask @hearth…" onChange={event => setContent(event.target.value)} onKeyDown={event => { if (submitsOnEnter(event)) { event.preventDefault(); void send(); } }} /><p className="small-copy">Enter to send · Shift+Enter for a new line · @hearth to ask your assistant</p><button className="primary-button" disabled={busy || !content.trim()}>Send to channel</button></form></> : <div className="chat-empty"><Icon name="users" /><h2>A place to think together.</h2><p>Join a channel to read its history and take part. hearth listens for its name before replying.</p></div>}</section></div>{error && <p className="error-notice" role="alert">{error}</p>}</>;
}
