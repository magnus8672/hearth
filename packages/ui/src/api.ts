export type Identity = { id: string; display_name: string; roles: string[]; permissions: string[]; csrf_token: string; admin_origin: string; user_origin: string };

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, credentials: 'same-origin', cache: 'no-store' });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error?.message || 'hearth could not complete this request. Try again.');
  return value as T;
}

export function mutation(identity: Identity, body?: unknown, method = 'POST'): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json', 'X-Hearth-CSRF': identity.csrf_token }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) };
}
