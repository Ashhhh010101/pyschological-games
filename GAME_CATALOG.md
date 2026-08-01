# Extracted Game Catalog

This document reorganizes the game information from `Psychology_Loss_Aversion_Games.md` into implementation-oriented specifications. It does not replace the source; it makes the rules, state, loop, scoring, and unresolved design questions easier to use.

## Shared product foundation

All five concepts are short, room-based multiplayer games built around loss aversion. The intended production stack is Next.js with TypeScript and Tailwind CSS, deployed on Vercel, with Vercel Postgres, Neon, or Supabase for persistence and Supabase Realtime, Ably, or Pusher for live updates. Players use automatically generated anonymous identities.

The common session parameters are:

- 3–10 players per room.
- 5–12 minutes per session.
- A simple interface based on cards, numbers, timers, and lightweight animation.
- A server-authoritative model: random events, balances, outcomes, and scores are calculated on the server.
- The browser sends intentions, never trusted balances or calculated results.

The shared server flow is:

```text
Lobby → Ready → Start round → Secret actions → Lock actions
      → Resolve → Broadcast → Save replay → Next round → Final score
```

The production multiplayer requirements are one action per phase, transactional updates, idempotency keys, server timestamps, reconnect support, safe AFK actions, room cleanup, rate limiting, and input sanitization. The minimal shared data model names four entities: rooms, players, actions, and events.

## 1. The Burden

### Player experience and objective

The Burden makes every allocation feel unsafe. Wealth left exposed can be hit immediately, protected wealth decays, and refusing to choose is itself consequential. The winner is the player with the greatest surviving wealth after six rounds.

### Initial player state

| Resource | Starting value | Purpose |
|---|---:|---|
| Wealth | 100 | Allocated every round and used in final scoring |
| Protection seals | 3 | Limit severe losses to exposed wealth |
| Burden | 0 | Named state in the source; its accumulation/effect still needs specification |

### Round loop

Each round lasts approximately 25 seconds.

1. A shared burden condition is revealed: Stability, Expansion, Panic, Corrosion, or Exposure.
2. Each player secretly divides current wealth among Protected, Exposed, and Transferred allocations. The three values must add up to current wealth.
3. The server aggregates total room exposure and derives a shared pressure band.
4. The server resolves protected decay, exposed growth/loss, transfers, seals, and any collapse effects.

Protected wealth always loses 3%. Exposed wealth follows hidden thresholds:

| Room exposure | Exposed outcome |
|---|---|
| 0–30% | +4% |
| 31–60% | +18% |
| 61–80% | 50% chance of +35%; 50% chance of −25% |
| 81–100% | 70% chance of −45%; the remaining outcome is not defined in the source |

Thresholds are deliberately hidden from players. Spending a protection seal prevents exposed wealth from falling below 70% of its pre-resolution amount. Transferred wealth permanently becomes the recipient’s property; transfer identities become public after resolution.

### Failure recovery and score

Players are never eliminated. A player reaching zero receives 15 emergency wealth and a Debt Scar. Each Debt Scar reduces final score by 12%; whether this means 12 points or 12% of score needs to be fixed before production.

Final score consists of remaining wealth, minus debt penalties, plus 5 points for every player the scorer supported before a collapse. “Supported” and the collapse window need formal event definitions.

## 2. Chain of Responsibility

### Player experience and objective

A shared Charge becomes more valuable and more dangerous the longer somebody holds it. Players try to secure the most value while avoiding possession at the moment of rupture.

### Initial player state

The source formatting is compressed; the intended values appear to be:

- 20 secured points.
- 0 unsecured points.
- 2 refusal tokens.
- 1 private risk clue.

### Chain loop

While held, the Charge generates unsecured value every second in an increasing sequence (`1, 2, 3, ...`). Rupture probability rises alongside value. A holder can pass the Charge. The proposed receiver may accept, spend a refusal token, or redirect it while losing 20%. On a successful pass, the previous holder banks 70% of their unsecured amount.

On rupture:

- The current holder loses all unsecured value.
- The holder also loses 25% of secured value.
- Previous passers lose 5%; the source does not specify whether this is secured value or another base.
- The last player who voluntarily received the Charge earns a Courage Mark.

Each player gets private, approximate risk clues, some of which may be false. Players can communicate or bluff about these clues. Instead of passing, the holder can bank/destroy the Charge: they secure 50%, end that chain, and gain a Breaker Mark.

### End and score

The game ends after five ruptures or eight completed chains. Final score is secured value plus Courage Mark value minus Breaker penalties. The point value of marks and penalties remains unspecified.

## 3. Insurance Market

### Player experience and objective

Players protect assets against danger that is partly created by the room itself. Selling insurance produces premium income but creates correlated liabilities. The winner has the greatest asset value after five market cycles.

### Assets and threats

Assets have three categories: Productive, Defensive, and Social. At the start of each cycle the market forecasts Liquidity Failure, Structural Damage, or Reputation Shock.

### Policy model

Players create policies for one another. A policy contains:

- Premium paid for protection.
- Coverage, identifying the protected loss or asset.
- Maximum payout.
- Deductible retained by the insured player.

### Cycle loop

1. Reveal the market forecast.
2. Open a 45-second negotiation window.
3. Players offer, buy, or sell insurance and choose hidden actions.
4. Hidden actions may Strengthen Market, Extract Profit, Redirect Risk, Investigate, Sabotage, or transact insurance.
5. The server derives threat probability from collective behavior and resolves the event.
6. Valid claims are paid automatically.
7. Insolvent insurers suffer reputation collapse, policy cancellation, and asset devaluation.

A single disaster can trigger correlated claims and cascade through multiple insurers.

### Reputation and score

Reputation progresses through Stable, Questionable, Fragile, and Defaulted. Final score combines asset value, liquid wealth, and premiums, then subtracts unpaid obligations and adds a reliability bonus. Exact asset values, action effects, reputation thresholds, and bonus values remain to be designed.

## 4. Reputation Economy

### Player experience and objective

Reputation simultaneously represents identity, purchasing power, influence, and access. Players pursue private goals while trying to preserve enough reputation to influence the final crisis.

### Initial player state

- 60 reputation.
- 2 private ambitions.
- 1 public promise.

### Actions and redistribution

Players spend reputation to Propose, Vote, Protect, Reveal Evidence, Challenge, Block, Guarantee, or Request Support. Spent reputation enters a shared pool and is redistributed through player voting.

Public promises create visible commitments. Keeping one restores reputation; breaking one creates permanent trust damage. Players may also lend reputation. If a borrower fails, voting privilege transfers to the lender; duration and scope need specification.

Behavior produces identity labels such as Protector, Reliable, Opportunist, Silent, and Dependent. During the final crisis, remaining reputation directly determines voting strength.

### Score

The score awards 30 points per completed ambition, 1 point per 2 reputation, 5 per kept promise, subtracts 8 per broken promise, and awards 20 points for alignment with the final outcome.

## 5. The Vault

### Player experience and objective

Players decide whether to lock wealth for safety or preserve liquidity for flexibility and opportunity. Collective over-locking causes scarcity; collective under-locking causes exposure. The objective is to achieve the highest final vault-oriented score while surviving room events.

### Initial player state

| Resource | Starting value | Purpose |
|---|---:|---|
| Liquid wealth | 100 | Can respond to opportunities but is exposed to events |
| Vault wealth | 0 | Normally cannot be withdrawn and may resist some events |
| Keys | 2 | Withdraw 20%, hide deposits, or seal another vault |
| Emergency seal | 1 | Protect liquid wealth before an event is revealed |

### Information model

A player sees their own exact values, every other player’s liquid wealth, approximate ranges for other vaults, and approximate room liquidity. The source’s event list is Flood, Opportunity, Tax, Audit, Rescue, and Fracture.

Keys can be traded and may be spent to withdraw 20%, hide deposits, or seal another vault. Vault deposits are otherwise irreversible. Before event reveal, a player may spend their one emergency seal to protect liquid wealth.

A Rescue event can trigger a room vote with four possible outcomes: everyone unlocks, the richest player unlocks, a volunteer unlocks, or the room accepts permanent damage.

The endgame reveals an event category but not its exact event. Named possessions—Founder’s Signature, First Reserve, Shared Promise, Unbroken Key, and Protected Memory—provide emotionally salient ownership; their acquisition and mechanical effects remain unspecified.

### Score

Final score is vault wealth plus 50% of liquid wealth, plus 3 points per remaining key, minus collapse penalties, plus rescue bonuses.

## Recommended development order

1. The Vault
2. Chain of Responsibility
3. The Burden
4. Reputation Economy
5. Insurance Market

The order moves from a relatively compact allocation/event loop toward systems with real-time passing, negotiation, long-lived obligations, and larger rule-definition gaps.

