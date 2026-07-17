import type { CoachConversation, CoachMessage, CoachTurnResponse } from './types';

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export type CoachAuthAdapter = {
  getAccessToken: () => Promise<string | null>;
  refreshAccessToken: () => Promise<string | null>;
};

type ClientOptions = {
  baseUrl?: string;
  auth?: CoachAuthAdapter;
  fetchImpl?: FetchLike;
  timeoutMs?: number;
};

export class CoachApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'CoachApiError';
  }
}

const supabaseAuth: CoachAuthAdapter = {
  async getAccessToken() {
    const { supabase } = await import('./supabase');
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  },
  async refreshAccessToken() {
    const { supabase } = await import('./supabase');
    const { data, error } = await supabase.auth.refreshSession();
    if (error) return null;
    return data.session?.access_token ?? null;
  },
};

async function safeError(response: Response): Promise<CoachApiError> {
  try {
    const body: unknown = await response.json();
    if (typeof body === 'object' && body !== null && 'detail' in body) {
      const detail = (body as { detail?: unknown }).detail;
      if (typeof detail === 'string' && detail.length <= 200) {
        return new CoachApiError(response.status, detail);
      }
    }
  } catch {
    // The API may be offline or a proxy may return a non-JSON error page.
  }
  return new CoachApiError(response.status, 'The financial coach request failed.');
}

export function createCoachApiClient(options: ClientOptions = {}) {
  const configuredBaseUrl = options.baseUrl;
  const auth = options.auth ?? supabaseAuth;
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  const timeoutMs = options.timeoutMs ?? 35_000;

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const defaultBaseUrl = configuredBaseUrl === undefined
      ? (await import('./env')).fincoachApiUrl
      : configuredBaseUrl;
    const baseUrl = defaultBaseUrl.replace(/\/$/, '');
    if (!baseUrl) throw new CoachApiError(0, 'Missing EXPO_PUBLIC_FINCOACH_API_URL.');
    const initialToken = await auth.getAccessToken();
    if (!initialToken) throw new CoachApiError(401, 'No active session found.');

    const execute = async (token: string): Promise<Response> => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      try {
        return await fetchImpl(`${baseUrl}${path}`, {
          ...init,
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
            ...init.headers,
          },
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }
    };

    let response = await execute(initialToken);
    if (response.status === 401) {
      const refreshedToken = await auth.refreshAccessToken();
      if (!refreshedToken) throw new CoachApiError(401, 'No active session found.');
      response = await execute(refreshedToken);
    }
    if (!response.ok) throw await safeError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  return {
    listConversations: () => request<CoachConversation[]>('/coach/conversations'),
    createConversation: (title = 'New conversation') =>
      request<CoachConversation>('/coach/conversations', {
        method: 'POST',
        body: JSON.stringify({ title: title.trim() }),
      }),
    renameConversation: (sessionId: string, title: string) =>
      request<CoachConversation>(`/coach/conversations/${encodeURIComponent(sessionId)}`, {
        method: 'PATCH',
        body: JSON.stringify({ title: title.trim() }),
      }),
    deleteConversation: (sessionId: string) =>
      request<void>(`/coach/conversations/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),
    listMessages: (sessionId: string) =>
      request<CoachMessage[]>(`/coach/conversations/${encodeURIComponent(sessionId)}/messages`),
    sendMessage: (sessionId: string, messageId: string, content: string) =>
      request<CoachTurnResponse>(`/coach/conversations/${encodeURIComponent(sessionId)}/messages`, {
        method: 'POST',
        body: JSON.stringify({ message_id: messageId, content: content.trim() }),
      }),
  };
}

const defaultClient = createCoachApiClient();

export const listCoachConversations = defaultClient.listConversations;
export const createCoachConversation = defaultClient.createConversation;
export const renameCoachConversation = defaultClient.renameConversation;
export const deleteCoachConversation = defaultClient.deleteConversation;
export const listCoachMessages = defaultClient.listMessages;
export const sendCoachMessage = defaultClient.sendMessage;
