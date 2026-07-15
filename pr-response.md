# PR Response Doc — CineLog Watchlist Feature

## AI Usage
I used an AI assistant (Claude) in four specific ways on this project.

**1. Codebase orientation (before reading the review).** I had it summarize
`models.py`, `services/collection_service.py`, and `tests/test_collection.py` and
walk me through what `add_to_collection()` does step by step — specifically what
it returns when a `film_id` doesn't exist. That surfaced the project's
`verb_to_noun` naming convention, its custom exceptions (`FilmNotFoundError`,
`AlreadyInCollectionError`), and its duplicate check via `filter_by(...).first()`
before insert. I verified each claim against the code rather than trusting the
summary — which mattered, because an early AI reading implied `WatchlistEntry` had
a `.film` relationship like `CollectionEntry` does. It doesn't, and that turned out
to be a real bug (see the note below).

**2. Stress-testing my design arguments (Comments 4 and 5).** I wrote my positions
first, then asked what counterargument a careful reviewer would raise and which
tradeoff I hadn't acknowledged. For **Comment 4**, it pushed back on my
"a watchlist is low-sensitivity" claim — a watchlist can reveal sensitive
interests (health, identity, religion), and public-by-default exposes those
without opt-in. That was a fair hit. I didn't drop my position, but I narrowed the
claim and added the mitigation I actually believe in: "public by default, but never
silently" — an explicit toggle plus a `public` parameter, rather than a private
default that would gut the community feature. For **Comment 5**, it raised YAGNI
(a `?sort=` param is premature). I kept my position but added the rebuttal that I'm
preserving behavior the code already had rather than inventing new surface area.
The positions and reasoning are mine; the AI's job was to find the holes.

**3. Verifying commit format.** I gave it my `git log --oneline` output and asked
whether the messages followed conventional commit format and whether any commit
bundled multiple logical changes. It flagged messages that bundled a rename and a
dedup fix together — which is what prompted the history rewrite into the six
single-purpose commits shown below.

**4. What I did not use it for.** I didn't have it write the deduplication logic —
I read `add_to_collection()` and wrote my own version following that pattern. And I
didn't ask it to make the Comment 4 or Comment 5 decisions, only to attack them
after I'd written them.

**Something the AI orientation missed:** while adding the sort tests I hit
`AttributeError: 'WatchlistEntry' object has no attribute 'film'`. `get_watchlist()`
had always called `entry.film.to_dict()`, but — unlike `CollectionEntry` — no
`film` relationship is defined for `WatchlistEntry`, so the endpoint crashed on any
non-empty watchlist. It had never been caught because no test exercised it. I fixed
it by fetching the film with `db.session.get(Film, entry.film_id)`, consistent with
how `add_to_watchlist()` already looks films up. The tests caught this, not the AI.

## Comment 1 — Rename
**What I did:** Renamed `save_to_watchlist()` to `add_to_watchlist()` in
`services/watchlist_service.py` to match the project's `verb_to_noun` naming
convention (consistent with `add_to_collection()` in `collection_service.py`). I
also updated the function's docstring ("Save a film…" → "Add a film…") for
consistency, and updated the one call site in `routes/watchlist/watchlist.py` —
both the import on line 8 and the call on line 32.

**How I verified:** I ran a project-wide search (`grep -rn "save_to_watchlist"`)
before and after the change to find every reference. Before: three hits (the
definition plus the import and call in the route). After: zero hits for the old
name and three for `add_to_watchlist`. The full test suite still passes
(`pytest tests/ -v` → 4 passed), confirming the route still imports and calls the
service correctly.

## Comment 2 — Deduplication
**What I did:** Mirrored the deduplication pattern from `add_to_collection()`. I
added an `AlreadyInWatchlistError` exception to `watchlist_service.py` (parallel
to `AlreadyInCollectionError`), and in `add_to_watchlist()`, after confirming the
film exists, I query for an existing `WatchlistEntry` with the same `user_id` and
`film_id` — if one exists, I raise `AlreadyInWatchlistError` instead of inserting
a duplicate. I also updated `routes/watchlist/watchlist.py` to catch that error
and return **409 Conflict** (and `FilmNotFoundError` → **404**), so the endpoint
now behaves exactly like the collection endpoint rather than returning a 500.

I followed the service-level check rather than relying only on a DB unique
constraint because that's the pattern the collection service already uses, and it
lets the API return a clean, specific error message.

**How I verified:** I wrote a quick in-memory check: added a film, then added the
same film again. The first call succeeded; the second raised
`AlreadyInWatchlistError`; and a count query confirmed exactly **one** entry
persisted (no duplicate row). The full suite still passes (4 passed). Comment 3's
new test also exercises the same service path.

## Comment 3 — Missing test
**What I did:** Created `tests/test_watchlist.py` and wrote
`test_add_to_watchlist_nonexistent_film_raises`, modeled directly on
`test_add_to_collection_nonexistent_film_raises` in `test_collection.py`. I reused
the same fixture structure — an in-memory `app` fixture, a `sample_user` fixture
returning a committed user's id, and a `sample_film` fixture — then asserted that
calling `add_to_watchlist()` with a `film_id` that isn't in the database raises
`FilmNotFoundError` (via `pytest.raises`), rather than surfacing a raw database
error.

**How I verified:** `pytest tests/test_watchlist.py -v` passes the new test, and
`pytest tests/ -v` runs green across the whole suite (5 passed: 4 collection + 1
watchlist).

## Comment 4 — Default visibility
**My position:** Keep `public=True` as the default for new watchlist entries.

**Reasoning:** CineLog is explicitly a *community* film-tracking app, and a
watchlist is a "want to watch" signal — exactly the kind of low-stakes, forward-
looking data that a community is built to share. Unlike the collection (which
records what a user has actually watched and carries no visibility field at all),
a watchlist is aspirational, not a behavioral history. Defaulting it to public is
what makes the community loop work: discovery, following other users' tastes, and
"what are people planning to watch" all depend on lists being visible. Because
most users never change a default, a private-by-default watchlist would ship the
social features essentially empty and undercut the product's core purpose. The
model already treats visibility as a first-class field (`public` is stored and
returned by `to_dict()`), so the default only sets the starting point — it doesn't
lock anyone in.

**Tradeoff acknowledged:** The real cost is consent. A user may not expect their
want-to-watch list to be world-visible, and a watchlist *can* reveal sensitive
interests (films tied to health, identity, religion). Privacy-by-default is the
more conservative, consent-respecting posture, and I take that concern seriously.
I'm accepting the tradeoff because the mitigation isn't a private default (which
would gut the community feature) — it's making visibility **explicit and easy to
change**: an obvious per-list toggle in the UI and a `public` parameter on
`add_to_watchlist()` (see the visibility-toggle stretch) so callers can set it at
creation time. The principle is "public by default, but never silently" — surface
the setting clearly rather than hide lists away.

## Comment 5 — Sort order
**My position:** Make sort order configurable via a `?sort=` query param
(`recent` | `title`), defaulting to **`recent`** (date-added, newest first). This
adopts the reviewer's preferred default while keeping alphabetical available.

**Reasoning:** I agree with the reviewer's core point, so I made date-added the
default. For a *want-to-watch* list, recency usually maps to intent — people add
a film because they just heard about it, so "what did I add recently" is "what am
I interested in right now." It also makes the two list endpoints consistent:
`get_collection()` already sorts date-added descending, and the project clearly
values the watchlist mirroring the collection (that consistency was the whole
basis of the Comment 1 naming feedback). But a single fixed order isn't right for
every task: once a watchlist gets long and the user is scanning to *find* a
specific title, alphabetical is genuinely more useful. Rather than trade one use
case for the other, I exposed both via `get_watchlist(user_id, sort=...)` and
`?sort=` on the endpoint — `recent` by default, `title` on request.

**Engagement with reviewer's point:** The reviewer said "most users want to see
what they added recently," and I've made that the default, so we're aligned on the
common case — I'm not overriding them. My one refinement is that "most" isn't
"all": the browse-to-find case is real, and preserving alphabetical costs almost
nothing (it was the existing behavior; I kept it as an option and tested both
paths). So I treat the disagreement as a *secondary* option rather than the
default. The one counterargument I weighed is YAGNI — that a sort param is
premature until users ask. I think it's justified here because I'm not inventing
new surface area; I'm keeping capability the code already had while switching the
default to the one the reviewer (rightly) prefers.

## Comment 6 — Rebase
**What conflicted:** I ran `git fetch origin` and `git rebase origin/main`. My
branch had diverged from `main` back at the initial commit — *before* two things
that later landed on `main`: the integer→UUID film-ID refactor, and a `.gitignore`
that was merged into `main` separately. So two conflicts surfaced:
1. **`.gitignore` (add/add):** both `main` and my branch added a `.gitignore`.
2. **UUID mismatch in `models.py`:** `main`'s refactor changed `Film.id` and
   `CollectionEntry.film_id` from `db.Integer` to `db.String(36)` (UUID). My
   `WatchlistEntry.film_id` was still declared `db.Integer` with a foreign key to
   the now-UUID `film.id`, and the watchlist service/route still documented
   `film_id` as an int.

**How I resolved it:**
1. `.gitignore`: I kept `main`'s version, which is a superset of mine (it also
   ignores `.pytest_cache/`), so nothing my branch needed was lost.
2. UUID: I reconciled `WatchlistEntry` to the UUID scheme —
   `film_id = db.Column(db.String(36), db.ForeignKey("film.id"), nullable=False)`
   (was `db.Integer`) — keeping the rest of the model unchanged. I then updated
   the `int`→UUID references in `add_to_watchlist`'s docstring and the route's
   request-body docstring so the watchlist code consistently describes film IDs as
   UUIDs.

**How I verified no conflict remains:** `git status` is clean and the rebase
finished without further stops. `git log --merges origin/main..HEAD` returns
nothing (**no merge commits**), and `git merge-base --is-ancestor origin/main
HEAD` confirms my branch sits directly on top of `origin/main`. Functionally, the
full test suite passes (7 passed) with UUIDs throughout — including the watchlist
add, deduplication, nonexistent-film, and both sort paths — and a `grep` for
`Integer`/`<int>` in the watchlist code returns only the explanatory comment.

## Commit History

`git log --oneline` on `feature/watchlist` after the interactive history rewrite —
six conventional commits, one logical change each, **no merge commits**, all
rebased on top of `origin/main`:

```
dd1f7dc docs: add pr-response.md with review responses and design decisions
5b470ca test: add watchlist tests for nonexistent film and sort order
d3ba03f feat: add watchlist endpoints with 404 and 409 error handling
3acdb25 feat: add watchlist service with deduplication and configurable sort order
c55cd26 feat: add WatchlistEntry model with UUID film reference
93a98bc fix: replace deprecated Query.get with db.session.get in collection service
```

Verified with `git log --merges origin/main..HEAD` (empty — no merge commits) and
`git merge-base --is-ancestor origin/main HEAD` (branch sits directly on `main`).

*(Note: the `docs:` commit's own hash necessarily shifts each time this file is
re-committed, since the log is captured from inside the file it describes. The
five commits below it are final.)*

## PR Description

### What this feature does
Adds a **watchlist** to CineLog: films a user wants to watch, kept separate from
their collection (films already watched). It introduces:

- **`WatchlistEntry` model** — links a user to a film with a `date_added`
  timestamp and a `public` visibility flag. Film IDs are UUIDs, matching `main`'s
  ID refactor.
- **`add_to_watchlist(user_id, film_id)`** — validates the film exists
  (`FilmNotFoundError`), refuses duplicates (`AlreadyInWatchlistError`), and
  creates the entry. Follows the same shape as `add_to_collection()`.
- **`get_watchlist(user_id, sort="recent")`** — returns the user's watchlist,
  ordered by date added (newest first) by default, or alphabetically with
  `sort="title"`.
- **Endpoints** — `POST /watchlist/<user_id>/add` (201, or 404 for an unknown
  film / 409 for a duplicate) and `GET /watchlist/<user_id>?sort=recent|title`.

### Design decisions
1. **Default visibility — watchlists stay public by default (`public=True`).**
   CineLog is a community app and a watchlist is aspirational, low-stakes data;
   public defaults are what make discovery work, and most users never change a
   default. The tradeoff is consent — a watchlist can reveal sensitive interests —
   so the mitigation is "public by default, but never silently": visibility is a
   first-class field, surfaced clearly and easy to toggle. (Full reasoning under
   Comment 4.)
2. **Sort order — configurable, defaulting to date-added.** I adopted the
   maintainer's preferred default (recency matches how people use a want-to-watch
   list, and it matches `get_collection()`), but kept alphabetical available via
   `?sort=title` for the browse-to-find case. (Full reasoning under Comment 5.)

### How to manually test
```bash
# 1. Set up and run
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py                      # serves on http://127.0.0.1:5000

# 2. Create a user and a film, and note their UUIDs.
#    (Use the /films endpoints or a Python shell; both IDs are UUIDs.)

# 3. Add a film to the watchlist -> expect 201 + the new entry
curl -s -X POST http://127.0.0.1:5000/watchlist/<USER_UUID>/add \
  -H "Content-Type: application/json" \
  -d '{"film_id": "<FILM_UUID>"}'

# 4. Add the SAME film again -> expect 409 Conflict (deduplication)
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  http://127.0.0.1:5000/watchlist/<USER_UUID>/add \
  -H "Content-Type: application/json" \
  -d '{"film_id": "<FILM_UUID>"}'

# 5. Add a film_id that doesn't exist -> expect 404 Not Found
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  http://127.0.0.1:5000/watchlist/<USER_UUID>/add \
  -H "Content-Type: application/json" \
  -d '{"film_id": "00000000-0000-0000-0000-000000000000"}'

# 6. View the watchlist — default is newest-first
curl -s http://127.0.0.1:5000/watchlist/<USER_UUID> | python -m json.tool

# 7. View it alphabetically (add 2+ films first to see the difference)
curl -s "http://127.0.0.1:5000/watchlist/<USER_UUID>?sort=title" | python -m json.tool

# 8. Run the automated tests
pytest tests/ -v                   # 7 passed
```
