# Psychology-Based Multiplayer Games (Loss Aversion)

## Shared Technical Foundation

-   Frontend: Next.js + TypeScript + Tailwind CSS
-   Deployment: Vercel
-   Database: Vercel Postgres, Neon, or Supabase
-   Realtime: Supabase Realtime, Ably, or Pusher
-   Authentication: Anonymous generated player identity
-   Players: 3--10 per room
-   Session length: 5--12 minutes
-   Interface: Cards, numbers, timers, simple animations
-   Server authority: All calculations and random events happen
    server-side

Never trust balances or action results submitted by the browser.

------------------------------------------------------------------------

# 1. The Burden

## Psychological foundation

The player owns wealth that is constantly threatened: - Risking it can
cause immediate loss. - Protecting it causes gradual decay. - Doing
nothing is still a decision.

There is deliberately **no completely safe choice**.

## Player objective

Finish six rounds with the greatest surviving wealth.

## Starting state

-   100 wealth
-   3 protection seals
-   0 burden

## Round structure

Each round lasts \~25 seconds.

### Phase 1: Burden revealed

Shared conditions: - Stability - Expansion - Panic - Corrosion -
Exposure

### Phase 2: Secret allocation

Split wealth into: - Protected - Exposed - Transferred

Example:

``` text
Current wealth:120
Protected:50
Exposed:60
Transferred:10
```

### Phase 3: Collective pressure

Room exposure determines stability/growth/collapse.

### Phase 4: Resolution

``` text
Protected loses 3%.

Exposed:
0–30% room exposure:+4%
31–60%:+18%
61–80%:50% +35%, 50% -25%
81–100%:70% chance -45%
```

Thresholds remain hidden.

## Protection seals

One seal prevents exposed wealth from falling below 70%.

## Transfer mechanic

Transferred wealth permanently belongs to the receiver. Transfer
identities reveal after resolution.

## Elimination

No elimination. Zero wealth → emergency 15 wealth + Debt Scar. Each Debt
Scar = −12% final score.

## Winning score

``` text
remaining wealth
− debt penalties
+5 for each player you supported before collapse
```

------------------------------------------------------------------------

# 2. Chain of Responsibility

## Psychological foundation

A valuable object becomes increasingly profitable and increasingly
dangerous.

## Objective

Most secured value without holding the Charge during rupture.

## Starting state

-20 secured points -0 unsecured -2 refusal tokens -1 private risk clue

## Main loop

Charge generates unsecured value every second:

``` text
1
2
3
...
```

Growth and rupture risk both increase.

## Passing

Receiver may: - Accept - Refuse (token) - Redirect (lose 20%)

Previous holder secures only 70%.

## Rupture

-   Holder loses unsecured value
-   Holder loses 25% secured
-   Previous passers lose 5%
-   Last voluntary receiver gains Courage Mark

## Private clues

Approximate or sometimes false risk hints. Players may bluff.

## Banking

Destroy Charge: - Secure 50% - End chain - Gain Breaker Mark

## End

5 ruptures or 8 chains.

## Final score

``` text
secured value
+courage marks
-breaker penalties
```

------------------------------------------------------------------------

# 3. Insurance Market

## Psychological foundation

Protection costs money while danger comes from other players.

## Objective

Highest asset value after five cycles.

## Assets

-   Productive
-   Defensive
-   Social

## Market cycle

### Forecast

Possible threats: - Liquidity failure - Structural damage - Reputation
shock

### Insurance

Players create policies for each other.

Policy: - Premium - Coverage - Maximum payout - Deductible

### Hidden actions

Examples: - Strengthen market - Extract profit - Redirect risk -
Investigate - Sabotage - Buy/sell insurance

### Negotiation

45 seconds.

### Resolution

Threat probability depends on collective behavior.

### Claims

Insurers pay automatically.

If insolvent: - Reputation collapse - Policies cancelled - Assets
devalue

## Correlated losses

One disaster can cascade across insurers.

## Reputation

Stable Questionable Fragile Defaulted

## Final score

``` text
asset value
+liquid wealth
+premiums
-unpaid obligations
+reliability bonus
```

------------------------------------------------------------------------

# 4. Reputation Economy

## Psychological foundation

Reputation is identity, currency, influence and access.

## Objective

Complete personal goals while preserving reputation.

## Starting state

-60 reputation -2 private ambitions -1 public promise

## Actions

Spend reputation to: - Propose - Vote - Protect - Reveal evidence -
Challenge - Block - Guarantee - Request support

## Shared pool

Spent reputation redistributes through player voting.

## Public promises

Keeping promises restores reputation. Breaking them creates permanent
trust damage.

## Borrowing

Players may lend reputation. Failure transfers voting privilege.

## Identity labels

Examples: - Protector - Reliable - Opportunist - Silent - Dependent

## Final crisis

Voting strength equals remaining reputation.

## Scoring

``` text
30 per ambition
1 point /2 reputation
+5 kept promises
-8 broken promises
+20 outcome alignment
```

------------------------------------------------------------------------

# 5. The Vault

## Psychological foundation

Lock wealth for safety or keep it liquid for opportunity.

## Objective

Highest vault value while surviving room events.

## Starting state

-100 liquid -empty vault -2 keys -1 emergency seal

## Locking

Vault deposits normally cannot be withdrawn.

## Collective liquidity

Too much locking causes scarcity. Too little locking causes exposure.

## Events

-   Flood
-   Opportunity
-   Tax
-   Audit
-   Rescue
-   Fracture

## Keys

Allow: - Withdraw 20% - Hide deposits - Seal another vault

Keys may be traded.

## Emergency seal

Protects liquid wealth before event reveal.

## Rescue vote

Possible outcomes: - Everyone unlocks - Richest unlock - Volunteer
unlocks - Accept permanent damage

## Information

Visible: - Your exact values - Others' liquid - Approximate vault
ranges - Approximate room liquidity

## Endgame

Known event category, unknown exact event.

## Final score

``` text
vault wealth
+50% liquid
+keys×3
-collapse penalties
+rescue bonuses
```

### Named possessions

Examples: - Founder's Signature - First Reserve - Shared Promise -
Unbroken Key - Protected Memory

------------------------------------------------------------------------

# Development Order

1.  The Vault
2.  Chain of Responsibility
3.  The Burden
4.  Reputation Economy
5.  Insurance Market

------------------------------------------------------------------------

# Database Schema

``` text
rooms
players
actions
events
```

## Server Flow

``` text
Lobby
→ Ready
→ Start round
→ Secret actions
→ Lock
→ Resolve
→ Broadcast
→ Save replay
→ Next round
→ Final scoring
```

## Multiplayer Protections

-   One action per phase
-   Database transactions
-   Idempotency keys
-   Server timestamps
-   Reconnection support
-   AFK safe actions
-   Room cleanup
-   Rate limiting
-   Input sanitization
