# 0002 Exactly-once processing on an at-least-once stream

## Context

The ledger's outbox delivers each event at least once: a crash between delivery and marking the event published sends it again, and several relays may run. Scoring a payment twice would double-count it in every window: a burst of five would look like ten.

## Decision

Handle each event in one Postgres transaction that inserts its `event_id` into `processed_events` first (`ON CONFLICT DO NOTHING`), then stores the payment, computes features, scores and writes any alert. If the insert finds the ID already there, the transaction does nothing else. Delivery is at least once; processing is exactly once.

Scoring also takes a transaction-scoped advisory lock on the payer, so concurrent payments from one account are scored one after another and each sees the ones before it. Different payers still score in parallel.

Status codes are chosen for the relay, which retries anything but 2xx and sends events in order: a malformed but authentic event gets 202 and goes to `rejected_events`, because retrying it forever would block every event behind it. A bad signature gets 401 and is retried, because that is a configuration problem someone needs to see.

## Consequences

- Redelivery, crashes and multiple relays are all safe, and tested with 20 concurrent deliveries of one event.
- The per-payer lock limits one account to one scoring at a time. That is a few milliseconds per payment; an account sending faster than that is itself suspicious.
