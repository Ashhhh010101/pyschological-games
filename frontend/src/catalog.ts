import type { GameGuide, GameId } from "./types.js";

export const GAMES: Record<GameId, GameGuide> = {
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

export const STAT_LABELS: Record<GameId, Record<string, string>> = {
  vault: { liquid: "Liquid", vault: "Vault", vaultRange: "Vault range", keys: "Keys", seals: "Seals", penalties: "Penalties", rescueBonus: "Rescue bonus" },
  burden: { wealth: "Wealth", seals: "Seals", debtScars: "Debt Scars", supportBonus: "Support" },
  chain: { secured: "Secured", unsecured: "Unsecured", refusals: "Refusals", courage: "Courage", breaker: "Breaker" },
  insurance: { assets: "Assets", liquid: "Liquid", premiums: "Premiums", obligations: "Obligations", reliability: "Reliability" },
  reputation: { reputation: "Reputation", ambitions: "Ambitions", keptPromises: "Promises kept", brokenPromises: "Promises broken", alignment: "Alignment" },
};
