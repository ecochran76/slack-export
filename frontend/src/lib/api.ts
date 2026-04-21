export interface ApiEnvelope<T> {
  ok: boolean;
  error?: {
    code?: string;
    message?: string;
  };
  data?: T;
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: {
      accept: "application/json",
      ...(init?.headers ?? {})
    }
  });
  const payload = (await response.json().catch(() => null)) as ApiEnvelope<T> | null;
  if (!response.ok) {
    throw new Error(payload?.error?.message ?? `Request failed with ${response.status}`);
  }
  return payload as T;
}
