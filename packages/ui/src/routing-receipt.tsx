export type RouteReceipt = { capability_id: string; provider_name: string; model_id: string; selection?: { policy?: string; reason?: string; candidate_count?: number; admission_changed_selection?: boolean; intent?: { source: string; proposed?: string; model?: string; elapsed_ms?: number; answer_confidence?: number; attempts?: { source: string; reason: string }[] } } };
const reasons: Record<string, string> = { ordered_priority: 'First eligible provider by priority', scoped_affinity: 'Kept the eligible provider for this conversation', switchyard_balanced: 'Switchyard selected among interchangeable providers', switchyard_unavailable_ordered_fallback: 'Switchyard unavailable; used the ordered fallback' };
export function RoutingReceipt({ receipt }: { receipt?: RouteReceipt }) {
  if (!receipt?.selection) return null;
  const selection = receipt.selection, intent = selection.intent;
  return <details className="routing-receipt"><summary>How this reply was routed</summary><p>{receipt.capability_id} · {receipt.provider_name} · {receipt.model_id}</p><p>{reasons[selection.reason || ''] || 'Typed capability dispatch'}{selection.candidate_count !== undefined && ` · ${selection.candidate_count} eligible target(s)`}</p>
    {selection.admission_changed_selection && <p>Availability changed before admission; an eligible alternative answered.</p>}
    {intent && <p>Intent: {intent.source.replaceAll('_', ' ')}{intent.model && ` · ${intent.model}`}{intent.elapsed_ms !== undefined && ` · ${intent.elapsed_ms.toFixed(0)} ms`}{intent.answer_confidence !== undefined && ` · ${(intent.answer_confidence*100).toFixed(1)}% answer confidence`}</p>}
    {!!intent?.attempts?.length && <p>Fallback: {intent.attempts.map(item => `${item.source}: ${item.reason.replaceAll('_', ' ')}`).join('; ')}</p>}
  </details>;
}
