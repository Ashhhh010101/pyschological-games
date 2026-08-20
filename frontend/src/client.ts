import type { GameId, GameState, Session } from "./types.js";

const SESSION_KEY = "loss-arcade-session";
const GAME_IDS: ReadonlySet<string> = new Set<GameId>([
  "vault", "burden", "chain", "insurance", "reputation",
]);

export class ApiConnectionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiConnectionError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isSession(value: unknown): value is Session {
  return isRecord(value) && typeof value.code === "string" && typeof value.playerId === "string";
}

export function readSession(): Session | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(SESSION_KEY) ?? "null");
    return isSession(value) ? value : null;
  } catch {
    return null;
  }
}

export function persistSession(session: Session | null): void {
  if (session) sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  else sessionStorage.removeItem(SESSION_KEY);
}

export function parseGameState(payload: unknown): GameState {
  const value: unknown = typeof payload === "string" ? JSON.parse(payload) : payload;
  if (
    !isRecord(value)
    || typeof value.code !== "string"
    || typeof value.gameId !== "string"
    || !GAME_IDS.has(value.gameId)
    || typeof value.version !== "number"
    || !Array.isArray(value.players)
  ) {
    throw new Error("The server returned an invalid game state.");
  }
  return value as unknown as GameState;
}

export async function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 10_000);
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  try {
    const response = await fetch(path, { ...options, headers, signal: controller.signal });
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
      throw new Error("The API returned an invalid response. Rebuild the frontend and restart FastAPI.");
    }
    const body: unknown = await response.json();
    if (!response.ok) {
      const error = isRecord(body) ? body.error : null;
      const detail = typeof error === "string"
        ? error
        : isRecord(error) && typeof error.message === "string"
          ? error.message
          : "Request failed.";
      throw new Error(detail);
    }
    return body as T;
  } catch (error) {
    if (error instanceof TypeError || (error instanceof DOMException && error.name === "AbortError")) {
      throw new ApiConnectionError("The game server is unavailable.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function escapeHtml(value: unknown): string {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function readNumber(stats: Record<string, number | string>, key: string): number {
  const value = stats[key];
  return typeof value === "number" ? value : 0;
}
