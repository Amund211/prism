---
title: Backfill 4v4 (two_four) bedwars stats — upgrade v1 rows to data format version 2
topic: player-stats-backfill
area: internal/adapters/playerrepository
related_pr: https://github.com/Amund211/flashlight/pull/291
created_at: 2026-07-01
status: planned            # planned | in_progress | done | aborted
started_at:                # fill when execution begins
completed_at:              # fill when execution finishes
executed_by:               # who ran it
target_instance:           # Cloud SQL instance
target_schema:             # schema the stats table lives in
tags: [backfill, jsonb, cloudsql, data-format-version, bedwars, 4v4, runbook]
---

# 4v4 stats backfill — interactive runbook

> This is a **live document**. As you run each step, fill in its **Execution record**
> (timestamp, output, rows affected, notes). Flip each step's status box and update the
> frontmatter `status` / `started_at` / `completed_at` as you go.

## Goal

Retroactively populate the `4v4` (Hypixel internal name `two_four`) bedwars stats block in
every historical `stats` row and bump those rows from `data_format_version = 1` to `2`, so
the result is **exactly what would have been written had we captured `two_four_*` all along**
(PR #291 started capturing it going forward).

## Key insight: historical 4v4 is exactly recoverable (except winstreak)

Verified against all 171 API fixtures (`internal/fixtures/hypixel_api_responses/`):
`overall == solo + doubles + threes + fours + 4v4` holds exactly for all 9 additive stats,
with **zero mismatches** — even for players with lots of dream/tourney modes (castle, rush,
lucky, voidless, ultimate, armed, swap, underworld, tourney_*). Those event modes do **not**
feed Hypixel's top-level `_bedwars` totals; only the 5 core modes do.

Every v1 row already stores `1, 2, 3, 4, all`, so 4v4 is reconstructable by subtraction:

```
4v4.X  =  all.X − (1.X + 2.X + 3.X + 4.X)     for X in {gp, w, l, bb, bl, fk, fd, k, d}
```

This is precisely what the v2 code writes, because the v2 code just copies Hypixel's
`two_four_*` fields — and those equal exactly this difference.

### The one exception: winstreak (`ws`)

Winstreak is a current-streak counter, not additive, so it cannot be derived. It will be
**absent** on every backfilled 4v4 block. In true history it would appear only when the
player had a *visible* 4v4 winstreak at query time (winstreak is often API-hidden, and 4v4
is niche), so this is the only place a backfilled row can differ from real history, and it
is rare. Step 4 quantifies it.

## Confirmed technical findings

- **JSONB normalizes storage.** `player_data` is `JSONB`, so Postgres reorders keys
  canonically and strips whitespace. Byte/key-order concerns are moot — a backfilled row and
  a natively-written v2 row with the same values are `=`-equal regardless of insertion order.
  Verified locally: inserting `{"xp":1200,"1":{...}}` came back with keys reordered.
- **Locking clause on the `batch` CTE — recommendation: no qualifier by default.**
  Both `FOR UPDATE` and `FOR UPDATE SKIP LOCKED` are *legal* in the `batch` CTE (tested
  locally); it's a plain `SELECT id ... ORDER BY id LIMIT n` with no aggregate, so a locking
  clause is allowed. (`FOR UPDATE` is *not* allowed on the `derived` CTE because it has
  `GROUP BY`/aggregation — but we never put it there.) Which to use:
  - **No qualifier — prefer for the normal single-session run.** The outer `UPDATE` already
    takes the row locks it needs; the CTE doesn't need to. Nothing else mutates v1 rows
    (`StorePlayer` only INSERTs new rows with fresh UUIDv7 ids at version 2; reads never
    write), so there's no race to defend against. In Cloud SQL Studio each statement
    autocommits, so a CTE lock would be held only for that one statement anyway.
  - **`FOR UPDATE SKIP LOCKED` — only if you run multiple backfill sessions in parallel.**
    `SKIP LOCKED` makes each session grab a *disjoint* batch instead of colliding on the same
    top-N ids. A pass may skip transiently-locked rows; the loop-until-0 re-check sweeps them
    up later, so completeness holds.
  - **Bare `FOR UPDATE` — avoid.** Redundant lock overhead for a single session; for parallel
    sessions it's worse (both pick the same ids, one *blocks*, then updates 0 rows after the
    `data_format_version = 1` re-check — wasted work). Worst of both worlds.
  - Independent of locking, the backfill UPDATE keeps `AND t.data_format_version = 1` in its
    **outer** `WHERE` so it is idempotent and re-checked at update time (EvalPlanQual):
    already-migrated rows are skipped, and re-runs are safe.
- **`omitempty` replicated in SQL.** The reconstruction drops zero-valued fields
  (`FILTER (WHERE v <> 0)`), matching Go's `omitempty`. A player with no 4v4 activity yields
  `"4v4": {}`, exactly like the native v2 code. Verified locally (`a2 -> {}`).

## Special considerations

1. **Negative-diff guard.** If any derived field is `< 0`, that row has inconsistent source
   data. Check over the whole DB (Step 2), not just fixtures. Don't blindly store negatives.
2. **Only touch v1.** `WHERE data_format_version = 1` protects the real v2 rows.
3. **Backup first.** Take an on-demand Cloud SQL backup (or confirm PITR is enabled).
4. **Schema/search_path.** The app does `SET search_path TO <schema>` — run these in the
   same schema (`target_schema` in the frontmatter).
5. **Batching.** A single `UPDATE` over the full v1 set could be a huge long-running
   transaction / WAL spike / Studio timeout. Use the self-limiting, resumable batched update.

## Context / low risk

- Nothing reads `domain.PlayerPIT.Fourv4` yet (only the domain struct declares it).
- `data_format_version` only gates the dedup comparison in `StorePlayer`; reads don't filter
  on it, so mixed v1/v2 already works. This backfill has **zero behavioral impact today** —
  it is purely forward-prep.
- Confirmed by owner: no v0 rows in production (v0 was early testing only); only v1 and v2.

## Storage key reference (`statsDataStorage` json tags)

| domain field | json key |
|---|---|
| Winstreak   | `ws` (omitempty, `*int`) |
| GamesPlayed | `gp` |
| Wins        | `w`  |
| Losses      | `l`  |
| BedsBroken  | `bb` |
| BedsLost    | `bl` |
| FinalKills  | `fk` |
| FinalDeaths | `fd` |
| Kills       | `k`  |
| Deaths      | `d`  |

Top-level `playerDataStorage` keys: `xp` (omitempty), `1`, `2`, `3`, `4`, `4v4`, `all`.

---

# Execution runbook

Fill in each **Execution record** as you go. Statuses: `pending → running → done` (or `blocked`).

## Step 0 — Backup

On-demand Cloud SQL backup (or verify PITR):

```
gcloud sql backups create --instance=<INSTANCE>
```

**Execution record**
- Status: `[ ] pending`  `[ ] done`  `[ ] blocked`
- Run at: _(YYYY-MM-DD HH:MM TZ)_
- Backup id / PITR confirmation: _____
- Notes: _____

---

## Step 1 — Preflight discovery

```sql
SELECT data_format_version, count(*) FROM stats GROUP BY 1 ORDER BY 1;
-- expect only 1 and 2

SELECT DISTINCT k FROM stats, jsonb_object_keys(player_data) AS k
WHERE data_format_version = 1;
-- expect exactly: xp, 1, 2, 3, 4, all   (NOT 4v4)
```

**Execution record**
- Status: `[ ] pending`  `[ ] done`  `[ ] blocked`
- Run at: _(YYYY-MM-DD HH:MM TZ)_
- Version counts (paste output):
  ```
  
  ```
- Distinct v1 keys (paste output):
  ```
  
  ```
- Matches expectation? `[ ] yes  [ ] no` — if no, explain: _____

---

## Step 2 — Consistency check (must return 0)

```sql
SELECT count(*) AS bad_rows
FROM stats s
WHERE s.data_format_version = 1
  AND EXISTS (
    SELECT 1
    FROM unnest(ARRAY['gp','w','l','bb','bl','fk','fd','k','d']) AS sk
    WHERE COALESCE((s.player_data->'all'->>sk)::bigint,0)
        - COALESCE((s.player_data->'1'  ->>sk)::bigint,0)
        - COALESCE((s.player_data->'2'  ->>sk)::bigint,0)
        - COALESCE((s.player_data->'3'  ->>sk)::bigint,0)
        - COALESCE((s.player_data->'4'  ->>sk)::bigint,0) < 0
  );
```

**Execution record**
- Status: `[ ] pending`  `[ ] done`  `[ ] blocked`
- Run at: _(YYYY-MM-DD HH:MM TZ)_
- `bad_rows` = _____   (must be **0** to proceed)
- If > 0, paste sample offending rows and decision: _____

---

## Step 3 — Validate reconstruction against real v2 data (`mismatching` must be 0)

```sql
WITH derived AS (
  SELECT s.id,
    (s.player_data->'4v4') - 'ws' AS stored_no_ws,
    COALESCE(jsonb_object_agg(kv.sk, kv.v) FILTER (WHERE kv.v <> 0), '{}'::jsonb) AS computed
  FROM stats s
  CROSS JOIN LATERAL (
    SELECT sk,
      COALESCE((s.player_data->'all'->>sk)::bigint,0)
      - COALESCE((s.player_data->'1'->>sk)::bigint,0)
      - COALESCE((s.player_data->'2'->>sk)::bigint,0)
      - COALESCE((s.player_data->'3'->>sk)::bigint,0)
      - COALESCE((s.player_data->'4'->>sk)::bigint,0) AS v
    FROM unnest(ARRAY['gp','w','l','bb','bl','fk','fd','k','d']) AS sk
  ) kv
  WHERE s.data_format_version = 2
  GROUP BY s.id, s.player_data
)
SELECT
  count(*)                                          AS total_v2,
  count(*) FILTER (WHERE stored_no_ws = computed)   AS matching,
  count(*) FILTER (WHERE stored_no_ws <> computed)  AS mismatching
FROM derived;

-- If mismatching > 0, inspect:
-- SELECT * FROM derived WHERE stored_no_ws <> computed LIMIT 20;
```

**Execution record**
- Status: `[ ] pending`  `[ ] done`  `[ ] blocked`
- Run at: _(YYYY-MM-DD HH:MM TZ)_
- `total_v2` = _____ · `matching` = _____ · `mismatching` = _____
- `mismatching` is **0**? `[ ] yes  [ ] no`
- If no, paste sample mismatches + analysis (this would be a real Hypixel-data finding):
  ```
  
  ```

---

## Step 4 — Quantify the only unrecoverable field (`ws` on 4v4)

```sql
SELECT
  count(*) FILTER (WHERE player_data->'4v4' ? 'ws') AS v2_4v4_with_ws,
  count(*)                                          AS v2_total
FROM stats WHERE data_format_version = 2;
```

**Execution record**
- Status: `[ ] pending`  `[ ] done`  `[ ] blocked`
- Run at: _(YYYY-MM-DD HH:MM TZ)_
- `v2_4v4_with_ws` = _____ / `v2_total` = _____  (share of rows where backfill omits a real `ws`)
- Acceptable? `[ ] yes  [ ] no` — notes: _____

---

## Step 5 — Backfill (batched, idempotent, resumable)

Run repeatedly until it reports **0 rows affected**. Each run flips up to 20k v1→v2; the
candidate pool shrinks each time. Safe to interrupt/resume. Default: **no locking clause**
(single session). Add `FOR UPDATE SKIP LOCKED` on the `batch` CTE *only* if you run multiple
sessions in parallel; do not use bare `FOR UPDATE` (see Confirmed technical findings).

```sql
WITH batch AS (
  SELECT id FROM stats
  WHERE data_format_version = 1
  ORDER BY id
  LIMIT 20000
  -- single session, no locking clause (chosen). See "Confirmed technical findings".
),
derived AS (
  SELECT s.id,
    COALESCE(jsonb_object_agg(kv.sk, kv.v) FILTER (WHERE kv.v <> 0), '{}'::jsonb) AS fourv4
  FROM stats s
  JOIN batch b ON b.id = s.id
  CROSS JOIN LATERAL (
    SELECT sk,
      COALESCE((s.player_data->'all'->>sk)::bigint,0)
      - COALESCE((s.player_data->'1'->>sk)::bigint,0)
      - COALESCE((s.player_data->'2'->>sk)::bigint,0)
      - COALESCE((s.player_data->'3'->>sk)::bigint,0)
      - COALESCE((s.player_data->'4'->>sk)::bigint,0) AS v
    FROM unnest(ARRAY['gp','w','l','bb','bl','fk','fd','k','d']) AS sk
  ) kv
  GROUP BY s.id
)
UPDATE stats t
SET player_data = t.player_data || jsonb_build_object('4v4', d.fourv4),
    data_format_version = 2
FROM derived d
WHERE t.id = d.id
  AND t.data_format_version = 1;
```

**Execution record — batch log**

| Batch # | Run at (TZ) | Rows affected | Cumulative | Notes |
|--------:|-------------|--------------:|-----------:|-------|
| 1       |             |               |            |       |
| 2       |             |               |            |       |
| 3       |             |               |            |       |
| …       |             |               |            |       |
| final   |             | **0**         |            | done  |

- Total v1 rows at start (from Step 1): _____
- Total rows migrated: _____
- Started at: _____ · Finished at: _____

---

## Step 6 — Post-verification

```sql
SELECT count(*) FROM stats WHERE data_format_version = 1;    -- expect 0
SELECT count(*) FROM stats WHERE NOT (player_data ? '4v4');  -- expect 0
```

Then **re-run Step 3** — it now covers the freshly-migrated rows too and must still show
`mismatching = 0`.

**Execution record**
- Status: `[ ] pending`  `[ ] done`  `[ ] blocked`
- Run at: _(YYYY-MM-DD HH:MM TZ)_
- Remaining v1 rows = _____ (expect 0)
- Rows missing `4v4` key = _____ (expect 0)
- Step 3 re-run `mismatching` = _____ (expect 0)

---

## Sign-off

- Outcome: `[ ] success  [ ] rolled back`
- Completed at: _____
- Signed off by: _____
- Follow-ups / anomalies observed: _____

## Approach notes

- **Keep the SQL in the repo.** Even though it's run ad-hoc in Cloud SQL Studio, this doc is
  the auditable record; keep it committed. A big synchronous `UPDATE` inside the migrator at
  deploy time would be slow/lock-heavy, so ad-hoc batched is the right call for a one-time
  backfill.
- **Optional Go-level cross-check.** A test that takes real v2 `player_data` blobs, zeroes
  the `4v4` block, runs the reconstruction, and asserts it round-trips to the same
  `playerToDataStorage` output (minus `ws`) would add belt-and-suspenders confidence.
