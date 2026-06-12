# PokéTactics Alpha Tester Guide

Welcome to the PokéTactics alpha. This is an early browser-based tactical RPG inspired by Advance Wars and Pokémon battles. Things will break — that's why you're here.

---

## What to test

Focus feedback on:

- **Creating and joining games** (Conquest, War, Capture the Flag)
- **Unit placement** during the preparation phase
- **Movement, combat, and turn flow** during active games
- **Real-time updates** (other players' actions appearing without refresh)
- **In-game chat**
- **Crashes, soft-locks, or rules that feel wrong**

---

## Getting started

### 1. Create an account

1. Open the alpha site (your host will provide the URL).
2. Click **Login** in the navbar, then **Register**.
3. Pick a username and password. Stay logged in — sessions last 24 hours by default.

> The site requires **HTTPS**. If you can't stay logged in, tell the host — cookie settings require a secure connection.

### 2. Create a game

1. Go to **Create Game** from the navbar.
2. Choose a **game mode**, **map**, player count, and turn timer.
3. Submit the form. You'll receive a **game link** — share it with your opponent(s).

### 3. Join a game

1. Go to **Join Game**.
2. Paste the game link your host or opponent shared.
3. Wait in the lobby until all players join, then mark yourself **Ready**.

### 4. Play

1. **Preparation:** spend starting cash to place units on your side of the map.
2. **In progress:** move units, use moves, and end your turn before the timer runs out.
3. **Completed games** appear under **Completed Games** in the navbar.

---

## Game modes (short)

| Mode | Goal |
|------|------|
| **Conquest** | Capture objectives and outlast opponents |
| **War** | Eliminate enemy forces |
| **Capture the Flag** | Bring the flag to your base |

Only **4 official maps** are available in alpha — you'll see the same ones often.

---

## Known limitations

Please **don't** file bugs for these — they're planned or unfinished:

- **Abilities** — battle code exists, but no Pokémon have abilities yet
- **Friends / tournaments** — not implemented
- **ELO / ranked matchmaking** — not active
- **Replay viewer** — game logs exist server-side, but there's no replay UI
- **Homepage** — placeholder only; use the navbar to navigate
- **Small map pool** — only 4 maps in this build

---

## How to report bugs

Include as much of this as you can:

1. **What you were trying to do**
2. **What happened instead**
3. **Game link** (if in a match)
4. **Browser** (Chrome, Firefox, Safari, version)
5. **Screenshot or screen recording** if possible
6. **Steps to reproduce**

Send reports via the channel your host provides (GitHub Issues, Discord, etc.).

### Good bug report example

> I joined a 2-player Conquest game on Grassy Field. During my turn I selected Pikachu, chose Thunderbolt on a adjacent foe, and clicked Execute. The UI showed "Move failed" with no other message. Browser: Firefox 128. Game link: `abc123`. Happened twice in a row.

### Low-priority / out of scope for alpha

- Cosmetic polish, missing animations, placeholder homepage text
- Features listed under **Known limitations** above
- Balance opinions (useful, but secondary to crashes and broken rules)

---

## Rules of conduct

- Be respectful in chat — moderation tools are active (warn, mute, ban).
- Don't share other players' personal info.
- Don't attempt to cheat, impersonate other accounts, or probe the infrastructure.

---

## Troubleshooting

| Problem | Try this |
|---------|----------|
| Can't stay logged in | Confirm you're on `https://` not `http://`; clear cookies and log in again |
| Can't create a game | Make sure you're logged in first |
| Game board doesn't update | Refresh once; if it persists, note the game link in your report |
| WebSocket won't connect | You must be **logged in** and **joined to that game** to receive live updates |
| Opponent's turn never ends | Turn timers auto-advance — wait for the deadline or report if stuck |

---

## For hosts deploying this alpha

Before inviting testers, confirm:

- `SESSION_SECRET` is a long random value (not the example placeholder)
- `BOOTSTRAP_ADMIN_PASSWORD` is at least 12 characters and not a common default
- Production Docker Compose does **not** expose Postgres, Redis, or pgAdmin ports
- HTTPS is configured with matching `CORS_ORIGIN` and `COOKIE_DOMAIN`
- CI is green on the deployed commit

Thank you for helping shape PokéTactics.
