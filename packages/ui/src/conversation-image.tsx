import type { ConversationImage as ImageResult } from '../../contracts/src/generated';

export type ConversationImage = ImageResult;

export function ConversationMedia({ image, images, content, unsaved = false }: { image?: ImageResult | null; images?: ImageResult[]; content: string; unsaved?: boolean }) {
  const pictures = images?.length ? images : image ? [image] : [];
  const complete = pictures.filter(item => item.status === 'completed').length;
  return <><div className="message-text">{pictures.length > 1 ? `${complete} of ${pictures.length} images ready.` : pictures.length ? (pictures[0].status === 'completed' ? pictures[0].variation ? 'Here’s a new variation.' : 'Here’s your image.' : '') : content}</div><div className={pictures.length > 1 ? 'conversation-image-batch' : undefined}>{pictures.map(item => <ConversationPicture key={item.request.id} image={item} unsaved={unsaved} />)}</div></>;
}

export function ConversationPicture({ image, unsaved = false }: { image: ImageResult; unsaved?: boolean }) {
  const { request } = image;
  if (image.status === 'deleted') return <figure className="conversation-image"><p className="small-copy">{(image.batch_count || 1) > 1 ? `Image ${image.batch_index} of ${image.batch_count} deleted.` : 'Image deleted.'}</p></figure>;
  const source = `/api/v1/conversation-images/${encodeURIComponent(request.id)}/image`;
  return <figure className="conversation-image">
    {(image.batch_count || 1) > 1 && <p className="small-copy">Image {image.batch_index} of {image.batch_count}</p>}
    {image.status === 'completed' ? <a href={source} target="_blank" rel="noreferrer" aria-label="Open generated image"><img src={source} alt={request.prompt} onLoad={event => { const transcript = event.currentTarget.closest('.chat-transcript'); if (transcript && transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < event.currentTarget.clientHeight + 180) transcript.scrollTop = transcript.scrollHeight; }} /></a> : <div className="conversation-image-progress" role="status"><strong>{image.status === 'queued' ? 'Waiting for the earlier images…' : image.status === 'running' ? 'Making your image…' : image.status === 'cancelled' ? 'Image stopped' : 'Image needs attention'}</strong>{image.status === 'running' && <><progress aria-label="Image generation progress" max={request.steps} value={image.progress} /><span className="small-copy">{image.progress ? `${image.progress} of ${request.steps} detail passes` : 'Preparing the local image model…'}</span></>}{image.reason && <p>{image.reason}</p>}</div>}
    <figcaption><span className="small-copy">{image.variation ? 'New image from the earlier description' : image.status === 'completed' ? 'Made locally' : 'Local image generation'} · {request.shape}</span>{image.status === 'completed' && <div className="target-actions"><a className="quiet-button" href={source} download={`hearth-${request.id}.png`}>Save PNG</a><a className="quiet-button button-link" href={`#geometry/conversation/${request.id}`} onClick={event => { if (unsaved && !window.confirm('Leave your unsent message to make a model?')) event.preventDefault(); }}>Make a model</a></div>}</figcaption>
    <details><summary>Image details</summary><p>{request.prompt}</p>{image.planning_model && <p className="small-copy">Prompt planned locally with {image.planning_model}. {image.variation && 'This is a new render, not an edit of the earlier pixels.'}</p>}<p className="small-copy">{request.model}<br />Seed {request.seed} · {request.steps} detail passes</p></details>
  </figure>;
}
