# Fix Duplicate Input Parameter Names Design Document

## Background & Goals

**Problem**: Currently, workflow nodes (code, llm, template, tool, subworkflow) can have duplicate input parameter names. When `resolve_inputs()` processes these, later parameters silently overwrite earlier ones, causing data loss and confusing behavior.

**Success Criteria**:
- Duplicate input parameter names are detected and rejected
- Clear error messages guide users to fix the issue
- Validation happens at both config validation and runtime

## High-Level Design

The fix will add duplicate name detection in two places:
1. **Base executor `resolve_inputs()`** - Runtime validation with clear error
2. **Individual node `validate_config()`** - Config-time validation for early feedback

Affected node types: code, llm, template, tool, subworkflow

## Implementation Plan

### Stage 1: Add Runtime Validation in Base Executor
**Files modified**: `backend/app/services/workflow/executor.py`

**Specific logic**:
- In `resolve_inputs()` method (line 92-134), before the loop:
  - Extract all `name` values from `input_mappings`
  - Check for duplicates using set comparison
  - If duplicates found, raise exception with duplicate names listed

**Validation**: 
- Create a test workflow with duplicate input names
- Verify execution fails with clear error message

### Stage 2: Add Config Validation in Code Node
**Files modified**: `backend/app/services/workflow/executors/code.py`

**Specific logic**:
- In `validate_config()` method (line 191-215), add check:
  - Extract input names from `config.get("inputs", [])`
  - Detect duplicates
  - Append error message to errors list

**Validation**:
- Test code node config validation rejects duplicate names
- Verify error message is clear and actionable

### Stage 3: Add i18n Error Messages
**Files modified**: 
- `backend/app/core/i18n.py` (add new translation keys)
- `backend/app/core/i18n_legacy.py` (if needed for legacy support)

**Specific logic**:
- Add translation key: `duplicate_input_parameter_names`
- English: "Duplicate input parameter names found: {names}"
- Chinese: "发现重复的输入参数名称：{names}"

**Validation**:
- Verify both English and Chinese messages display correctly
- Test with actual duplicate names

### Stage 4: Testing
**Files modified**: None (manual testing)

**Test cases**:
1. **Happy path**: Node with unique input names executes successfully
2. **Duplicate detection**: Node with duplicate names fails validation
3. **Error message**: Error clearly lists duplicate parameter names
4. **Multiple duplicates**: Correctly identifies all duplicate names

**Validation**:
- Run workflow with test cases
- Check logs for proper error messages
- Verify no regression in existing workflows

## Testing Strategy

### Happy Path
- Create code node with inputs: `[{name: "x"}, {name: "y"}]`
- Execute and verify success

### Error Path
- Create code node with inputs: `[{name: "x"}, {name: "x"}]`
- Verify validation error with message listing "x"
- Create node with inputs: `[{name: "a"}, {name: "b"}, {name: "a"}, {name: "b"}]`
- Verify error lists "a, b"

### Regression
- Test existing workflows with unique input names
- Verify no impact on other node types

## Risks & Mitigation

**Risk**: Breaking existing workflows that accidentally have duplicates
**Mitigation**: This is actually desired behavior - we want to catch these bugs

**Risk**: Performance impact from duplicate checking
**Mitigation**: Duplicate check is O(n) with small n (typically < 10 inputs), negligible impact

**Risk**: Inconsistent validation across node types
**Mitigation**: Base executor validation catches all cases at runtime
