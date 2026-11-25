# 0003 Features in Postgres, not in memory

## Context

Rules need sliding windows over each account's history: payments in the last minute, distinct payees in ten minutes, a 30-day median, money in and out over 30 minutes. These could live in process memory, Redis, or a stream processor.

## Decision

Keep a `payments` table indexed by `(from_account, occurred_at)` and `(to_account, occurred_at)`, and compute every feature in one SQL query inside the scoring transaction. Windows are measured from the ledger's posting time (`occurred_at`), not arrival time.

## Consequences

- Any number of replicas can score: state lives in one place, and the advisory lock (0002) keeps one payer's payments in order across replicas.
- A late or redelivered event is judged against the activity around when it was posted. An event that arrives late doesn't cause earlier payments to be re-scored; that would need a re-scoring pass and is left out deliberately.
- No extra infrastructure. On a 2-vCPU machine the whole pipeline (HTTP, de-duplication, insert, features, alert) runs at about 550 events/s with Postgres on the same machine. Past that point, the next steps are partitioning `payments` by time and moving hot windows to Redis, measured with the simulator before and after.
