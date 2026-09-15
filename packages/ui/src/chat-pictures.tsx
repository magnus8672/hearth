export type ChatAttachment = { id: string; width: number; height: number; media_type: string; byte_count: number };

export function ChatPictures({ chatId, attachments, onRemove, disabled }: {
  chatId: string; attachments?: ChatAttachment[]; onRemove?: (id: string) => void; disabled?: boolean;
}) {
  if (!attachments?.length) return null;
  return <div className="chat-pictures">{attachments.map((item, index) => {
    const source = `/api/v1/chats/${encodeURIComponent(chatId)}/attachments/${encodeURIComponent(item.id)}`;
    return <figure key={item.id}><a href={source} target="_blank" rel="noreferrer"><img src={source} alt={`Attached image ${index + 1}`} /></a><figcaption className="small-copy">{item.width} × {item.height}{onRemove && <button className="quiet-button" type="button" disabled={disabled} aria-label={`Remove attached image ${index + 1}`} onClick={() => onRemove(item.id)}>Remove</button>}</figcaption></figure>;
  })}</div>;
}
