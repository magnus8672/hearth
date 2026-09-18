export type Identity = { state?: string; authorization_version?: number; id: string; display_name: string; roles: string[]; permissions: string[]; csrf_token: string; admin_origin: string; user_origin: string };

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, credentials: 'same-origin', cache: 'no-store' });
  // A proxy rejection can have an empty or HTML body. Keep the HTTP failure
  // visible instead of replacing it with a JSON parser exception.
  const value = await response.json().catch(() => null);
  if (!response.ok) {
    const message = value?.error?.message;
    const fallback = response.status === 413
      ? 'This upload exceeds the server limit. Choose a smaller file.'
      : [502, 503, 504].includes(response.status)
        ? 'hearth is temporarily unavailable. Please try again shortly.'
        : `hearth could not complete this request (HTTP ${response.status}). Try again.`;
    throw new Error(typeof message === 'string' && message ? message : fallback);
  }
  if (value === null) throw new Error('hearth returned an empty or unreadable response. Refresh the page to check whether your request completed.');
  return value as T;
}

export function mutation(identity: Identity, body?: unknown, method = 'POST'): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json', 'X-Hearth-CSRF': identity.csrf_token }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) };
}
