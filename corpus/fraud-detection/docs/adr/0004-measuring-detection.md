# 0004 Measuring detection in CI

## Context

A rule change can quietly make detection worse: catch less fraud, or flag more good customers. Unit tests check that a rule fires on a literal; they say nothing about how it behaves on a realistic population.

## Decision

`cmd/simulate` generates labelled traffic: customers with different spending levels, rent, friends, new shops and the occasional big purchase, plus fraud cases of each pattern. It sends them as signed ledger events, reads back the alerts, and reports per-pattern recall, how many fraudulent payments got through before the first alert, the false positive rate on ordinary payments, and alert precision. A 30-day warm-up gives every customer history before measuring starts, as a live system would have.

CI runs it on every push with a fixed seed and fails if recall on any gated pattern drops below 90% or the false positive rate rises above 0.5%. The report is published to the job summary.

Patterns the rules aren't designed to catch are generated too, marked as not gated, and shown in the report, so the blind spots stay visible.

A second mode drives the real payments-ledger through its API, so the signed outbox, the webhook and the service are tested together.

## Consequences

- Tuning a threshold is an experiment with a number attached, not a guess.
- The generator is synthetic: it proves the rules separate the patterns it models, not that those patterns match a particular bank's customers. Real labelled outcomes from resolved alerts are the next source of truth.
