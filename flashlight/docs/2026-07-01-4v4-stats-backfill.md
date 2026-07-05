---
title: Backfill 4v4 (two_four) bedwars stats — upgrade v1 rows to data format version 2
topic: player-stats-backfill
area: internal/adapters/playerrepository
related_pr: https://github.com/Amund211/flashlight/pull/291
created_at: 2026-07-01
status: in_progress
started_at: 2026-07-05 19:57 CEST
completed_at:
executed_by: Amund211
target_instance: prism-overlay:northamerica-northeast2:flashlight-postgres
target_schema: flashlight
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
- Status: `[x] done`
- Run at: 2026-07-05 20:03 CEST
- Backup id / PITR confirmation: PITR **enabled** (`pointInTimeRecoveryEnabled=True`, `enabled=True`). On-demand backup also created successfully: `gcloud sql backups create --instance=flashlight-postgres` → "backed up."
- Notes: Belt-and-suspenders — both PITR and a fresh on-demand backup are in place before any writes.

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
- Status: `[x] done`
- Run at: 2026-07-05 20:06 CEST
- Version counts (paste output):
  ```
   data_format_version |  count
  ---------------------+---------
                     1 | 2490482
                     2 |  121509
  ```
- Distinct v1 keys (paste output):
  ```
   1, 2, 3, 4, all, xp   (6 keys — no 4v4)
  ```
- Matches expectation? `[x] yes` — only v1/v2 present (no v0); v1 keys are exactly `xp,1,2,3,4,all` with no `4v4`. **Start-of-run v1 count: 2,490,482** (carry to Step 5).

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
- Status: `[x] done`
- Run at: 2026-07-05 20:09 CEST
- `bad_rows` = **0**   (must be **0** to proceed) ✅
- If > 0, paste sample offending rows and decision: n/a — clean across all 2,490,482 v1 rows.

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
- Status: `[x] done` — 27 mismatches investigated; **not a blocker**, error accepted by owner (see "Step 3 analysis" + Step 3c below)
- Run at: 2026-07-05 20:11 CEST
- `total_v2` = 121546 · `matching` = 121519 · `mismatching` = **27**
- `mismatching` is **0**? `[ ] yes  [x] no` — 27/121546 ≈ 0.022% of v2 rows do not reconcile by subtraction.
- Note: `total_v2` (121546) > Step 1 v2 count (121509); live service wrote ~37 new v2 rows between steps. Expected — `StorePlayer` only INSERTs new rows at v2, so the v1 pool is static/monotonically decreasing.
- If no, paste sample mismatches + analysis (this would be a real Hypixel-data finding):


```sql
flashlight=> WITH derived AS (
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
  ),
  mm AS (
    SELECT id, stored_no_ws, computed FROM derived WHERE stored_no_ws <> computed
  )
  SELECT mm.id,
         keys.k              AS differing_key,
         mm.stored_no_ws->keys.k AS stored_val,
         mm.computed->keys.k     AS computed_val
  FROM mm
  CROSS JOIN LATERAL jsonb_object_keys(mm.stored_no_ws || mm.computed) AS keys(k)
  WHERE (mm.stored_no_ws->keys.k) IS DISTINCT FROM (mm.computed->keys.k)
  ORDER BY mm.id, differing_key;
                  id                  | differing_key | stored_val | computed_val
--------------------------------------+---------------+------------+--------------
 019f1f80-0e6e-7aac-9866-1eb662fcc52b | bl            | 17         | 18
 019f1f80-0e6e-7aac-9866-1eb662fcc52b | d             | 163        | 165
 019f1f80-0e6e-7aac-9866-1eb662fcc52b | fd            | 12         | 13
 019f1f80-0e6e-7aac-9866-1eb662fcc52b | gp            | 82         | 83
 019f1f80-0e6e-7aac-9866-1eb662fcc52b | l             | 15         | 16
 019f1faa-8c04-7a9f-9e55-1bfe2f0a8de3 | bl            | 17         | 18
 019f1faa-8c04-7a9f-9e55-1bfe2f0a8de3 | d             | 163        | 165
 019f1faa-8c04-7a9f-9e55-1bfe2f0a8de3 | fd            | 12         | 13
 019f1faa-8c04-7a9f-9e55-1bfe2f0a8de3 | gp            | 82         | 83
 019f1faa-8c04-7a9f-9e55-1bfe2f0a8de3 | l             | 15         | 16
 019f2053-7858-7816-8bdf-708c240c67bd | bl            | 7          | 8
 019f2053-7858-7816-8bdf-708c240c67bd | fd            | 7          | 8
 019f2053-7858-7816-8bdf-708c240c67bd | gp            | 12         | 13
 019f2053-7858-7816-8bdf-708c240c67bd | l             | 7          | 8
 019f2053-7861-772b-9491-f8e92c560f33 | bl            | 144        | 145
 019f2053-7861-772b-9491-f8e92c560f33 | fd            | 135        | 136
 019f2053-7861-772b-9491-f8e92c560f33 | gp            | 242        | 243
 019f2053-7861-772b-9491-f8e92c560f33 | k             | 478        | 480
 019f2053-7861-772b-9491-f8e92c560f33 | l             | 131        | 132
 019f20b1-e779-782b-803c-8aa2d88ca216 | bl            | 91         | 92
 019f20b1-e779-782b-803c-8aa2d88ca216 | d             | 365        | 367
 019f20b1-e779-782b-803c-8aa2d88ca216 | fd            | 84         | 85
 019f20b1-e779-782b-803c-8aa2d88ca216 | gp            | 167        | 168
 019f20b1-e779-782b-803c-8aa2d88ca216 | k             | 255        | 256
 019f20b1-e779-782b-803c-8aa2d88ca216 | l             | 82         | 83
 019f23bd-251e-7479-ba73-a2503fe6e000 | bl            | 70         | 71
 019f23bd-251e-7479-ba73-a2503fe6e000 | d             | 439        | 440
 019f23bd-251e-7479-ba73-a2503fe6e000 | fd            | 67         | 68
 019f23bd-251e-7479-ba73-a2503fe6e000 | gp            | 150        | 151
 019f23bd-251e-7479-ba73-a2503fe6e000 | k             | 343        | 345
 019f23bd-251e-7479-ba73-a2503fe6e000 | l             | 64         | 65
 019f245d-91df-7589-bae4-fcf6428b8f71 | bl            | 45         | 46
 019f245d-91df-7589-bae4-fcf6428b8f71 | d             | 1111       | 1113
 019f245d-91df-7589-bae4-fcf6428b8f71 | fd            | 37         | 38
 019f245d-91df-7589-bae4-fcf6428b8f71 | gp            | 542        | 543
 019f245d-91df-7589-bae4-fcf6428b8f71 | k             | 563        | 567
 019f245d-91df-7589-bae4-fcf6428b8f71 | l             | 34         | 35
 019f2499-33a9-7bfe-834b-6e5bc6279fca | bb            | 87         | 88
 019f2499-33a9-7bfe-834b-6e5bc6279fca | bl            | 26         | 27
 019f2499-33a9-7bfe-834b-6e5bc6279fca | d             | 407        | 413
 019f2499-33a9-7bfe-834b-6e5bc6279fca | fd            | 27         | 28
 019f2499-33a9-7bfe-834b-6e5bc6279fca | fk            | 271        | 272
 019f2499-33a9-7bfe-834b-6e5bc6279fca | gp            | 349        | 350
 019f2499-33a9-7bfe-834b-6e5bc6279fca | k             | 278        | 281
 019f2499-33a9-7bfe-834b-6e5bc6279fca | l             | 28         | 29
 019f249b-d720-7606-b0ab-a213673e98dc | bl            | 144        | 145
 019f249b-d720-7606-b0ab-a213673e98dc | fd            | 135        | 136
 019f249b-d720-7606-b0ab-a213673e98dc | gp            | 242        | 243
 019f249b-d720-7606-b0ab-a213673e98dc | k             | 478        | 480
 019f249b-d720-7606-b0ab-a213673e98dc | l             | 131        | 132
 019f24df-01ca-7919-8499-14157b93faaa | bl            | 7          | 8
 019f24df-01ca-7919-8499-14157b93faaa | fd            | 7          | 8
 019f24df-01ca-7919-8499-14157b93faaa | gp            | 12         | 13
 019f24df-01ca-7919-8499-14157b93faaa | l             | 7          | 8
 019f24df-0227-7b0c-9b77-63b3597a5b5f | bl            | 144        | 145
 019f24df-0227-7b0c-9b77-63b3597a5b5f | fd            | 135        | 136
 019f24df-0227-7b0c-9b77-63b3597a5b5f | gp            | 242        | 243
 019f24df-0227-7b0c-9b77-63b3597a5b5f | k             | 478        | 480
 019f24df-0227-7b0c-9b77-63b3597a5b5f | l             | 131        | 132
 019f251a-8c2c-77c9-8cf0-83c40ed78742 | bb            |            | 2
 019f251a-8c2c-77c9-8cf0-83c40ed78742 | bl            |            | 1
 019f251a-8c2c-77c9-8cf0-83c40ed78742 | d             | 11         | 13
 019f251a-8c2c-77c9-8cf0-83c40ed78742 | fk            | 5          | 9
 019f251a-8c2c-77c9-8cf0-83c40ed78742 | gp            | 10         | 11
 019f251a-8c2c-77c9-8cf0-83c40ed78742 | w             | 10         | 11
 019f2593-538f-779a-8cd8-ce4732d698e0 | bb            |            | 2
 019f2593-538f-779a-8cd8-ce4732d698e0 | bl            |            | 1
 019f2593-538f-779a-8cd8-ce4732d698e0 | d             | 11         | 13
 019f2593-538f-779a-8cd8-ce4732d698e0 | fk            | 5          | 9
 019f2593-538f-779a-8cd8-ce4732d698e0 | gp            | 10         | 11
 019f2593-538f-779a-8cd8-ce4732d698e0 | w             | 10         | 11
 019f25a5-7a94-711c-9e72-7d9d69142990 | bl            | 138        | 139
 019f25a5-7a94-711c-9e72-7d9d69142990 | d             | 609        | 611
 019f25a5-7a94-711c-9e72-7d9d69142990 | fd            | 134        | 135
 019f25a5-7a94-711c-9e72-7d9d69142990 | gp            | 228        | 229
 019f25a5-7a94-711c-9e72-7d9d69142990 | k             | 663        | 664
 019f25a5-7a94-711c-9e72-7d9d69142990 | l             | 141        | 142
 019f2601-b02d-733d-8acf-cb203abf83d4 | bl            | 138        | 139
 019f2601-b02d-733d-8acf-cb203abf83d4 | d             | 609        | 611
 019f2601-b02d-733d-8acf-cb203abf83d4 | fd            | 134        | 135
 019f2601-b02d-733d-8acf-cb203abf83d4 | gp            | 228        | 229
 019f2601-b02d-733d-8acf-cb203abf83d4 | k             | 663        | 664
 019f2601-b02d-733d-8acf-cb203abf83d4 | l             | 141        | 142
 019f2823-1b4d-7ac0-96b8-e112d38ecfad | bl            | 45         | 46
 019f2823-1b4d-7ac0-96b8-e112d38ecfad | d             | 1111       | 1113
 019f2823-1b4d-7ac0-96b8-e112d38ecfad | fd            | 37         | 38
 019f2823-1b4d-7ac0-96b8-e112d38ecfad | gp            | 542        | 543
 019f2823-1b4d-7ac0-96b8-e112d38ecfad | k             | 563        | 567
 019f2823-1b4d-7ac0-96b8-e112d38ecfad | l             | 34         | 35
 019f28fc-3023-740b-8030-09dfb6f363b1 | d             | 1502       | 1523
 019f28fc-3023-740b-8030-09dfb6f363b1 | fk            | 675        | 676
 019f28fc-3023-740b-8030-09dfb6f363b1 | gp            | 667        | 668
 019f28fc-3023-740b-8030-09dfb6f363b1 | k             | 1182       | 1192
 019f28fc-3023-740b-8030-09dfb6f363b1 | w             | 460        | 461
 019f28fd-00fc-744b-861b-4664bca360d8 | bb            | 26         | 27
 019f28fd-00fc-744b-861b-4664bca360d8 | bl            | 5          | 6
 019f28fd-00fc-744b-861b-4664bca360d8 | d             | 132        | 141
 019f28fd-00fc-744b-861b-4664bca360d8 | fd            | 4          | 5
 019f28fd-00fc-744b-861b-4664bca360d8 | gp            | 144        | 145
 019f28fd-00fc-744b-861b-4664bca360d8 | k             | 99         | 109
 019f28fd-00fc-744b-861b-4664bca360d8 | l             | 5          | 6
 019f2964-ac8d-7956-b4e7-1f55d3cf1a0c | d             | 1502       | 1523
 019f2964-ac8d-7956-b4e7-1f55d3cf1a0c | fk            | 675        | 676
 019f2964-ac8d-7956-b4e7-1f55d3cf1a0c | gp            | 667        | 668
 019f2964-ac8d-7956-b4e7-1f55d3cf1a0c | k             | 1182       | 1192
 019f2964-ac8d-7956-b4e7-1f55d3cf1a0c | w             | 460        | 461
 019f2aae-1ce1-71d5-99e3-a5f193ae800d | bl            | 138        | 139
 019f2aae-1ce1-71d5-99e3-a5f193ae800d | d             | 609        | 611
 019f2aae-1ce1-71d5-99e3-a5f193ae800d | fd            | 134        | 135
 019f2aae-1ce1-71d5-99e3-a5f193ae800d | gp            | 228        | 229
 019f2aae-1ce1-71d5-99e3-a5f193ae800d | k             | 663        | 664
 019f2aae-1ce1-71d5-99e3-a5f193ae800d | l             | 141        | 142
 019f2ae1-70f6-718b-8fc5-ea950b88f73a | bl            | 144        | 145
 019f2ae1-70f6-718b-8fc5-ea950b88f73a | fd            | 135        | 136
 019f2ae1-70f6-718b-8fc5-ea950b88f73a | gp            | 242        | 243
 019f2ae1-70f6-718b-8fc5-ea950b88f73a | k             | 478        | 480
 019f2ae1-70f6-718b-8fc5-ea950b88f73a | l             | 131        | 132
 019f2b57-42c6-781c-a33f-d7adadc76def | bl            | 5          | 6
 019f2b57-42c6-781c-a33f-d7adadc76def | d             | 28         | 30
 019f2b57-42c6-781c-a33f-d7adadc76def | fd            | 5          | 6
 019f2b57-42c6-781c-a33f-d7adadc76def | gp            | 18         | 19
 019f2b57-42c6-781c-a33f-d7adadc76def | k             | 21         | 22
 019f2b57-42c6-781c-a33f-d7adadc76def | l             | 5          | 6
 019f2dbb-e605-78c9-be3b-7a2416f861d4 | bl            | 70         | 71
 019f2dbb-e605-78c9-be3b-7a2416f861d4 | d             | 439        | 440
 019f2dbb-e605-78c9-be3b-7a2416f861d4 | fd            | 67         | 68
 019f2dbb-e605-78c9-be3b-7a2416f861d4 | gp            | 150        | 151
 019f2dbb-e605-78c9-be3b-7a2416f861d4 | k             | 343        | 345
 019f2dbb-e605-78c9-be3b-7a2416f861d4 | l             | 64         | 65
 019f2e7a-5386-7217-80e7-22742e842f00 | bl            | 138        | 139
 019f2e7a-5386-7217-80e7-22742e842f00 | d             | 609        | 611
 019f2e7a-5386-7217-80e7-22742e842f00 | fd            | 134        | 135
 019f2e7a-5386-7217-80e7-22742e842f00 | gp            | 228        | 229
 019f2e7a-5386-7217-80e7-22742e842f00 | k             | 663        | 664
 019f2e7a-5386-7217-80e7-22742e842f00 | l             | 141        | 142
 019f2f76-723f-79af-8894-cb7174757b45 | bl            | 47         | 48
 019f2f76-723f-79af-8894-cb7174757b45 | d             | 1170       | 1172
 019f2f76-723f-79af-8894-cb7174757b45 | fd            | 38         | 39
 019f2f76-723f-79af-8894-cb7174757b45 | gp            | 573        | 574
 019f2f76-723f-79af-8894-cb7174757b45 | k             | 578        | 582
 019f2f76-723f-79af-8894-cb7174757b45 | l             | 35         | 36
 019f2fac-cdda-7deb-8939-91d545b1e3a7 | bl            | 4          | 5
 019f2fac-cdda-7deb-8939-91d545b1e3a7 | d             | 50         | 59
 019f2fac-cdda-7deb-8939-91d545b1e3a7 | fd            | 3          | 4
 019f2fac-cdda-7deb-8939-91d545b1e3a7 | gp            | 31         | 32
 019f2fac-cdda-7deb-8939-91d545b1e3a7 | k             | 37         | 43
 019f2fac-cdda-7deb-8939-91d545b1e3a7 | l             | 3          | 4
 019f2fc3-ee1b-780a-8218-437c7edad5cb | bl            | 22         | 23
 019f2fc3-ee1b-780a-8218-437c7edad5cb | d             | 207        | 211
 019f2fc3-ee1b-780a-8218-437c7edad5cb | fd            | 23         | 24
 019f2fc3-ee1b-780a-8218-437c7edad5cb | gp            | 89         | 90
 019f2fc3-ee1b-780a-8218-437c7edad5cb | k             | 189        | 195
 019f2fc3-ee1b-780a-8218-437c7edad5cb | l             | 24         | 25
(153 rows)
```

```sql
flashlight=> WITH derived AS (
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
  ),
  mm AS (
    SELECT id FROM derived WHERE stored_no_ws <> computed
  )
  SELECT s.player_uuid,
         u.username,
         count(*)          AS mismatching_rows,
         min(s.queried_at) AS first_seen,
         max(s.queried_at) AS last_seen
  FROM mm
  JOIN stats s      ON s.id = mm.id
  LEFT JOIN usernames u ON u.player_uuid = s.player_uuid
  GROUP BY s.player_uuid, u.username
  ORDER BY mismatching_rows DESC, s.player_uuid;
             player_uuid              |    username    | mismatching_rows |          first_seen           |           last_seen
--------------------------------------+----------------+------------------+-------------------------------+-------------------------------
 5cf1dd9a-40ac-4656-b76d-48e8f47f8332 | NoobzCraft     |                4 | 2026-07-02 00:56:09.030552+00 | 2026-07-04 02:07:25.394238+00
 ff06feeb-aa61-43c3-8bc9-74b9b4e12b48 | PulsarX2       |                4 | 2026-07-03 01:43:49.63677+00  | 2026-07-04 18:53:16.536023+00
 ddbc32c2-9648-406c-840c-f6ed62a77d5b | KS7D           |                3 | 2026-07-02 19:45:39.756548+00 | 2026-07-04 23:28:39.468885+00
 8ae4e743-a998-4a86-b970-9ad7dd6f57c9 | liltikes       |                2 | 2026-07-02 16:50:26.189478+00 | 2026-07-04 15:25:16.660639+00
 8b301d37-78bd-4dca-a334-e35ef933adf3 |                |                2 | 2026-07-03 17:17:23.806561+00 | 2026-07-03 19:11:31.386959+00
 d132284b-740e-4dba-b97b-721a80d66dca | jahmers        |                2 | 2026-07-01 21:05:13.806432+00 | 2026-07-01 21:51:38.467783+00
 eda7a720-826c-48ae-a069-5cda307858bc | Lioness_Rising |                2 | 2026-07-02 23:12:04.633788+00 | 2026-07-03 01:23:59.99315+00
 f14cb7ab-ee22-46a9-9473-3f62997bb468 | Tra1se         |                2 | 2026-07-02 00:56:09.034901+00 | 2026-07-02 22:07:02.587699+00
 0fe5d9fc-567e-4e8b-93ce-1430a1f5b145 | Stumptail      |                1 | 2026-07-04 04:16:06.851825+00 | 2026-07-04 04:16:06.851825+00
 6b8be2f8-2f8b-464a-837c-302a03655fd2 | tcry           |                1 | 2026-07-02 02:39:17.844765+00 | 2026-07-02 02:39:17.844765+00
 88411250-8df7-448a-afab-a51c137aee70 | tabrodrodrod   |                1 | 2026-07-05 00:28:01.852403+00 | 2026-07-05 00:28:01.852403+00
 abe8bfd4-12dc-4e54-bf48-10f024501705 | aubrdan        |                1 | 2026-07-02 20:50:47.814615+00 | 2026-07-02 20:50:47.814615+00
 d2d9b9c3-d463-4403-b72f-b9804dba13ba |                |                1 | 2026-07-03 17:18:17.309658+00 | 2026-07-03 17:18:17.309658+00
 e80cd78e-38e6-43a8-bff2-f9dac366a7bc | Amin888        |                1 | 2026-07-05 00:53:17.452252+00 | 2026-07-05 00:53:17.452252+00
(14 rows)
```

### Step 3 analysis — root cause of the 27 mismatches

The 153-row key-level diff and the 14-row player rollup above (both pasted verbatim) show a
single, coherent pattern:

- **27 mismatching rows → 14 distinct players**, each snapshotted 1–4 times. Not scattered
  noise; a small set of accounts.
- **`computed` is always ≥ `stored`, never <.** So `all − (1+2+3+4) > two_four_real`, i.e.
  `all > 1 + 2 + 3 + 4 + 4v4`. The top-level `_bedwars` totals include activity from **a mode
  we do not bucket** into `1/2/3/4/4v4`. Subtraction wrongly folds that residual into 4v4.
- **The residual is small per row** — often a single game's worth (`gp +1`, a win, or a few
  extra kills/deaths).
- **Every mismatch is dated 2026-07-01 → 2026-07-05.** But so is *every* v2 row (see Step 3c).

**Step 3c — timeline check (results):**

Query 1 (version date ranges):
```
 version |  rows   |           earliest            |            latest
---------+---------+-------------------------------+-------------------------------
       1 | 2490482 | 2024-12-04 22:00:53.431959+00 | 2026-07-01 09:33:15.629986+00
       2 |  121709 | 2026-07-01 09:33:50.723834+00 | 2026-07-05 18:27:02.749205+00
```
Query 2 (v2 rows bucketed by reconcile/mismatch):
```
 mismatch |  rows  |           earliest            |            latest
----------+--------+-------------------------------+-------------------------------
 f        | 121693 | 2026-07-01 09:33:50.723834+00 | 2026-07-05 18:27:18.528004+00
 t        |     27 | 2026-07-01 21:05:13.806432+00 | 2026-07-05 00:53:17.452252+00
```

**Interpretation — the "new mode" hypothesis is UNCONFIRMABLE and rejected.** v2 begins
`2026-07-01 09:33:50`, ~35s after the last v1 write (`09:33:15`) — PR #291 deployed here and
flipped the write path v1→v2. So **there are zero pre-July-1 v2 rows**: both the matching and
mismatching buckets span the identical 4-day window. There is no older v2 baseline that could
show "the invariant held before ~July 1", so the data cannot support a new-mode story. Owner
does not believe a new mode exists.

**Most likely cause: ordinary Hypixel counter drift** — the top-level `_bedwars` totals
occasionally running a game or two ahead of the summed per-mode counters. Persistent, not
tied to any launch, scattered across a small set of players. This means it affects **v1 rows
at the same rate**, and there is no ground truth on v1 rows to detect *which* ones.

**Decision (owner, 2026-07-05): accept the error and proceed with the backfill.** Rationale:
- Impact is tiny: ~0.022% of rows (27/121,709 on v2 → est. **~550 of 2,490,482 v1 rows**),
  each off by roughly one game's worth on the 4v4 block only.
- The residual is *positive* (`all > sum`), so Step 2's negative-diff guard does not catch it;
  the backfill will write these slightly-too-large 4v4 blocks. That is understood and accepted.
- `domain.PlayerPIT.Fourv4` is unread today → zero behavioral impact now.
- No cheaper, more-accurate alternative exists for v1 (no ground truth to validate against);
  the only "more correct" option would be to not backfill at all.

### Migration provenance — the v1 vs native-v2 split (capture before the backfill erases it)

After Step 5 every row is `data_format_version = 2`, and **nothing flags "backfilled from v1"
vs "written natively as v2"** (the backfill sets `data_format_version = 2` and does not stamp a
provenance marker). So the boundary must be recorded here, before we run it.

**The cutover is clean in time — no interleaving** (Step 3c, Query 1):

| set | rows (at start) | `queried_at` range |
|---|---|---|
| **v1** — will be backfilled | 2,490,482 | `2024-12-04 22:00:53.431959+00` → `2026-07-01 09:33:15.629986+00` |
| **native v2** — untouched | 121,855+ (growing; live) | `2026-07-01 09:33:50.723834+00` → ongoing |

`max(v1) = 09:33:15.63` is ~35s **before** `min(v2) = 09:33:50.72` — the PR #291 deploy
cutover, with zero overlap. `id` is UUIDv7 (time-ordered), so the split is clean by `id` too.

> **Definition of the backfilled set (permanent):** exactly the rows with
> `queried_at ≤ 2026-07-01 09:33:15.629986+00` — equivalently `id ≤` the last v1 id captured
> below. Native-v2 rows are `queried_at ≥ 2026-07-01 09:33:50.723834+00`. This predicate still
> identifies the once-v1 rows after they've all become `data_format_version = 2`.

Concrete boundary ids (run this and paste; recorded so the split is reproducible forever):

```sql
-- Last 5 v1 rows and first 5 v2 rows, ordered by time — the exact cutover boundary.
(
  SELECT 'v1 (last)'  AS bucket, id, queried_at
  FROM stats WHERE data_format_version = 1
  ORDER BY queried_at DESC, id DESC LIMIT 5
)
UNION ALL
(
  SELECT 'v2 (first)' AS bucket, id, queried_at
  FROM stats WHERE data_format_version = 2
  ORDER BY queried_at ASC, id ASC LIMIT 5
)
ORDER BY queried_at;
```

_Boundary ids (run 2026-07-05 20:38 CEST):_
```
   bucket   |                  id                  |          queried_at
------------+--------------------------------------+-------------------------------
 v1 (last)  | 019f1d05-56f3-79ad-8cc3-a237c6d84f70 | 2026-07-01 09:31:57.043342+00
 v1 (last)  | 019f1d05-5757-78c6-9c71-02029ad5161d | 2026-07-01 09:31:57.142943+00
 v1 (last)  | 019f1d05-5776-7ced-95e3-b740ce2d9c89 | 2026-07-01 09:31:57.174188+00
 v1 (last)  | 019f1d05-6a1c-73a9-88dc-3a9ca532519a | 2026-07-01 09:32:01.947185+00
 v1 (last)  | 019f1d06-89ee-7ea0-bea9-7fe149faac38 | 2026-07-01 09:33:15.629986+00   <- LAST v1
 v2 (first) | 019f1d07-1313-7672-9e48-e784c7839c09 | 2026-07-01 09:33:50.723834+00   <- FIRST v2
 v2 (first) | 019f1d07-552d-7b06-9062-0bdae271b308 | 2026-07-01 09:34:07.659807+00
 v2 (first) | 019f1d07-580a-70c8-a11e-f6b29867a3c1 | 2026-07-01 09:34:08.393369+00
 v2 (first) | 019f1d07-5a28-763a-a3b7-5b95c35f836b | 2026-07-01 09:34:08.935926+00
 v2 (first) | 019f1d07-5a28-7b71-9e95-2b2081e3e851 | 2026-07-01 09:34:08.936271+00
```
- **Last v1 id:** `019f1d06-89ee-7ea0-bea9-7fe149faac38` @ `2026-07-01 09:33:15.629986+00`
- **First v2 id:** `019f1d07-1313-7672-9e48-e784c7839c09` @ `2026-07-01 09:33:50.723834+00`
- UUIDv7 prefixes `019f1d06…` (last v1) < `019f1d07…` (first v2) confirm the split is clean by
  `id` as well as by time — **the backfilled set is exactly `id ≤ 019f1d06-89ee-7ea0-bea9-7fe149faac38`**
  (⇔ `queried_at ≤ 2026-07-01 09:33:15.629986+00`).

---

## Step 4 — Quantify the only unrecoverable field (`ws` on 4v4)

```sql
SELECT
  count(*) FILTER (WHERE player_data->'4v4' ? 'ws') AS v2_4v4_with_ws,
  count(*)                                          AS v2_total
FROM stats WHERE data_format_version = 2;
```

**Execution record**
- Status: `[x] done`
- Run at: 2026-07-05 20:34 CEST
- `v2_4v4_with_ws` = **52677** / `v2_total` = **121855**  ⇒ **~43.2%** of v2 rows carry a `ws` key on the 4v4 block.
- Acceptable? `[x] yes` — accepted, but **higher than the runbook's "rare" assumption** (§ "The one exception: winstreak"). Caveats/interpretation:
  - A present `ws` means the winstreak was API-*visible*, not that it was nonzero. `ws` is `*int` with `omitempty`, so a visible streak of 0 still serializes as `"ws":0`; only an *absent/hidden* streak is dropped. So 43.2% ≈ "winstreak visible", of which most values are likely 0. Share with a *meaningful* (nonzero) 4v4 streak is not yet measured — see optional Step 4a below.
  - **Every backfilled row omits `ws` entirely**, so ~43% will differ from a native-v2 row by a missing `ws` key (mostly `ws:0` vs absent — semantically ~"no active streak"). This is an accepted, known imperfection; `Fourv4` is unread today.
  - ⚠️ **Sample caveat (applies to all v2-derived numbers here, incl. Step 3's mismatch rate):** the v2 window is only ~4 days (2026-07-01 → 07-05) and flashlight currently serves heavy non-Prism/Rainbow traffic (bots, third parties scanning players / mapping guilds, etc.). That traffic may query a very different player distribution than real bedwars players — so this 43.2% (and the 0.022% mismatch rate) may not represent the historical v1 population we're actually backfilling. Treat these as rough, possibly-skewed estimates, not ground truth.

---

## Step 4a — `ws` value distribution (optional; how much of the 43.2% is meaningful)

Splits the `ws` presence from Step 4 into nonzero (real streak, lost on backfill) vs
visible-but-0 (`ws:0` vs absent — negligible) vs hidden (already absent).

```sql
SELECT
  count(*) FILTER (WHERE (player_data->'4v4'->>'ws')::int > 0) AS ws_positive,
  count(*) FILTER (WHERE (player_data->'4v4'->>'ws')::int = 0) AS ws_zero,
  count(*) FILTER (WHERE NOT (player_data->'4v4' ? 'ws'))      AS ws_absent,
  count(*)                                                     AS v2_total
FROM stats WHERE data_format_version = 2;
```

**Execution record**
- Status: `[x] done`
- Run at: 2026-07-05 20:38 CEST
- Result:
  ```
   ws_positive | ws_zero | ws_absent | v2_total
  -------------+---------+-----------+----------
         22405 |   30341 |     69236 |   121982
  ```
- Interpretation: **22,405 (18.4%)** have a *nonzero* 4v4 winstreak — the genuinely meaningful
  loss on backfill. 30,341 (24.9%) are visible-but-0 (`ws:0` vs absent — negligible). 69,236
  (56.8%) already hide it. So the ws omission materially changes ~18% of rows vs native v2
  (same 4-day/bot-skew caveat as Step 4). **Owner accepts the ws loss on backfilled rows.**
  (`v2_total` 121,982 > Step 4's 121,855 — live writes between the two queries; expected.)

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

### Batch 1 dry-run + automation plan (2026-07-05 20:54 CEST)

- **Batch 1 validated as a dry-run, then rolled back.** Ran the statement above inside an
  explicit transaction: `UPDATE 20000`; counts inside the txn `v1 2,470,482 / v2 142,221`;
  spot-check of pre-cutover (`id < 019f1d07-1313…`) v2 rows showed sane 4v4 blocks, including a
  correct empty `{}` for a player with zero net 4v4 activity (`omitempty` parity). **Rolled
  back — nothing committed;** the write logic is confirmed correct.
- **Timing: ~20s per 20k batch.** ~124 batches left ⇒ ~42-min floor, and it degrades: migrated
  rows keep their low `id`s and there is no index on `data_format_version`, so each later `batch`
  CTE random-heap-skips a growing prefix of already-v2 rows (O(N²)).
- **Mitigation — partial index on v1 rows, built `CONCURRENTLY` (no write lock on the live table):**
  ```sql
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stats_v1_id
    ON stats (id) WHERE data_format_version = 1;
  ```
  Keeps every batch flat (~20s); the index self-shrinks as rows migrate and is empty when done.
  (Temporary — the only schema change; dropped after Step 6.)
- **Automation — loop in a procedure that COMMITs per batch** (keeps per-batch txns small, prints
  live progress, resumable via re-`CALL` since `data_format_version = 1` makes it idempotent):
  ```sql
  CREATE OR REPLACE PROCEDURE backfill_4v4() LANGUAGE plpgsql AS $$
  DECLARE affected bigint; total bigint := 0;
  BEGIN
    LOOP
      WITH batch AS (
        SELECT id FROM stats WHERE data_format_version = 1 ORDER BY id LIMIT 20000
      ),
      derived AS (
        SELECT s.id,
          COALESCE(jsonb_object_agg(kv.sk, kv.v) FILTER (WHERE kv.v <> 0), '{}'::jsonb) AS fourv4
        FROM stats s JOIN batch b ON b.id = s.id
        CROSS JOIN LATERAL (
          SELECT sk,
            COALESCE((s.player_data->'all'->>sk)::bigint,0)
            - COALESCE((s.player_data->'1'->>sk)::bigint,0)
            - COALESCE((s.player_data->'2'->>sk)::bigint,0)
            - COALESCE((s.player_data->'3'->>sk)::bigint,0)
            - COALESCE((s.player_data->'4'->>sk)::bigint,0) AS v
          FROM unnest(ARRAY['gp','w','l','bb','bl','fk','fd','k','d']) AS sk
        ) kv GROUP BY s.id
      )
      UPDATE stats t
      SET player_data = t.player_data || jsonb_build_object('4v4', d.fourv4),
          data_format_version = 2
      FROM derived d WHERE t.id = d.id AND t.data_format_version = 1;

      GET DIAGNOSTICS affected = ROW_COUNT;
      total := total + affected;
      RAISE NOTICE 'batch: % rows (cumulative %)', affected, total;
      COMMIT;                       -- per-batch commit; legal in a top-level CALL (autocommit)
      EXIT WHEN affected = 0;
    END LOOP;
    RAISE NOTICE 'backfill_4v4 done: % rows migrated', total;
  END; $$;

  CALL backfill_4v4();              -- run at top level, NOT inside BEGIN/a txn block
  ```
- **Cleanup (after Step 6 confirms):**
  ```sql
  DROP PROCEDURE backfill_4v4();
  DROP INDEX CONCURRENTLY IF EXISTS idx_stats_v1_id;
  ```

> The procedure's `RAISE NOTICE` output supersedes the manual per-batch table below; paste the
> final `done: N rows migrated` notice (and a few sample batch lines) into the log for the record.

### ⚠️ Revision (2026-07-05 ~21:05 CEST) — version-filter approach degraded; switched to keyset

The procedure above (**with** the partial index) degraded badly in the real run: batches went
20s (dry-run) → 1 → 2 → 3 min and climbing, and Cloud SQL error logs filled with `canceling
statement due to user request`. Those cancellations were the **live flashlight app's** queries
hitting their Go `context` deadlines (Cloud Run `timeoutSeconds: 30`) because the backfill
saturated the small instance — *not* the migration's own statements. Two root causes:

1. **O(N²) re-scan.** `WHERE data_format_version = 1 ORDER BY id LIMIT 20000` re-traverses the
   already-migrated low-id prefix every batch — no forward resume.
2. **The partial index backfired.** `id` is `TEXT PRIMARY KEY`, and *no* index references
   `data_format_version` or `player_data`, so the UPDATE was **HOT-eligible** (no index writes,
   cheap) — until `idx_stats_v1_id` made `data_format_version` an indexed predicate, disabling
   HOT and accumulating dead index entries the batch scan then had to walk. The index I added
   made it worse, not better.

**Fix — keyset/watermark by `id`, and drop the partial index (restores HOT updates).** The
backfilled set is exactly `id <= '019f1d06-89ee-7ea0-bea9-7fe149faac38'` (clean split, Step 5
boundary), so march that id range forward in fixed 20k windows — never re-scanning, never
filtering on version for *selection* (the UPDATE keeps `data_format_version = 1` only as an
idempotency guard). Each batch is a fresh PK range scan → flat and light; app cancellations
subside. Ctrl-C is safe (per-batch COMMITs durable; only the in-flight batch rolls back), and
re-running is safe: it starts from the beginning and already-done id windows update 0 rows
(skipped in seconds), so it converges without an expensive resume-point lookup.

```sql
DROP INDEX CONCURRENTLY IF EXISTS idx_stats_v1_id;

CREATE OR REPLACE PROCEDURE backfill_4v4() LANGUAGE plpgsql AS $$
DECLARE
  cutover   text := '019f1d06-89ee-7ea0-bea9-7fe149faac38';  -- last v1 id (Step 5 boundary)
  last_id   text;
  batch_max text;
  affected  bigint;
  total     bigint := 0;
BEGIN
  last_id := '';   -- start from the beginning; the keyset march skips already-done windows as
                   -- cheap no-op UPDATEs. Do NOT compute a max(id) "frontier" here: with no index
                   -- on data_format_version that scan is O(N) over the unmigrated range and took
                   -- >5 min on prod before the loop even started (first attempt was cancelled there).
  RAISE NOTICE 'starting from id > %', last_id;
  LOOP
    SELECT max(id) INTO batch_max
    FROM (SELECT id FROM stats WHERE id > last_id AND id <= cutover ORDER BY id LIMIT 20000) q;
    EXIT WHEN batch_max IS NULL;
    WITH batch AS (
      SELECT id FROM stats WHERE id > last_id AND id <= batch_max
    ),
    derived AS (
      SELECT s.id,
        COALESCE(jsonb_object_agg(kv.sk, kv.v) FILTER (WHERE kv.v <> 0), '{}'::jsonb) AS fourv4
      FROM stats s JOIN batch b ON b.id = s.id
      CROSS JOIN LATERAL (
        SELECT sk,
          COALESCE((s.player_data->'all'->>sk)::bigint,0)
          - COALESCE((s.player_data->'1'->>sk)::bigint,0)
          - COALESCE((s.player_data->'2'->>sk)::bigint,0)
          - COALESCE((s.player_data->'3'->>sk)::bigint,0)
          - COALESCE((s.player_data->'4'->>sk)::bigint,0) AS v
        FROM unnest(ARRAY['gp','w','l','bb','bl','fk','fd','k','d']) AS sk
      ) kv GROUP BY s.id
    )
    UPDATE stats t
    SET player_data = t.player_data || jsonb_build_object('4v4', d.fourv4),
        data_format_version = 2
    FROM derived d WHERE t.id = d.id AND t.data_format_version = 1;
    GET DIAGNOSTICS affected = ROW_COUNT;
    total := total + affected; last_id := batch_max;
    RAISE NOTICE 'batch up to % : % rows (cumulative %)', batch_max, affected, total;
    COMMIT;
    -- PERFORM pg_sleep(0.5);   -- throttle if app cancellations persist
  END LOOP;
  RAISE NOTICE 'backfill_4v4 done: % rows migrated', total;
END; $$;

CALL backfill_4v4();
```

Cleanup after Step 6: `DROP PROCEDURE backfill_4v4();` (index already dropped above).

**Verified locally (Postgres 18.4) before resuming on prod** — a scratch schema with
hand-computed ground-truth 4v4 blocks confirmed: exact reconstruction on all rows incl. edge
cases (`{}` for zero 4v4, partial zero-drop of `l`/`bl`/`fd`, `xp` preserved by `||`); the
`id <= cutover` bound leaves out-of-range rows untouched; idempotent re-run migrates 0; and
resume-from-frontier picks up exactly after the already-committed rows (the Ctrl-C case).

**Execution record — batch log**

| Phase | Run at (TZ) | Rows | Notes |
|---|---|--:|---|
| degraded runs (version-filter + partial index) | 2026-07-05 ~20:50–21:15 | ~120,000 | 6 batches committed before cancel; batches slowed 20s→3min (index disabled HOT). Cancelled. |
| index dropped + 1 timed batch (version-filter) | 2026-07-05 ~21:30 | 20,000 | **20.9s** committed — confirms dropping `idx_stats_v1_id` restored HOT updates; the index, not the id-skip, was the slowdown. |
| keyset, 20k batches (index dropped) | 2026-07-05 ~21:40 | ~20,000 | batch 8 = 20s clean; batch 9 spiked >80s (cancelled) — first sign of CPU throttling. |
| keyset, throttled 5k + pg_sleep(2) + per-batch timing | 2026-07-05 ~22:50 | ~80,000 | **Diagnostic run.** batches 1–10 = 3–7s, then 26s → **72s** → 38–40s as CPU burst credits drained. Cancelled at cum 80,000. |
| keyset (remaining) | _(paused — resume later)_ | _(fill)_ | resume with `CALL backfill_4v4();` after scaling the instance up (see root cause). |

- Total v1 rows at start (from Step 1): **2,490,482**
- **Migrated so far: 240,000** (confirmed 2026-07-05 ~22:56 CEST: v1 `2,250,482` / v2 `363,201`). **~2,250,482 v1 remaining (~90%)** for the resume run. Paused here.

> ### 🔴 Root cause of the slow/uneven batches: instance tier `db-f1-micro`
> The Cloud SQL instance is `db-f1-micro` — shared-core, ~0.6 GB RAM, **burstable CPU**. Sustained
> writes fly for ~10 batches (3–7s) on accumulated burst credits, then the credits drain and CPU is
> throttled to baseline → batches balloon to 30–70s and the live app's queries hit `context`
> deadlines (`canceling statement due to user request`). Not checkpoints/autovacuum (`last_autovacuum`
> was 2026-06-13; `n_dead_tup` 201k < the ~520k trigger). A bare `count(*)` took 12s — the instance is
> simply underpowered for this one-time bulk write.
>
> **Resume plan:** temporarily scale up to a dedicated-core tier, run to completion in minutes, scale back:
> ```bash
> gcloud sql instances patch flashlight-postgres --project=prism-overlay --tier=db-custom-1-3840   # up (restarts)
> # ... CALL backfill_4v4();  (can bump batch back to 20k and drop pg_sleep on a dedicated core) ...
> gcloud sql instances patch flashlight-postgres --project=prism-overlay --tier=db-f1-micro         # back down
> ```

- **Nothing to clean up while paused:** in-flight batch rolled back on Ctrl-C; committed batches durable;
  no open txn/locks; partial index already dropped; `backfill_4v4()` procedure left in place for one-command resume.
- Total rows migrated: _(fill after final run)_
- Started at: 2026-07-05 (multiple sessions) · Finished at: _____

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
