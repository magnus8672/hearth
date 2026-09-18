/** Only saved hearth image IDs can become reference URLs. Never follow model URLs. */
export function geometryReference(hash: string): string {
  const channel = /^#geometry\/channel\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i.exec(hash);
  if (channel) return `channel/${channel[1]}/${channel[2]}`;
  const match = /^#geometry\/(?:(gallery|conversation)\/)?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i.exec(hash);
  return match ? `${match[1] || 'gallery'}/${match[2]}` : '';
}

export function geometryReferenceUrl(source: string): string {
  const [kind, id, attachment] = source.split('/');
  return kind === 'channel' ? `/api/v1/channels/${id}/attachments/${attachment}` : `/api/v1/${kind === 'conversation' ? 'conversation-images' : 'images'}/${id}/image`;
}

export async function prepareGeometryReference(blob: Blob): Promise<File> {
  if (!blob.size || blob.size > 64 * 1024 * 1024) throw new Error('This saved image is too large to use as a reference.');
  // Gallery output may be a 4K PNG larger than the upload limit. Resize a copy
  // to the same maximum edge used by the head, keeping the original untouched.
  const bitmap = await createImageBitmap(blob);
  try {
    if (bitmap.width * bitmap.height > 20_000_000) throw new Error('Choose an image up to 20 megapixels.');
    const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext('2d');
    if (!context) throw new Error('The image could not be prepared. Try uploading a reference instead.');
    context.fillStyle = 'white'; context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const jpeg = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('The image could not be prepared.')), 'image/jpeg', .92));
    return new File([jpeg], 'Your hearth image.jpg', { type: 'image/jpeg' });
  } finally { bitmap.close(); }
}
