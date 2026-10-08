# Obsidian vault package — staging area, not part of the trading codebase

This folder is **not** part of the Trading Intelligence AI system. It's a
prepared package of vault content, built by Trading Codex (cloud) because
this cloud session has no Computer Use, no filesystem access to the
owner's PC, no Obsidian connector, and no browser extension — verified by
searching this session's actual tool list, not assumed. Per the owner's
own fallback instruction, everything is prepared here instead of asking
for manual steps.

**Task for Claude Code local — do this, then delete this folder:**

1. **Find the real vault.** Obsidian is already open on the owner's PC.
   The currently-open vault's path is recorded at
   `%APPDATA%\Obsidian\obsidian.json` (a JSON map of vault IDs to paths,
   with an `open` flag) — read that file rather than guessing a path. If
   more than one vault is open, pick the one that looks like the owner's
   main/general vault (it will NOT be `C:\Users\tatop\trading-ai` itself;
   this package assumes a separate personal vault, since the folder
   taxonomy below — "01 Projects" plural, "99 Inbox" — is a general PKM
   structure, not trading-specific). If genuinely ambiguous, that's the
   one case worth a single clarifying note back through the normal
   checkpoint/coordination channel — don't guess silently on something
   this structural.
2. **Create the folder taxonomy** at the vault root if these don't already
   exist (check for near-matches first — e.g. an existing "Projects"
   folder without the number prefix — and ask via checkpoint rather than
   creating a duplicate structure):
   `00 Home`, `01 Projects`, `02 Agents`, `03 Architecture`, `04 Research`,
   `05 Strategies`, `06 Decisions`, `07 Experiments`, `08 Runbooks`,
   `09 Checkpoints`, `10 Postmortems`, `11 Dashboards`, `12 Templates`,
   `99 Inbox`. Only `00 Home`, `01 Projects`, `02 Agents`, `09 Checkpoints`,
   and `11 Dashboards` have real content below; create the rest empty —
   they're namespace reserved for later work, not content to invent now.
3. **Copy each file below into the matching numbered folder**, preserving
   filenames exactly (Obsidian wikilinks in these notes assume that).
4. **Fix the repo-path links.** Every note below that references this
   git repo uses a GitHub URL (works regardless of vault location). If
   the vault is configured to also include a local clone of this repo as
   a linked/mounted folder, you may additionally add a local wikilink —
   but keep the GitHub URL too, since GitHub remains the source of truth
   per `AGENTS.md` and the vault must never become a second one.
5. **Report back** via the usual checkpoint/coordination channel once
   placed: what vault path was used, and confirmation the five populated
   folders now exist with their files. Don't report this as "Obsidian
   integration complete" — it's the vault structure and first content
   existing, not a sync mechanism; nothing here auto-updates, so treat
   each note as a snapshot to be manually refreshed later, same as
   Agent City V1.

**Why no content for the other 9 folders**: the owner asked for the
taxonomy and *specific* named notes (Home, Trading Intelligence, agent
notes, Current Checkpoint, Trading Dashboard, Agent City, Agent
City.canvas) — all of which are covered below. Inventing filler content
for Architecture/Research/Strategies/etc. right now would be exactly the
"invented activity" this project's own rules forbid; those folders exist
as destinations for real future work (e.g. `docs/SYSTEM_ARCHITECTURE.md`
could later be mirrored into `03 Architecture` when someone actually
does that), not as something to backfill today.
