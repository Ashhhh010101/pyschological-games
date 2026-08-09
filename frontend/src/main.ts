import type { GameGuide, GameId, GameState, Phase, PlayerState, Session } from "./types";

const GAMES: Record<GameId, GameGuide> = {
  vault: {
    id: "vault", number: "01", name: "The Vault", accent: "#b7e4c7",
    tagline: "Safety has an opportunity cost.",
    description: "Lock wealth away from danger or keep it liquid enough to seize opportunity. The room’s combined fear changes what happens to everyone.",
    objective: "Finish with the highest vault-weighted score while surviving five shared events.", rounds: "5 rounds · 6 event types",
    steps: [
      { title: "Read the category", text: "You know whether Flood, Opportunity, Tax, Audit, Rescue, or Fracture is approaching—but not its severity." },
      { title: "Choose liquidity", text: "Secretly deposit any amount. Vault wealth is resilient but normally cannot be withdrawn." },
      { title: "Spend tools", text: "A key withdraws 20% of your vault. Your one emergency seal caps liquid losses at 5%." },
      { title: "Face the room", text: "Too little shared liquidity creates scarcity; too much leaves everyone exposed." },
    ],
    resources: ["100 liquid", "2 keys", "1 emergency seal"],
    score: "Vault + 50% liquid + 3 per key − penalties + rescue bonuses",
  },
  burden: {
    id: "burden", number: "02", name: "The Burden", accent: "#e7c78e",
    tagline: "There is no completely safe choice.",
    description: "Protected wealth always decays. Exposed wealth can grow or collapse. Transfers become permanent—and everyone learns who helped whom.",
    objective: "Hold the greatest surviving wealth after six rounds without being crushed by collective exposure.", rounds: "6 rounds · hidden thresholds",
    steps: [
      { title: "Read the burden", text: "A shared condition—such as Panic or Expansion—tilts the coming resolution." },
      { title: "Allocate everything", text: "Split all wealth between Protected, Exposed, and a permanent transfer to another player." },
      { title: "Judge collective risk", text: "The server combines every exposed allocation. Hidden pressure bands determine growth or collapse." },
      { title: "Recover if broken", text: "A player reaching zero receives 15 emergency wealth and a score-reducing Debt Scar." },
    ],
    resources: ["100 wealth", "3 protection seals", "0 Debt Scars"],
    score: "Surviving wealth − 12% per Debt Scar + support bonuses",
  },
  chain: {
    id: "chain", number: "03", name: "Chain of Responsibility", accent: "#dca39a",
    tagline: "Value rises with the danger.",
    description: "The Charge grows more profitable and more likely to rupture. Carry it, pass responsibility, refuse, redirect, or end the chain early.",
    objective: "Secure the most value without being exposed when the Charge ruptures.", rounds: "Up to 8 chains · ends at 5 ruptures",
    steps: [
      { title: "Read your clue", text: "Every player receives a private approximate risk estimate. It may be inaccurate." },
      { title: "Choose a stance", text: "Carry for upside, pass for 70%, refuse safely, redirect at a cost, or bank at 50%." },
      { title: "Test the Charge", text: "More carriers increase shared rupture risk. The server resolves one hidden roll." },
      { title: "Mark the outcome", text: "Carriers lose unsecured and 25% secured on rupture, but earn Courage. Banking adds a Breaker penalty." },
    ],
    resources: ["20 secured", "2 refusal tokens", "1 private clue each chain"],
    score: "Secured value + 10 per Courage Mark − 5 per Breaker Mark",
  },
  insurance: {
    id: "insurance", number: "04", name: "Insurance Market", accent: "#a9c9e8",
    tagline: "Other players are the weather.",
    description: "Buy protection, collect premiums, strengthen the market, or quietly raise the danger. One event can cascade across every underwriter.",
    objective: "Build the highest combined asset and liquid value after five market cycles.", rounds: "5 cycles · correlated losses",
    steps: [
      { title: "Study the forecast", text: "The market signals Liquidity Failure, Structural Damage, or Reputation Shock." },
      { title: "Take a market action", text: "Strengthen, extract profit, buy protection, underwrite others, or sabotage the room." },
      { title: "Move threat probability", text: "Every choice changes a hidden shared disaster probability." },
      { title: "Settle claims", text: "Insurance reduces asset loss. Underwriters pay obligations automatically and can become insolvent." },
    ],
    resources: ["100 assets", "40 liquid", "Stable reputation"],
    score: "Assets + liquid + premiums − unpaid obligations + reliability",
  },
  reputation: {
    id: "reputation", number: "05", name: "Reputation Economy", accent: "#c8b7e8",
    tagline: "Identity is currency.",
    description: "Spend reputation to pursue ambition, keep promises, support allies, or challenge rivals. Spent influence always returns to somebody.",
    objective: "Complete personal ambitions while preserving enough reputation to control the final outcome.", rounds: "5 crises · final influence reveal",
    steps: [
      { title: "Read the crisis", text: "A public promise, evidence leak, coalition vote, trust crisis, or mandate frames the round." },
      { title: "Spend your identity", text: "Pursue ambition, protect a promise, support someone, challenge a rival, or conserve." },
      { title: "Redistribute influence", text: "All reputation spent this round returns to the room’s most-supported voice." },
      { title: "Build a legacy", text: "Ambitions, promises, remaining reputation, and outcome alignment all affect the final score." },
    ],
    resources: ["60 reputation", "Private ambitions", "1 public promise"],
    score: "30 per ambition + ½ reputation + promises + outcome alignment",
  },
};

const STAT_LABELS: Record<GameId, Record<string, string>> = {
  vault: { liquid: "Liquid", vault: "Vault", vaultRange: "Vault range", keys: "Keys", seals: "Seals", penalties: "Penalties", rescueBonus: "Rescue bonus" },
  burden: { wealth: "Wealth", seals: "Seals", debtScars: "Debt Scars", supportBonus: "Support" },
  chain: { secured: "Secured", unsecured: "Unsecured", refusals: "Refusals", courage: "Courage", breaker: "Breaker" },
  insurance: { assets: "Assets", liquid: "Liquid", premiums: "Premiums", obligations: "Obligations", reliability: "Reliability" },
  reputation: { reputation: "Reputation", ambitions: "Ambitions", keptPromises: "Promises kept", brokenPromises: "Promises broken", alignment: "Alignment" },
};

const app = document.querySelector<HTMLElement>("#app")!;
let session: Session | null = readSession();
let state: GameState | null = null;
let selectedGame: GameId | null = null;
let showRules = false;
let busy = false;
let message = "";
let serverStatus: "checking" | "online" | "offline" = "checking";
let pollTimer: number | undefined;
let roomSocket: WebSocket | undefined;
let socketRetry: number | undefined;

function readSession(): Session | null {
  try {
    const value = JSON.parse(sessionStorage.getItem("loss-arcade-session") || "null");
    return value?.code && value?.playerId ? value : null;
  } catch { return null; }
}

function saveSession(next: Session | null): void {
  roomSocket?.close(); roomSocket = undefined;
  window.clearTimeout(socketRetry);
  session = next;
  if (next) sessionStorage.setItem("loss-arcade-session", JSON.stringify(next));
  else sessionStorage.removeItem("loss-arcade-session");
}

function connectRoomSocket(): void {
  if (!session) return;
  roomSocket?.close();
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  roomSocket = new WebSocket(`${protocol}//${location.host}/api/rooms/${encodeURIComponent(session.code)}/ws?playerId=${encodeURIComponent(session.playerId)}`);
  roomSocket.onopen = () => { serverStatus = "online"; render(); };
  roomSocket.onmessage = (event) => { state = JSON.parse(event.data) as GameState; selectedGame = state.gameId; serverStatus = "online"; render(); };
  roomSocket.onclose = () => { if (session) { serverStatus = "offline"; render(); socketRetry = window.setTimeout(connectRoomSocket, 2000); } };
}

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) throw new Error("The API returned an invalid response. Rebuild the frontend and restart FastAPI.");
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "Request failed.");
    serverStatus = "online";
    return body as T;
  } catch (error) {
    if (error instanceof TypeError || (error instanceof DOMException && error.name === "AbortError")) serverStatus = "offline";
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function escapeHtml(value: unknown): string {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function readNumber(stats: Record<string, number | string>, key: string): number {
  const value = stats[key];
  return typeof value === "number" ? value : 0;
}

async function withBusy(task: () => Promise<void>): Promise<void> {
  if (busy) return;
  busy = true; message = ""; render();
  try { await task(); }
  catch (error) { message = error instanceof Error ? error.message : "Something went wrong."; }
  finally { busy = false; render(); }
}

async function refresh(quiet = false): Promise<void> {
  if (!session || (busy && quiet)) return;
  try {
    const next = await api<GameState>(`/api/rooms/${encodeURIComponent(session.code)}?playerId=${encodeURIComponent(session.playerId)}`);
    const changed = !state || state.version !== next.version;
    state = next; selectedGame = next.gameId;
    if (changed) render();
  } catch (error) {
    if (!quiet) { message = error instanceof Error ? error.message : "Could not load room."; render(); }
  }
}

function render(): void {
  document.documentElement.style.setProperty("--game-accent", selectedGame ? GAMES[selectedGame].accent : "#b7e4c7");
  if (session && state) renderGame();
  else if (selectedGame) renderGuide(selectedGame);
  else renderCatalog();
}

function alertHtml(): string { return message ? `<p class="alert" role="alert">${escapeHtml(message)}</p>` : ""; }

function statusPill(): string {
  const label = serverStatus === "online" ? "FastAPI online" : serverStatus === "offline" ? "Server offline" : "Checking server";
  return `<span class="server-status status-${serverStatus}"><i></i>${label}</span>`;
}

function renderCatalog(): void {
  const inviteCode = location.hash.slice(1).toUpperCase().replace(/[^A-Z]/g, "").slice(0, 5);
  app.innerHTML = `
    <section class="catalog-shell">
      <header class="catalog-header">
        <div class="mini-brand"><span class="mini-mark">P</span><span>PSYCHOLOGICAL GAMES</span></div>
        ${statusPill()}
        <form id="quick-join" class="quick-join">
          <input name="name" maxlength="24" required placeholder="Your name" aria-label="Your name" />
          <input name="code" maxlength="5" required value="${escapeHtml(inviteCode)}" placeholder="ROOM CODE" aria-label="Room code" />
          <button ${busy ? "disabled" : ""}>Join room</button>
        </form>
      </header>
      ${alertHtml()}
      <div class="catalog-intro">
        <p class="eyebrow">Five social experiments</p>
        <h1>What are you<br/>afraid to lose?</h1>
        <div class="intro-copy"><p>Each game turns ownership, uncertainty, and other people’s choices into pressure. Choose one to learn the rules before entering.</p><span>Choose → Learn → Invite → Play</span></div>
      </div>
      <div class="game-catalog">
        ${Object.values(GAMES).map((game) => `
          <button class="game-tile" data-game="${game.id}" style="--tile-accent:${game.accent}">
            <span class="tile-number">${game.number}</span>
            <span class="tile-body"><small>${escapeHtml(game.rounds)}</small><strong>${escapeHtml(game.name)}</strong><em>${escapeHtml(game.tagline)}</em></span>
            <span class="tile-arrow">↗</span>
          </button>`).join("")}
      </div>
      <p class="catalog-foot">Local multiplayer · 2–10 players · server-authoritative outcomes</p>
    </section>`;
  document.querySelectorAll<HTMLElement>("[data-game]").forEach((button) => button.addEventListener("click", () => {
    selectedGame = button.dataset.game as GameId; message = ""; render(); window.scrollTo(0, 0);
  }));
  bindJoin("#quick-join");
}

function guideContent(game: GameGuide, compact = false): string {
  return `
    <div class="guide-hero" style="--tile-accent:${game.accent}">
      <div><p class="eyebrow">Game ${game.number} · ${escapeHtml(game.rounds)}</p><h1>${escapeHtml(game.name)}</h1><p class="guide-tagline">${escapeHtml(game.tagline)}</p></div>
      <p class="guide-description">${escapeHtml(game.description)}</p>
    </div>
    <div class="guide-objective"><span>Objective</span><p>${escapeHtml(game.objective)}</p></div>
    <div class="steps-heading"><p class="eyebrow">How a round works</p><h2>Four clear steps</h2></div>
    <ol class="steps-grid ${compact ? "compact-steps" : ""}">
      ${game.steps.map((step, index) => `<li><span class="step-icon">${["◎", "↔", "⚡", "★"][index]}</span><div><span class="step-number">${String(index + 1).padStart(2, "0")}</span><strong>${escapeHtml(step.title)}</strong><p>${escapeHtml(step.text)}</p></div></li>`).join("")}
    </ol>
    <div class="guide-meta">
      <div><span>Starting resources</span><p>${game.resources.map(escapeHtml).join(" · ")}</p></div>
      <div><span>Final score</span><p>${escapeHtml(game.score)}</p></div>
    </div>`;
}

function renderGuide(gameId: GameId): void {
  const game = GAMES[gameId];
  app.innerHTML = `
    <section class="guide-shell">
      <header class="guide-nav"><button id="back-catalog" class="text-button">← All games</button><span>READ THE ROOM BEFORE YOU ENTER</span></header>
      ${alertHtml()}
      ${guideContent(game)}
      <section class="create-room-panel">
        <div><p class="eyebrow">Ready to play?</p><h2>Create a ${escapeHtml(game.name)} room</h2><p>You become the host. Share the five-letter room code with the other players.</p></div>
        <form id="create-form"><label>Your name<input name="name" maxlength="24" required autocomplete="nickname" placeholder="The Curator" /></label><button class="primary" ${busy ? "disabled" : ""}>${busy ? "Opening…" : "Create room"}</button></form>
      </section>
    </section>`;
  document.querySelector("#back-catalog")?.addEventListener("click", () => { selectedGame = null; message = ""; render(); });
  document.querySelector<HTMLFormElement>("#create-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget as HTMLFormElement);
    void withBusy(async () => {
      const created = await api<Session>("/api/rooms", { method: "POST", body: JSON.stringify({ name: data.get("name"), gameId }) });
      saveSession(created); location.hash = created.code; await refresh();
    });
  });
}

function bindJoin(selector: string): void {
  document.querySelector<HTMLFormElement>(selector)?.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget as HTMLFormElement);
    const code = String(data.get("code") || "").toUpperCase();
    void withBusy(async () => {
      const joined = await api<Session>(`/api/rooms/${encodeURIComponent(code)}/join`, { method: "POST", body: JSON.stringify({ name: data.get("name") }) });
      saveSession(joined); location.hash = joined.code; await refresh();
    });
  });
}

function renderGame(): void {
  const game = state!;
  const guide = GAMES[game.gameId];
  const me = game.players.find((player) => player.id === game.viewerId)!;
  const isHost = game.hostId === game.viewerId;
  app.innerHTML = `
    <div class="game-shell">
      <header class="topbar">
        <div><span class="mini-mark">${guide.number}</span><span class="wordmark">${escapeHtml(game.gameName)}</span></div>
        <div class="room-chip">ROOM <strong>${escapeHtml(game.code)}</strong> <button id="copy-code" class="icon-button">COPY</button></div>
        <div class="top-actions">${statusPill()}<button id="rules" class="text-button">How to play</button><button id="leave" class="text-button">Leave</button></div>
      </header>
      ${alertHtml()}
      ${renderPhaseRail(game.phase)}
      <div class="game-grid">
        <main class="main-panel">${renderPhase(game, me, isHost)}</main>
        <aside class="side-panel">${renderStats(game.gameId, me)}${renderPlayers(game)}</aside>
      </div>
    </div>
    ${showRules ? `<div class="rules-overlay"><div class="rules-modal"><button id="close-rules" class="modal-close">×</button>${guideContent(guide, true)}</div></div>` : ""}`;
  bindGameEvents(game, me);
}

function renderPhaseRail(phase: Phase): string {
  const order: Phase[] = ["lobby", "decision", "results", "finished"];
  const current = order.indexOf(phase);
  return `<nav class="phase-rail" aria-label="Game progress">${order.map((item, index) => `<span class="${index === current ? "current" : index < current ? "done" : ""}"><i>${index < current ? "✓" : index + 1}</i>${item === "results" ? "Reveal" : item === "finished" ? "Final" : item[0].toUpperCase() + item.slice(1)}</span>`).join("")}</nav>`;
}

function renderPhase(game: GameState, me: PlayerState, isHost: boolean): string {
  const submitted = game.players.filter((p) => p.acted).length;
  if (game.phase === "lobby") return `
    <div class="phase-heading"><p class="eyebrow">${escapeHtml(game.gameName)}</p><h1>Gather the room.</h1><p>Everyone can open “How to play” before the host begins.</p></div>
    <div class="lobby-code"><span>Invite code</span><strong>${escapeHtml(game.code)}</strong><small>Share the code or copy the invite link.</small></div>
    <div class="lobby-status"><span class="pulse"></span>${game.players.length} of 10 players connected</div>
    ${isHost ? `<button id="start-game" class="primary wide" ${busy || game.players.length < 2 ? "disabled" : ""}>${busy ? "Starting…" : "Everyone understands · Begin"}</button>` : `<p class="waiting">Waiting for the host to begin…</p>`}`;

  if (game.phase === "decision") return `
    <div class="round-line"><span>ROUND ${game.round} / ${game.totalRounds}</span><span>${submitted} / ${game.players.length} decisions sealed</span></div>
    <div class="event-card"><p class="eyebrow">Shared condition</p><h1>${escapeHtml(game.prompt?.title)}</h1><p>${escapeHtml(game.prompt?.subtitle)}</p></div>
    ${liveGuide(game.gameId, game, me)}
    ${game.viewerHint ? `<div class="private-clue"><span>PRIVATE CLUE</span><p>${escapeHtml(game.viewerHint)}</p></div>` : ""}
    ${game.viewerHasActed ? `<div class="sealed-state"><div class="seal-glyph">✓</div><h2>Your decision is sealed.</h2><p>Resolution begins automatically when everyone submits.</p></div>` : renderActionForm(game, me)}
    ${isHost ? `<button id="force-resolve" class="text-button force">Resolve with safe defaults for missing players</button>` : ""}`;

  if (game.phase === "results" && game.result) {
    const mine = game.result.changes.find((change) => change.playerId === game.viewerId);
    return `
      <div class="round-line"><span>ROUND ${game.round} RESOLVED</span><span class="pressure">${escapeHtml(game.result.pressure)}</span></div>
      <div class="result-card"><p class="eyebrow">Round replay</p><div class="replay-track"><span class="replay-node done">Choice</span><i>→</i><span class="replay-node done">Room effect</span><i>→</i><span class="replay-node current">Outcome</span></div><h1>${escapeHtml(game.result.title)}</h1><p>${escapeHtml(game.result.detail)}</p>${game.result.forced ? `<p class="muted">Missing players received the game’s safest default action.</p>` : ""}<div class="your-change"><span>Your change</span><strong>${escapeHtml(mine?.summary || "No change")}</strong></div></div>
      ${isHost ? `<button id="next-round" class="primary wide" ${busy ? "disabled" : ""}>${busy ? "Continuing…" : game.round === game.totalRounds ? "Reveal final standing" : "Continue"}</button>` : `<p class="waiting">Waiting for the host to continue…</p>`}`;
  }

  const rankings = [...game.players].sort((a, b) => (b.score || 0) - (a.score || 0));
  return `
    <div class="phase-heading final-heading"><p class="eyebrow">Experiment complete</p><h1>Final standing</h1><p>${escapeHtml(GAMES[game.gameId].score)}</p></div>
    <ol class="rankings">${rankings.map((player, index) => `<li class="${player.id === game.viewerId ? "is-you" : ""}"><span class="rank">${String(index + 1).padStart(2, "0")}</span><strong>${escapeHtml(player.name)}${player.id === game.viewerId ? " · YOU" : ""}</strong><span>${player.score} pts</span></li>`).join("")}</ol>
    <button id="leave-finished" class="secondary wide">Choose another game</button>`;
}

function liveGuide(gameId: GameId, game: GameState, me: PlayerState): string {
  const hints: Record<GameId, string> = {
    vault: "Locking protects wealth; liquidity lets you react. Watch the room meter before committing.",
    burden: "Protected wealth is safer but decays. Exposed wealth follows the room’s shared pressure.",
    chain: "Every pass banks value, but rupture risk grows. Refusing is safer when your tokens remain.",
    insurance: "The room creates the threat together. Protection lowers risk; profit and sabotage raise it.",
    reputation: "Spending reputation buys influence now. Conserving it keeps your final voting power strong."
  };
  const values = Object.values(me.stats).map(Number).filter(Number.isFinite);
  const intensity = Math.min(100, Math.max(12, Math.round((values[0] || 0) % 100)));
  return `<section class="live-guide" aria-label="Live round guidance"><div class="live-guide-head"><span class="eyebrow">Live decision guide</span><span class="live-pulse"><i></i> ROOM UPDATING</span></div><div class="live-flow"><span class="flow-step active">1<br><small>Choose</small></span><b>→</b><span class="flow-step">2<br><small>Seal</small></span><b>→</b><span class="flow-step">3<br><small>Reveal</small></span></div><p>${hints[gameId]}</p><div class="room-meter"><span>Pressure</span><div><i style="width:${intensity}%"></i></div><strong>${game.players.filter((p) => p.acted).length}/${game.players.length}</strong></div></section>`;
}

function targetOptions(game: GameState): string {
  return game.players.filter((p) => p.id !== game.viewerId).map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join("");
}

function radioChoice(name: string, value: string, title: string, text: string, disabled = false): string {
  return `<label class="choice action-choice ${disabled ? "disabled" : ""}"><input type="radio" name="${name}" value="${value}" ${disabled ? "disabled" : ""} required/><span><strong>${title}</strong><small>${text}</small></span></label>`;
}

function renderActionForm(game: GameState, me: PlayerState): string {
  const s = me.stats;
  if (game.gameId === "vault") return `
    <form id="action-form" class="decision-card"><div class="decision-title"><div><p class="eyebrow">Private decision</p><h2>How much will you lock?</h2></div><output id="deposit-output">0</output></div>
    <input id="deposit" name="deposit" class="range" type="range" min="0" max="${readNumber(s, "liquid")}" value="0"/><div class="range-labels"><span>Keep liquid</span><span>Lock all ${readNumber(s, "liquid")}</span></div>
    <div class="option-grid"><label class="choice"><input name="useKey" type="checkbox" ${readNumber(s, "keys") ? "" : "disabled"}/><span><strong>Use a key</strong><small>Withdraw 20% from the vault first.</small></span></label><label class="choice"><input name="useSeal" type="checkbox" ${readNumber(s, "seals") ? "" : "disabled"}/><span><strong>Use emergency seal</strong><small>Cap liquid loss at 5% this round.</small></span></label></div>${submitButton()}</form>`;

  if (game.gameId === "burden") return `
    <form id="action-form" class="decision-card"><p class="eyebrow">Allocate exactly ${readNumber(s, "wealth")} wealth</p><h2>No part of your wealth is completely safe.</h2>
    <div class="allocation-grid"><label>Protected<input name="protected" type="number" min="0" max="${readNumber(s, "wealth")}" value="${readNumber(s, "wealth")}" required/><small>Always decays 3%</small></label><label>Exposed<input name="exposed" type="number" min="0" max="${readNumber(s, "wealth")}" value="0" required/><small>Shared risk, larger upside</small></label><label>Transfer<input name="transferred" type="number" min="0" max="${readNumber(s, "wealth")}" value="0" required/><small>Permanent support</small></label></div>
    <div id="allocation-status" class="allocation-status ready">Allocated ${readNumber(s, "wealth")} of ${readNumber(s, "wealth")} · Ready</div>
    <label class="select-label">Transfer recipient<select name="target"><option value="">No recipient</option>${targetOptions(game)}</select></label><label class="choice inline-choice"><input name="useSeal" type="checkbox" ${readNumber(s, "seals") ? "" : "disabled"}/><span><strong>Use protection seal</strong><small>Exposed wealth cannot fall below 70%.</small></span></label>${submitButton()}</form>`;

  if (game.gameId === "chain") return `<form id="action-form" class="decision-card"><p class="eyebrow">Choose your relationship to the Charge</p><h2>How much danger will you own?</h2><div class="action-grid">
    ${radioChoice("stance", "carry", "Carry", "Highest upside; rupture loses unsecured and 25% secured.")}${radioChoice("stance", "pass", "Pass", "Secure 70% of this chain’s growth; lose 5% on rupture.")}${radioChoice("stance", "refuse", "Refuse", "Spend a refusal token to avoid the Charge.", readNumber(s, "refusals") < 1)}${radioChoice("stance", "redirect", "Redirect", "Keep 80% of pass value and remain lightly exposed.")}${radioChoice("stance", "bank", "Break the chain", "Secure 50% now and take a Breaker Mark.")}</div>${submitButton()}</form>`;

  if (game.gameId === "insurance") return `<form id="action-form" class="decision-card"><p class="eyebrow">One hidden market action</p><h2>Protection, profit, or sabotage?</h2><div class="action-grid">
    ${radioChoice("choice", "strengthen", "Strengthen market · 8", "Lower shared threat and gain reliability.", readNumber(s, "liquid") < 8)}${radioChoice("choice", "extract", "Extract profit · +15", "Gain liquid wealth, raise risk, and weaken assets.")}${radioChoice("choice", "buy", "Buy policy · 8", "Reduce asset loss if the forecast materializes.", readNumber(s, "liquid") < 8)}${radioChoice("choice", "underwrite", "Underwrite · +12", "Collect premium and accept 20 in obligations.")}${radioChoice("choice", "sabotage", "Sabotage · +10", "Raise threat sharply and lose reliability.")}</div>${submitButton()}</form>`;

  return `<form id="action-form" class="decision-card"><p class="eyebrow">Spend reputation deliberately</p><h2>What identity will the room remember?</h2><div class="action-grid">
    ${radioChoice("choice", "ambition", "Pursue ambition · 10", "Complete one private ambition.", readNumber(s, "reputation") < 10)}${radioChoice("choice", "protect", "Keep promise · 6", "Record a kept public promise.", readNumber(s, "reputation") < 6)}${radioChoice("choice", "support", "Support player · 6", "Vote to give the shared pool to another player.", readNumber(s, "reputation") < 6)}${radioChoice("choice", "challenge", "Challenge player · 8", "Reduce a rival’s reputation by 5.", readNumber(s, "reputation") < 8)}${radioChoice("choice", "conserve", "Stay silent", "Gain 4 reputation but no public identity progress.")}</div><label class="select-label">Target for support or challenge<select name="target"><option value="">Choose when needed</option>${targetOptions(game)}</select></label>${submitButton()}</form>`;
}

function submitButton(): string { return `<button class="primary wide" ${busy ? "disabled" : ""}>${busy ? "Sealing…" : "Seal decision"}</button><p class="fine-print">This choice cannot be changed after submission.</p>`; }

function renderStats(gameId: GameId, me: PlayerState): string {
  const labels = STAT_LABELS[gameId];
  return `<section class="portfolio"><div class="section-label"><span>Your state</span><span>Private view</span></div><div class="stat-grid">${Object.entries(me.stats).map(([key, value]) => `<div><span>${escapeHtml(labels[key] || key)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}</div></section>`;
}

function renderPlayers(game: GameState): string {
  const labels = STAT_LABELS[game.gameId];
  return `<section class="players"><div class="section-label"><span>Players</span><span>${game.players.length} online</span></div><ul>${game.players.map((player) => {
    const visible = Object.entries(player.stats).slice(0, 2).map(([key, value]) => `${labels[key] || key} ${value}`).join(" · ");
    return `<li><span class="avatar">${escapeHtml(player.name.slice(0, 1).toUpperCase())}</span><span class="player-name"><strong>${escapeHtml(player.name)}</strong><small>${player.id === game.hostId ? "Host · " : ""}${escapeHtml(visible)}</small></span>${game.phase === "decision" ? `<span class="status-dot ${player.acted ? "acted" : ""}"></span>` : ""}</li>`;
  }).join("")}</ul></section>`;
}

function collectAction(game: GameState, data: FormData): Record<string, unknown> {
  if (game.gameId === "vault") return { deposit: Number(data.get("deposit")), useKey: data.get("useKey") === "on", useSeal: data.get("useSeal") === "on" };
  if (game.gameId === "burden") return { protected: Number(data.get("protected")), exposed: Number(data.get("exposed")), transferred: Number(data.get("transferred")), target: data.get("target"), useSeal: data.get("useSeal") === "on" };
  if (game.gameId === "chain") return { stance: data.get("stance") };
  return { choice: data.get("choice"), target: data.get("target") };
}

function bindGameEvents(game: GameState, _me: PlayerState): void {
  document.querySelector("#copy-code")?.addEventListener("click", () => void copyInvite(game.code));
  const leave = (): void => { saveSession(null); state = null; selectedGame = null; showRules = false; message = ""; location.hash = ""; render(); };
  document.querySelector("#leave")?.addEventListener("click", leave);
  document.querySelector("#leave-finished")?.addEventListener("click", leave);
  document.querySelector("#rules")?.addEventListener("click", () => { showRules = true; render(); });
  document.querySelector("#close-rules")?.addEventListener("click", () => { showRules = false; render(); });
  document.querySelector("#start-game")?.addEventListener("click", () => void postState("start"));
  document.querySelector("#force-resolve")?.addEventListener("click", () => void postState("resolve"));
  document.querySelector("#next-round")?.addEventListener("click", () => void postState("next"));
  const deposit = document.querySelector<HTMLInputElement>("#deposit");
  deposit?.addEventListener("input", () => { const output = document.querySelector<HTMLOutputElement>("#deposit-output"); if (output) output.value = deposit.value; });
  const allocationInputs = document.querySelectorAll<HTMLInputElement>(".allocation-grid input");
  allocationInputs.forEach((input) => input.addEventListener("input", () => {
    const total = Array.from(allocationInputs).reduce((sum, item) => sum + Number(item.value || 0), 0);
    const wealth = readNumber(_me.stats, "wealth");
    const status = document.querySelector<HTMLElement>("#allocation-status");
    if (status) {
      status.textContent = total === wealth ? `Allocated ${total} of ${wealth} · Ready` : `Allocated ${total} of ${wealth} · ${total < wealth ? `${wealth - total} remaining` : `${total - wealth} over`}`;
      status.classList.toggle("ready", total === wealth);
    }
  }));
  document.querySelector<HTMLFormElement>("#action-form")?.addEventListener("submit", (event) => {
    event.preventDefault(); const data = new FormData(event.currentTarget as HTMLFormElement);
    void withBusy(async () => { state = await api<GameState>(`/api/rooms/${game.code}/actions`, { method: "POST", body: JSON.stringify({ playerId: game.viewerId, values: collectAction(game, data), idempotencyKey: crypto.randomUUID() }) }); });
  });
}

async function copyInvite(code: string): Promise<void> {
  const link = `${location.origin}/#${code}`;
  try {
    if (!navigator.clipboard) throw new Error("Clipboard unavailable");
    await navigator.clipboard.writeText(link);
    message = "Invite link copied.";
  } catch {
    message = `Invite code: ${code}`;
  }
  render();
}

async function postState(action: "start" | "resolve" | "next"): Promise<void> {
  if (!session) return;
  await withBusy(async () => { state = await api<GameState>(`/api/rooms/${session!.code}/${action}`, { method: "POST", body: JSON.stringify({ playerId: session!.playerId }) }); });
}

async function boot(): Promise<void> {
  app.innerHTML = `<div class="boot-screen"><span class="brand-mark">P</span><p>Preparing the room…</p></div>`;
  try {
    await api<{ status: string }>("/api/health");
    serverStatus = "online";
  } catch {
    serverStatus = "offline";
    message = "FastAPI is not reachable. Run: python -m backend.server";
  }
  render(); if (session && serverStatus === "online") await refresh();
  window.clearInterval(pollTimer);
  connectRoomSocket();
  pollTimer = window.setInterval(() => { if (!roomSocket || roomSocket.readyState !== WebSocket.OPEN) void refresh(true); }, 5000);
}

void boot();
