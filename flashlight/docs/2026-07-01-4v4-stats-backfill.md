---
title: Backfill 4v4 (two_four) bedwars stats — upgrade v1 rows to data format version 2
topic: player-stats-backfill
area: internal/adapters/playerrepository
related_pr: https://github.com/Amund211/flashlight/pull/291
created_at: 2026-07-01
status: done
started_at: 2026-07-05 19:57 CEST
completed_at: 2026-07-06 CEST
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

## Connection (how the SQL steps are executed)

The SQL steps below are run from a local `psql` over the Cloud SQL Auth Proxy (Unix socket), with
the `postgres` password pulled from Secret Manager — not Cloud SQL Studio. In one shell:

```bash
cloud-sql-proxy --unix-socket /cloudsql/ prism-overlay:northamerica-northeast2:flashlight-postgres
```
then, in another:
```bash
PGPASSWORD="$(gcloud secrets versions access latest --secret=flashlight-db-password --project=prism-overlay)" \
  psql "host=/cloudsql/prism-overlay:northamerica-northeast2:flashlight-postgres user=postgres dbname=flashlight"
```
All steps run in the `flashlight` schema, so each block starts with `SET search_path TO flashlight;`.
(The proxy holds one long-lived connection; per-statement autocommit applies as with Studio.)

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
| keyset (remaining), dedicated core `db-custom-4-16384` | 2026-07-06 (post-Step 5.5) | ~2,250,482 | **Completed.** Each 20k batch ≈ **just under 2 s** (~10k rows/s) — no throttling, no app-cancellation storm. Already-done id windows reported 0 rows and flew past. |

- Total v1 rows at start (from Step 1): **2,490,482**
- Migrated pre-pause: 240,000 (2026-07-05). Remaining ~2,250,482 migrated on the dedicated core 2026-07-06.
- **Total rows migrated: 2,490,482 (backfill COMPLETE).** Confirm with Step 6 (0 v1 rows remaining).
- Finished at: 2026-07-06 (dedicated-core resume run) — per-batch ~2 s, whole remainder in a few minutes.

> ### 🔴 Root cause of the slow/uneven batches: instance tier `db-f1-micro`
> The Cloud SQL instance is `db-f1-micro` — shared-core, ~0.6 GB RAM, **burstable CPU**. Sustained
> writes fly for ~10 batches (3–7s) on accumulated burst credits, then the credits drain and CPU is
> throttled to baseline → batches balloon to 30–70s and the live app's queries hit `context`
> deadlines (`canceling statement due to user request`). Not checkpoints/autovacuum (`last_autovacuum`
> was 2026-06-13; `n_dead_tup` 201k < the ~520k trigger). A bare `count(*)` took 12s — the instance is
> simply underpowered for this one-time bulk write.
>
> **Resume plan → see [Step 5.5](#step-55--temporary-instance-upgrade-resume-enabler) for the researched tier choice + full mechanics.** In short: temporarily scale to a dedicated-core tier, run to completion (~20–25 min single-session), scale back:
> ```bash
> gcloud sql instances patch flashlight-postgres --project=prism-overlay --tier=db-custom-4-16384   # up (restarts, <60s offline)
> # ... CALL backfill_4v4();  (restore batch=20k and drop pg_sleep on a dedicated core) ...
> gcloud sql instances patch flashlight-postgres --project=prism-overlay --tier=db-f1-micro          # back down (<60s offline)
> ```

- **Nothing to clean up while paused:** in-flight batch rolled back on Ctrl-C; committed batches durable;
  no open txn/locks; partial index already dropped; `backfill_4v4()` procedure left in place for one-command resume.
- Started at: 2026-07-05 (multiple sessions) · Finished at: 2026-07-06 (dedicated-core resume).

> ### 📈 Storage impact (expected MVCC bloat — noted for posterity)
> A one-time full-table UPDATE rewrites every row (new version + dead old version) and, because we
> *grew* each row (added the `4v4` key) with the default `fillfactor=100`, most updates spilled
> off-page → **non-HOT**, bloating both the heap and all three `stats` indexes; plus a transient WAL
> burst on the data disk. So a large storage rise during the run is **expected** — it is not
> duplicated logical data (row count is exactly 2,490,482 and Step 6 checksums confirm no unintended
> changes).
>
> **Observed 2026-07-06 (Storage usage chart, 1 h window):** flat until the `CALL backfill_4v4()` run
> at ~20:05 CEST, a step up during the run, then **plateau** — growth was bounded to the UPDATE.
> Tooltip at **20:04:00 CEST** showed two "Storage usage" series reading **3.79 GiB** and **7.24 GiB**;
> the provisioned disk auto-resized one step (to ~16 GiB).
>
> **Precedent + expectation:** the 2026-07-05 pre-pause run produced the same transient "blip" that
> **receded afterward** as autovacuum reclaimed dead tuples for reuse — the used-bytes line is
> expected to fall again here too. ⚠️ But reclaimed space is only *reusable*, not returned: neither
> the heap file nor the Cloud SQL disk shrinks, and disk auto-resize is **one-way** — the instance is
> now provisioned (and billed) at the larger disk permanently, and scaling the tier back to
> `db-f1-micro` does **not** reduce the disk size.
>
> **Post-run resolution (2026-07-06, after downgrade + `VACUUM stats`):** disk settled at
> `dataDiskSizeGb=15` (was 10 → +50%, permanent — confirmed still 15 GB on `db-f1-micro`).
> `VACUUM stats;` brought `n_dead_tup` to **0** (dead space reclaimed for reuse); `stats` is total
> **5662 MB** (heap 4869 MB, indexes 792 MB), `n_live_tup` 2,660,885, autovacuum already having run
> 18:11 UTC. Plain VACUUM freed space for reuse but — as expected — did **not** shrink the file or the
> 15 GB disk. (The size query matched **two** `stats` tables across schemas; the real one is
> `flashlight.stats` @ 2,660,885 rows — filter by `schemaname='flashlight'` next time.)

---

## Step 5.5 — Temporary instance upgrade (resume enabler)

The paused run stalled purely because `db-f1-micro` is shared-core / burstable (Step 5 root
cause). Before resuming, temporarily move the instance to a **dedicated-core** tier so CPU is
sustained, run the backfill to completion, then scale straight back to `db-f1-micro`. This step
records the tier research, the chosen target, and exactly what the change does to the instance,
data, and connections. Sources: Cloud SQL docs — [machine series](https://docs.cloud.google.com/sql/docs/postgres/machine-series-overview),
[instance settings](https://docs.cloud.google.com/sql/docs/postgres/instance-settings),
[storage options](https://docs.cloud.google.com/sql/docs/postgres/storage-options-overview).

### 5.5.1 — Current instance (from `gcloud sql instances describe`, 2026-07-06)

| field | value |
|---|---|
| tier | `db-f1-micro` — shared-core, 1 burst vCPU, **0.614 GB** RAM |
| edition | `ENTERPRISE` |
| availabilityType | `ZONAL` — single node, **no HA / no failover** |
| region / zone | `northamerica-northeast2` (Toronto) / `-c` |
| Postgres | 17.7 |
| disk | **10 GB `PD_SSD`**, `storageAutoResize=true` (limit 0 = unlimited) |
| read replicas | none |
| primary IP | `34.124.127.91` (`ipv4Enabled`); `connectionName` = `prism-overlay:northamerica-northeast2:flashlight-postgres` |
| protections | PITR on, 7 daily backups, `deletionProtectionEnabled=true`, `cloudsql.iam_authentication=on` |

### 5.5.2 — Available machine types (Cloud SQL Enterprise edition)

Enterprise offers three series. Shared-core and dedicated-core both sit on the instance's
current `PD_SSD` storage, so moving *between* them is a plain in-place tier change. N4 uses
Hyperdisk Balanced → a storage migration, not a simple resize → **avoid for a temporary bump**.

| series | naming | vCPU | RAM rule | note |
|---|---|---|---|---|
| Shared-core | `db-f1-micro`, `db-g1-small` | 1 (burst) | 0.614 / 1.7 GB fixed | **burstable CPU — the current bottleneck** |
| **Dedicated-core** | `db-custom-{vCPU}-{MB}` | 1, or even 2–96 | 0.9–6.5 GB per vCPU, ×256 MB, ≥ 3.75 GB | **sustained CPU; same PD_SSD; simple in-place resize** |
| N4 | `db-custom-N4-{vCPU}-{MB}` | 2–80 (step 2) | 2–8 GB per vCPU | Hyperdisk only → storage migration; skip |

(Enterprise **Plus** adds N2/C4A + near-zero-downtime scaling, but switching editions is a
larger, not-cleanly-reversible change — out of scope for a one-time backfill.)

### 5.5.3 — What actually binds this backfill

- **Primary = CPU throttling.** Shared-core burst credits drain after ~10 batches → CPU
  throttled to baseline → batches balloon 20s→70s and the live app's 30s-deadline queries get
  cancelled (Step 5 root cause). A **dedicated core removes this entirely** — that alone unblocks
  the resume.
- **Secondary ceiling = the 10 GB disk.** Cloud SQL PD_SSD scales ~**30 IOPS/GB** and
  ~**0.48 MB/s per GB**, so 10 GB ≈ **300 IOPS / ~4.8 MB/s** write ceiling. Per-vCPU network caps
  (~250 MB/s per vCPU) sit far above that, so on a dedicated core the **disk size — not the
  machine — is the throughput cap.** Empirically the healthy batches ran ~1,000 rows/s ≈ ~2 MB/s
  WAL, comfortably under 4.8 MB/s ⇒ the disk sustains roughly **1,500–2,000 rows/s** ⇒ a single
  session finishes ~2.25M rows in **~20–25 min**. More vCPUs can't beat this cap.
- **RAM.** The whole DB fits on a 10 GB disk that has never auto-resized, so it is ≤ ~10 GB.
  **16 GB RAM caches the entire table in memory**, eliminating read IOPS so the disk's small
  IOPS/throughput budget is spent entirely on WAL/heap writes.

### 5.5.4 — Chosen target tier: `db-custom-4-16384` (4 vCPU, 16 GB)

Rationale: 4 sustained vCPUs kill the throttling with comfortable headroom for the WAL writer,
checkpointer, autovacuum, **and the live flashlight app** (which keeps serving throughout the
resume — the whole point of not co-starving it as `db-f1-micro` did); 16 GB caches the whole DB.
Valid custom shape (16384/4 = 4096 MB per vCPU, within 0.9–6.5 GB). Cost is negligible — a few
cents for the <1 h it's up.
- **Minimum-viable / cheaper:** `db-custom-2-8192` (2/8) — also uncaps CPU; single-session speed
  is identical (disk-bound), just less headroom for the co-resident app + background workers.
- **Overkill:** `db-custom-8-32768` and up — extra cores cannot beat the 10 GB disk cap.
- ⚠️ **Do NOT grow the disk.** The only lever to beat ~4.8 MB/s is a larger disk, but Cloud SQL
  disks **cannot shrink** — a "temporary" disk bump would be permanent. Accept the ceiling;
  ~20–25 min is fine. (Parallelizing 2–3 keyset-disjoint sessions could ~2× it but is likewise
  capped by the disk and needs a range-parameterized proc + hand-picked UUIDv7 split points —
  not worth the extra moving parts for a 20-min job. **Run single-session.**)

### 5.5.5 — What the tier change does (Enterprise, ZONAL)

- **Restart, brief downtime.** Changing vCPU/RAM takes the instance **offline < 60 s** (full
  operation completes in a few minutes). No HA here, so no failover shortens it — expect the full
  sub-minute blip. Applies to **both** the scale-up and the scale-back.
- **Existing connections dropped** across each restart (Cloud SQL Studio session included — the
  in-flight batch rolls back; see below).
- **Data preserved.** The persistent disk is decoupled from the compute VM; only the VM is
  resized/replaced. All committed rows — including the **240k already migrated** — are intact.
  PITR/backups unaffected.
- **IP + zone preserved.** Primary IP stays `34.124.127.91`, same zone `-c`, same
  `connectionName` ⇒ **no flashlight config change and no redeploy** needed.
- **Live flashlight app (Cloud Run):** during the <60 s restart its DB queries fail/time out;
  being stateless and connecting per-request via the Cloud SQL connector, it **reconnects
  automatically** once the instance is RUNNABLE. Users may see brief errors for ~1 min — the same
  failure mode the backfill already induces, so no new surface. Prefer a low-traffic moment.
- **The paused backfill:** the `backfill_4v4()` procedure lives in the DB and **survives the
  restart**. Do the tier change with **no `CALL` running** (it's paused now — good). If a restart
  ever coincides with a live `CALL`: in-flight batch rolls back, committed batches stay durable,
  re-`CALL` resumes (idempotent keyset march).

### 5.5.6 — Procedure

```bash
# 0. (optional) eyeball current disk usage vs the 10 GB cap in the console/metrics — the backfill
#    adds a small '4v4' key to every row + dead tuples, so the table grows; if used approaches
#    10 GB it may trip the (irreversible) auto-resize. 240k rows already migrated with no resize,
#    so there is headroom, but confirm before the big remaining ~2.25M.

# 1. Scale UP to dedicated core (restarts, <60s offline). deletion-protection does NOT block a patch.
gcloud sql instances patch flashlight-postgres --project=prism-overlay --tier=db-custom-4-16384

# 2. Wait until RUNNABLE on the new tier.
gcloud sql instances describe flashlight-postgres --project=prism-overlay \
  --format='value(state,settings.tier)'
#    expect:  RUNNABLE   db-custom-4-16384

# 3. Resume in Cloud SQL Studio. On a dedicated core, restore batch=20000 and DROP the pg_sleep
#    throttle inside backfill_4v4() (the 5k+pg_sleep(2) build was a micro-only diagnostic).
#    Then:  CALL backfill_4v4();
#    Idempotent keyset: already-done id windows update 0 rows and fly past in seconds.

# 4. Post-verify (Step 6): 0 v1 rows, 0 rows missing '4v4', Step 3 re-run mismatching = 0.

# 5. Scale BACK DOWN once verified (another <60s restart).
gcloud sql instances patch flashlight-postgres --project=prism-overlay --tier=db-f1-micro

# 6. Confirm back on db-f1-micro + RUNNABLE, then run Step 5 cleanup (DROP PROCEDURE backfill_4v4();).
gcloud sql instances describe flashlight-postgres --project=prism-overlay \
  --format='value(state,settings.tier)'   # expect: RUNNABLE  db-f1-micro
```

**Execution record**
- Status: `[ ] pending  [x] scaled-up  [x] resumed  [x] scaled-back`
- Scaled up at: 2026-07-06 19:41:30 CEST (17:41:30 UTC) · tier `db-custom-4-16384` (4 vCPU / 16 GB) ·
  operation `UPDATE` 17:41:30→17:46:16 UTC (DONE) · `settingsVersion` 615→620 · zone/IP unchanged.
- Instance RUNNABLE / `database system is ready to accept connections` at:
  **2026-07-06 19:43:40 CEST (17:43:40 UTC)**.
- Observed downtime: **~22 s** — old node served until `17:43:18` (fast-shutdown → `checkpoint: shutdown
  immediate`), back up `17:43:40`. Cloud SQL provisioned the new machine *before* cutting over (op
  started 17:41:30 but DB stayed up until 17:43:18), so user-facing outage was far under the <60 s cap.
- Restart log check: **clean.** Only expected shutdown-sequence lines (`received fast shutdown request`,
  `checkpoint: shutdown immediate`, internal `cloudsqladmin@127.0.0.1` FATALs); **no PANIC, no
  post-restart WARNING+**. IP `34.124.127.91` and zone `-c` preserved (no flashlight config change).
- Resume run: 2026-07-06 · `CALL backfill_4v4()` (batch=20k, no pg_sleep) migrated the remaining
  ~2,250,482 rows · **each 20k batch ≈ just under 2 s (~10k rows/s)** · no throttling, no app
  cancellations — the dedicated core did exactly what it was for. Whole remainder in a few minutes.
- Scaled back down at: 2026-07-06 · op 18:18:05→18:29:06 UTC (DONE, ~11 min; the gcloud client wait
  timed out but the server op completed — confirmed via `gcloud beta sql operations wait`). Now
  **RUNNABLE on `db-f1-micro`** (settingsVersion 627). Disk stays at **15 GB** (tier change ≠ disk change).
- Notes / anomalies: none. ~2 s/batch was ~5× the pre-run estimate (16 GB cached the whole DB in RAM,
  so the 10 GB disk-throughput ceiling never bit at this batch size). Downgrade took ~11 min (vs ~5 min
  up) — slower to shrink the machine under the now-larger disk, but clean and non-erroring.

---

## Step 5.6 — Integrity checksums (capture before resume, compare after)

Belt-and-suspenders proof that the backfill changes **only** the two things it's supposed to.
The UPDATE's `SET` clause writes exactly `player_data = player_data || {'4v4':…}` and
`data_format_version = 2` — it *structurally cannot* touch `id`, `player_uuid`, or `queried_at`.
So a checksum over each row **with `data_format_version` and `player_data->'4v4'` masked out** is
an **invariant**: correct migration ⇒ identical before and after; any corruption of a non-4v4
field ⇒ the checksum changes. We also checksum the untouched native-v2 set as a second safety net.

**Why the mask is exact (verified locally, PG18):** on a v1 row `player_data` has no `4v4` key, so
`player_data - '4v4'` = `player_data`. After the backfill, `player_data - '4v4'` strips the added
key and — because JSONB canonical key order is a pure function of the key set — yields text
**byte-identical** to the original. A scratch-schema test (incl. `4v4 = {}`, zero-key drops, no-`xp`
rows, plus a negative-control tamper that correctly flipped to MISMATCH) confirmed round-trip
equality. `data_format_version` is excluded entirely since it flips 1→2 by design.

**Coverage caveat (read this).** The backfill is already ~240k rows in, so a baseline captured now
is a *true* pre-migration snapshot only for the **~2.25M rows still at v1**; comparing it at the
end fully validates the remaining run. The **240k already migrated** have no pre-touch baseline
here — they are trusted **by construction** (the UPDATE cannot write the masked columns). For
100% coverage including those 240k, use the **gold-standard** option: the Step 0 on-demand backup
(20:03 CEST) / PITR predates *all* migration writes (~20:50) — restore it to a throwaway instance,
run the same **(A)** checksum over `id <= cutover` there, and compare to prod's `:after`.

- **Masked columns:** `data_format_version` (dropped), `player_data->'4v4'` (dropped via `- '4v4'`).
- **Migrated set:** `id <= '019f1d06-89ee-7ea0-bea9-7fe149faac38'` (the Step 5 cutover). Static —
  no new rows ever land in this id range (UUIDv7 only ascends), so its membership is frozen.
- **Native-v2 set:** `cutover < id <= frozen_ceiling`. We freeze `max(id)` of current v2 rows so
  live writes (which get `id > ceiling`) are excluded and before/after compare like-for-like.
- Aggregate is order-independent and streamable (no giant `string_agg`): two 64-bit `bit_xor`
  slices of the per-row md5 + a 64-bit `sum` + `count`. Detecting an accidental collision after
  real corruption is ~2⁻¹²⁸.

Each set collapses to **one 32-char `checksum` string** you can paste and eyeball later, plus two
corroborating columns: `n` (rows checksummed) and `checksum_sum` (an order-independent hash-sum
component). The `checksum` is the authoritative comparison — it folds `count` + two 64-bit
`bit_xor` slices + the sum into a single md5. (Verified locally on PG18, incl. a negative-control
tamper that correctly changed the value.)

### Setup — run once, now (before resuming)

```sql
SET search_path TO flashlight;

-- 1) Find the native-v2 ceiling (the "latest current v2 row"). Record it, then paste it as the
--    literal in view (B) below — that bakes the ceiling into the view definition so it stays frozen
--    (live writes get id > it → excluded). No table; the only cleanup is the two views.
SELECT max(id) AS v2_ceiling FROM stats WHERE data_format_version = 2;
--    => paste the returned id into (B)'s  id <= '...'  bound.

-- (A) migrated set — masked: drop data_format_version + player_data->'4v4'; scope id <= cutover
CREATE OR REPLACE VIEW ck_migrated AS
SELECT
  count(*) AS n,
  coalesce(sum(('x'||substr(h,1,16))::bit(64)::bigint::numeric),0) AS checksum_sum,
  md5(
    count(*)::text || '|' ||
    coalesce(bit_xor(('x'||substr(h,1,16))::bit(64)::bigint),0)::text || '|' ||
    coalesce(bit_xor(('x'||substr(h,17,16))::bit(64)::bigint),0)::text || '|' ||
    coalesce(sum(('x'||substr(h,1,16))::bit(64)::bigint::numeric),0)::text
  ) AS checksum
FROM (
  SELECT md5(id||'|'||player_uuid||'|'||
             (queried_at AT TIME ZONE 'UTC')::text||'|'||
             (player_data - '4v4')::text) AS h
  FROM stats WHERE id <= '019f1d06-89ee-7ea0-bea9-7fe149faac38'
) q;

-- (B) native-v2 set — FULL row (must stay entirely untouched); scope cutover < id <= frozen ceiling
CREATE OR REPLACE VIEW ck_v2 AS
SELECT
  count(*) AS n,
  coalesce(sum(('x'||substr(h,1,16))::bit(64)::bigint::numeric),0) AS checksum_sum,
  md5(
    count(*)::text || '|' ||
    coalesce(bit_xor(('x'||substr(h,1,16))::bit(64)::bigint),0)::text || '|' ||
    coalesce(bit_xor(('x'||substr(h,17,16))::bit(64)::bigint),0)::text || '|' ||
    coalesce(sum(('x'||substr(h,1,16))::bit(64)::bigint::numeric),0)::text
  ) AS checksum
FROM (
  SELECT md5(id||'|'||player_uuid||'|'||
             (queried_at AT TIME ZONE 'UTC')::text||'|'||
             player_data::text||'|'||data_format_version::text) AS h
  FROM stats
  WHERE id >  '019f1d06-89ee-7ea0-bea9-7fe149faac38'
    AND id <= '019f3894-c7b2-7360-9fef-a4bca3cf2264'   -- frozen v2 ceiling (captured 2026-07-06)
) q;
```

### Capture (now) and compare (Step 6)

Run this one query **now** (paste the two rows into the record), then **again after** the migration
(Step 6). The `checksum` per set must be identical; `n` and `checksum_sum` corroborate.

```sql
SET search_path TO flashlight;
SELECT 'migrated' AS set, n, checksum_sum, checksum FROM ck_migrated
UNION ALL
SELECT 'v2'       AS set, n, checksum_sum, checksum FROM ck_v2;
```

Cleanup after Step 6 sign-off: `DROP VIEW ck_migrated, ck_v2;` (no table to drop — ceiling is baked into the view def).

**Execution record**
- Status: `[x] baseline captured  [ ] compared`
- Frozen `v2_ceiling` id: `019f3894-c7b2-7360-9fef-a4bca3cf2264` (captured 2026-07-06)
- Baseline (before), captured 2026-07-06:
  - `migrated` n=**2490482** (== Step 1 start-of-run v1 count ✓) · sum=`-3721709571243416750685` · **checksum=`87f86f10a02ff0fd3f91a002a01acc58`**
  - `v2` n=**171288** · sum=`-2756496957840101405499` · **checksum=`2d2c0c58b2848e3f93b04eda1cc650fc`**
- After migration: `migrated` **checksum=`________`** (expect `87f86f10a02ff0fd3f91a002a01acc58`) · `v2` **checksum=`________`** (expect `2d2c0c58b2848e3f93b04eda1cc650fc`)
- Verdict (checksum strings identical?): migrated = ___ · v2 = ___
- (optional) gold-standard backup cross-check of the 240k: ___

---

## Step 6 — Post-verification

```sql
SELECT count(*) FROM stats WHERE data_format_version = 1;    -- expect 0
SELECT count(*) FROM stats WHERE NOT (player_data ? '4v4');  -- expect 0
```

Then **re-run Step 3's reconstruction check, split by the cutover boundary.** ⚠️ A full re-run will
still surface Step 3's **27 accepted native-v2 mismatches** (`id > cutover`, untouched by the
backfill) — so those are *not* expected to be 0. What must be **exactly 0** is mismatches among the
**backfilled** rows (`id <= cutover`), since we wrote their `4v4` block as precisely this subtraction:

```sql
WITH derived AS (
  SELECT s.id,
    s.id <= '019f1d06-89ee-7ea0-bea9-7fe149faac38' AS is_backfilled,
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
  GROUP BY s.id, s.player_data
)
SELECT is_backfilled,
       count(*)                                         AS total,
       count(*) FILTER (WHERE stored_no_ws <> computed) AS mismatching
FROM derived GROUP BY is_backfilled ORDER BY is_backfilled DESC;
-- is_backfilled = t: total ≈ 2,490,482, mismatching MUST be 0
-- is_backfilled = f: the accepted native-v2 drift (~27, maybe a few more from new writes)
```

Finally, run the **Step 5.6 "compare after"** capture and confirm each `checksum` equals its baseline
(`migrated` = `87f86f10a02ff0fd3f91a002a01acc58`, `v2` = `2d2c0c58b2848e3f93b04eda1cc650fc`).

**Execution record**
- Status: `[x] done` — run 2026-07-06 on the dedicated core, all checks green.
- Remaining v1 rows = **0** ✓
- Rows missing `4v4` key = **0** ✓
- Step 3 re-run: backfilled (`id<=cutover`) `total`=2,490,482 · `mismatching` = **0** ✓ (every reconstructed 4v4 block exact) ·
  native-v2 (`id>cutover`) `total`=172,172 · `mismatching` = **33** (accepted Hypixel drift — was 27 at Step 3 over 121,546 rows; +6 from new native-v2 writes since; 33/172,172 = 0.019%, same rate).
- Step 5.6 checksums both **match baseline exactly**: migrated `87f86f10a02ff0fd3f91a002a01acc58`
  (n=2,490,482) · v2 `2d2c0c58b2848e3f93b04eda1cc650fc` (n=171,288). ⇒ every non-`4v4` field is
  byte-identical pre/post migration, and native-v2 rows are entirely untouched.

---

## Sign-off

- Outcome: `[x] success  [ ] rolled back` — all 2,490,482 v1 rows backfilled to v2. Step 6 all green:
  0 v1 rows left, 0 rows missing `4v4`, 0 mismatches among backfilled rows, both Step 5.6 checksums
  == baseline (`migrated` `87f86f10…acc58`, `v2` `2d2c0c58…50fc`).
- Completed at: 2026-07-06 CEST
- Signed off by: Amund211
- Follow-ups / anomalies observed:
  - **Disk permanently grew 10 GB → 15 GB** (`dataDiskSizeGb`; one-way auto-resize, survives the
    downgrade to `db-f1-micro`). See the 📈 Storage impact callout. Used bytes recede post-VACUUM; the
    provisioned/billed 15 GB does not.
  - **Cleanup:** done 2026-07-06 — `backfill_4v4()` procedure and the `ck_migrated` / `ck_v2` views dropped.
  - Known/accepted imperfections (owner-approved, unchanged from Steps 3/4): `ws` omitted on
    backfilled 4v4 blocks; ~33 native-v2 reconstruction mismatches (ordinary Hypixel counter drift),
    which the backfill did not touch.

## Approach notes

- **Keep the SQL in the repo.** Even though it's run ad-hoc in Cloud SQL Studio, this doc is
  the auditable record; keep it committed. A big synchronous `UPDATE` inside the migrator at
  deploy time would be slow/lock-heavy, so ad-hoc batched is the right call for a one-time
  backfill.
- **Optional Go-level cross-check.** A test that takes real v2 `player_data` blobs, zeroes
  the `4v4` block, runs the reconstruction, and asserts it round-trips to the same
  `playerToDataStorage` output (minus `ws`) would add belt-and-suspenders confidence.

---

# Ongoing — native-v2 reconstruction-mismatch tracking

The backfill reconstructs `4v4` by subtraction (`all − (1+2+3+4)`). On **native-v2** rows we have
Hypixel's real `two_four_*`, so we can measure where that reconstruction would have been *wrong* —
the rows where `(4v4 − ws) ≠ all − (1+2+3+4)`, i.e. the ordinary Hypixel counter drift analysed in
Step 3 (27 rows then, 33 at Step 6). v1 rows have no ground truth, so this native-v2 population is our
**proxy for the backfill's error rate** — the same drift affects the backfilled rows at the same rate,
we just can't point to which ones.

**Re-runnable at any time**, scoped to native-v2 rows via `id >= '019f1d07-1313-7672-9e48-e784c7839c09'`
(the earliest native-v2 id — the `first v2` boundary from Step 3c; equivalently `id > cutover`). The
population grows as the live app writes new v2 rows, so the counts drift upward over time — that's
expected. **Append a new dated entry under each query every time you run it** (don't overwrite prior
runs — this is a time series). Run in the `flashlight` schema (`SET search_path TO flashlight;`).

## Query A — number of stats with incorrect backfill

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
  WHERE s.id >= '019f1d07-1313-7672-9e48-e784c7839c09'
  GROUP BY s.id, s.player_data
)
SELECT count(*) AS stats_with_incorrect_backfill
FROM derived WHERE stored_no_ws <> computed;
```

**Runs:**
- 2026-07-06 20:42 CEST → `stats_with_incorrect_backfill` = **33** (Step 3 baseline was 27 on 2026-07-05).

## Query B — number of players with incorrect backfill

```sql
WITH derived AS (
  SELECT s.id, s.player_uuid,
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
  WHERE s.id >= '019f1d07-1313-7672-9e48-e784c7839c09'
  GROUP BY s.id, s.player_uuid, s.player_data
)
SELECT count(DISTINCT player_uuid) AS players_with_incorrect_backfill
FROM derived WHERE stored_no_ws <> computed;
```

**Runs:**
- 2026-07-06 20:42 CEST → `players_with_incorrect_backfill` = **15** (Step 3 baseline was 14 on 2026-07-05).

## Query C — players with incorrect backfill by count (uuid, username, #stats; desc, limit 25)

```sql
WITH derived AS (
  SELECT s.id, s.player_uuid,
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
  WHERE s.id >= '019f1d07-1313-7672-9e48-e784c7839c09'
  GROUP BY s.id, s.player_uuid, s.player_data
),
mm AS (SELECT player_uuid FROM derived WHERE stored_no_ws <> computed)
SELECT mm.player_uuid,
       u.username,
       count(*) AS incorrect_stats
FROM mm
LEFT JOIN usernames u ON u.player_uuid = mm.player_uuid
GROUP BY mm.player_uuid, u.username
ORDER BY incorrect_stats DESC, mm.player_uuid
LIMIT 25;
```

**Runs:**
- 2026-07-06 20:42 CEST — top 25 (15 rows returned):

  ```
             player_uuid              |    username    | incorrect_stats
  --------------------------------------+----------------+-----------------
   5cf1dd9a-40ac-4656-b76d-48e8f47f8332 | NoobzCraft     |               5
   ff06feeb-aa61-43c3-8bc9-74b9b4e12b48 | PulsarX2       |               5
   d132284b-740e-4dba-b97b-721a80d66dca | jahmers        |               3
   ddbc32c2-9648-406c-840c-f6ed62a77d5b | KS7D           |               3
   eda7a720-826c-48ae-a069-5cda307858bc | Lioness_Rising |               3
   f14cb7ab-ee22-46a9-9473-3f62997bb468 | Tra1se         |               3
   8ae4e743-a998-4a86-b970-9ad7dd6f57c9 | liltikes       |               2
   8b301d37-78bd-4dca-a334-e35ef933adf3 |                |               2
   0fe5d9fc-567e-4e8b-93ce-1430a1f5b145 | Stumptail      |               1
   6b8be2f8-2f8b-464a-837c-302a03655fd2 | tcry           |               1
   ...
  (15 rows)
  ```
