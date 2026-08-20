export type GameId = "vault" | "burden" | "chain" | "insurance" | "reputation";
export type Phase = "lobby" | "decision" | "results" | "finished";

export interface GameGuide {
  id: GameId;
  number: string;
  name: string;
  tagline: string;
  description: string;
  objective: string;
  rounds: string;
  steps: Array<{ title: string; text: string }>;
  resources: string[];
  score: string;
  accent: string;
}

export interface PlayerState {
  id: string;
  name: string;
  acted: boolean;
  stats: Record<string, number | string>;
  score: number | null;
}

export interface GameState {
  code: string;
  gameId: GameId;
  gameName: string;
  phase: Phase;
  round: number;
  totalRounds: number;
  prompt: { title: string; subtitle: string } | null;
  result: {
    title: string;
    detail: string;
    pressure: string;
    forced: boolean;
    changes: Array<{ playerId: string; summary: string }>;
  } | null;
  version: number;
  hostId: string;
  viewerId: string;
  viewerHasActed: boolean;
  viewerHint: string | null;
  players: PlayerState[];
}

export interface Session {
  code: string;
  playerId: string;
}
