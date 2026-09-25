# Workflow Design Patterns

Common workflow design patterns.

## Sequential Pattern

Linear execution: A → B → C → D

**Use case**: Document processing pipeline

## Parallel Pattern

Concurrent execution: A → (B, C, D) → E

**Use case**: Multi-source data aggregation

## Conditional Pattern

Branching logic: A → if(condition) → B else C

**Use case**: Content routing

## Decision Routing Pattern

Typed branching: A → decide(model, state) → one of {option/level handles, fallback}

**Use case**: Judgements that need a calibrated answer rather than free text — approval, refund eligibility, priority scoring, yes/no gating.

Use a Decision node with a `decision` model (TypeSafe AI) instead of asking an LLM node to "reply with one of these labels":

- Ask one typed question per node — `choice` (1–255 options), `score` (2–10 ordered levels), or `noul` (yes/no probability). Outputs carry the answer, the probability distribution, and a confidence derived from it.
- Every option or level becomes a branch handle; connect the branch you take for each answer and keep the fallback branch wired so low-confidence answers have a defined path.
- Set a confidence threshold when downstream steps assume a confident answer; answers below it route to the fallback instead of the selected branch.
- `noul` routes to `yes` at probability ≥ 0.5 and returns no confidence value, so add a threshold only to `choice`/`score` questions.

## Loop Pattern

Iterative execution: A → while(condition) → B → A

**Use case**: Batch processing and bounded retries

Configure an explicit termination condition and a finite cap. The workflow editor defaults the loop limit to 10; the executor enforces a maximum of 1000 iterations. Use an Iteration node when processing an array or object so each item has a clear input and output rather than relying on an unbounded loop.

**Safety checklist**:
- Set a cap appropriate to the input size
- Ensure the condition can make progress toward termination
- Handle empty input and per-item failures
- Keep retries separate from business iteration

## Related documentation

- [Agent vs Workflow](../concepts/agent-vs-workflow.md) - Choosing the right abstraction
- [System Architecture](../concepts/architecture.md) - Component overview
- [Prompt Engineering](./prompt-engineering.md) - Prompt-writing guidance
