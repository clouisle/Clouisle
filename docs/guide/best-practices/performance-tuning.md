# Performance Tuning

Performance optimization tips.

## Model Selection

Choose from models that are enabled and authorized for the team. Do not assume a fixed GPT-3.5/GPT-4 speed or quality ranking: measure representative prompts for latency, answer quality, context capacity, and cost in your deployment.

## Caching Strategies

- Cache only data with a clear invalidation policy.
- JWT is the primary session mechanism; Redis supports token blacklist and optional single-session state, in addition to Celery brokering, rate limits, and temporary caches.
- Do not add a global LLM response cache unless the prompt, model, team permissions, tools, and freshness requirements make reuse safe. Current runtime caching focuses on workflow definitions and deterministic node results rather than universal LLM responses.

## Database Optimization

- Add indexes on fields used by frequent filters and joins
- Use connection pooling appropriate to the deployment
- Measure query plans and retrieval latency before changing schema or cache settings

## Workflow Runtime

- Bound every loop. The editor defaults to 10 iterations and the executor caps loops at 1000.
- Use an Iteration node for array/object batches and make termination conditions explicit.
