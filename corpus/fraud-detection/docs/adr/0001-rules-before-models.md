# 0001 Rules before models

## Context

Fraud detection is often pitched as a machine-learning problem. A model needs labelled outcomes (chargebacks, confirmed fraud) to learn from, and a new payments product has none. It also has to explain itself: an analyst clearing an alert, or a customer whose payment was held, needs to know why.

## Decision

Start with transparent rules over behavioural features, each giving a score and a human-readable reason, combined as independent evidence (`1 − Π(1 − sᵢ)`). Every alert records which rules fired and why. Analysts resolve alerts as `fraud` or `legitimate`, which is exactly the labelled data a model would need later.

## Consequences

- Each rule is cheap to explain, test and tune per currency.
- Rules miss what they weren't written for; the simulator reports those blind spots (see 0004) instead of hiding them.
- The resolution data builds up a training set. A model can later sit beside the rules as one more signal, scored in the same place and judged by the same simulator.
