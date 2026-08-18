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
