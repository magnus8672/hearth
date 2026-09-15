import type { ConversationImage } from './conversation-image';

export function ReplyHeading({ name = 'hearth', model, image, images }: {
  name?: string; model?: string | null; image?: ConversationImage | null; images?: ConversationImage[];
}) {
  const pictures = images?.length ? images : image ? [image] : [];
  const models = [...new Set(pictures.length ? pictures.map(item => item.request.model) : model ? [model] : [])];
  return <header className="reply-heading"><strong>{name}</strong><span className="reply-model">{models.length ? models.join(' · ') : 'Model not recorded'}</span></header>;
}
