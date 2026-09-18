import type { ChatAttachment } from './chat-pictures';

export function ChannelPictures({ channelId, attachments, onRemove, disabled, canMakeModel, unsaved }: {
  channelId: string; attachments?: ChatAttachment[]; onRemove?: (id: string) => void;
  disabled?: boolean; canMakeModel?: boolean; unsaved?: boolean;
}) {
  if (!attachments?.length) return null;
  return <div className="chat-pictures">{attachments.map((item, index) => {
    const source = `/api/v1/channels/${encodeURIComponent(channelId)}/attachments/${encodeURIComponent(item.id)}`;
    return <figure key={item.id}><a href={source} target="_blank" rel="noreferrer"><img src={source} alt={`Attached image ${index + 1}`} /></a><figcaption className="small-copy">{item.width} × {item.height}
      {onRemove ? <button className="quiet-button" type="button" disabled={disabled} aria-label={`Remove attached image ${index + 1}`} onClick={() => onRemove(item.id)}>Remove</button> : canMakeModel && <a className="quiet-button button-link" href={`#geometry/channel/${channelId}/${item.id}`} onClick={event => { if (unsaved && !window.confirm('Leave your unsent message to generate a model?')) event.preventDefault(); }}>Generate model</a>}
    </figcaption></figure>;
  })}</div>;
}
