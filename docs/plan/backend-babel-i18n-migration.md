## Feature: Backend Babel i18n migration
**Status**: Complete

### Stages
1. **Stage 1**: Introduce Babel-backed runtime behind `backend/app/core/i18n.py`
   - **Validation**: `t()` returns expected English/Chinese text; request header language still affects API response messages.
   - **Status**: Complete
2. **Stage 2**: Add compatibility fallback and initial locale resources
   - **Validation**: existing `success()`, `error()`, and `BusinessError(msg_key=...)` paths work unchanged; missing Babel entries safely fall back.
   - **Status**: Complete
3. **Stage 3**: Add migration tooling and checks
   - **Validation**: locale export/check scripts run successfully and catch placeholder/key mismatches.
   - **Status**: Complete
4. **Stage 4**: Update backend i18n docs
   - **Validation**: docs describe the Babel workflow and no longer tell developers to add keys directly to the runtime dict.
   - **Status**: Complete
