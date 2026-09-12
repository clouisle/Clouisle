# Form Architecture Migration Plan: Moving to React Hook Form + Zod

## Background & Objectives

Currently, forms across Clouisle manage their state via manual `useState`, custom error mapping dictionaries (`ValidationPathMap`), manual input clear callbacks (`clearValidationError`), and varying error handling strategies. This results in:
1. Forgotten fields in error path maps causing silent validation failures.
2. Inconsistent error display (some with `<FieldError>`, some with plain `toast`, some re-throwing uncaught errors).
3. Duplicated boilerplate for touched, dirty, and invalid input states.

**Objective**: Systematically migrate all forms across the application to the shadcn-standard **React Hook Form (`react-hook-form`) + Zod (`@hookform/resolvers/zod`)** architecture with a unified server-side error bridge (`setFormServerErrors`).

---

## Architecture Foundation (Phase 0)

Before migrating individual forms, establish the shared infrastructure:
1. **Dependencies**: Add `react-hook-form` and `@hookform/resolvers` (Zod v3/v4 compatible).
2. **UI Primitives**: Add `@/components/ui/form.tsx` following the shadcn standard:
   - `Form` (FormProvider)
   - `FormField` (Controller wrapper)
   - `FormItem`
   - `FormLabel`
   - `FormControl`
   - `FormDescription`
   - `FormMessage` (integrated with `<FieldError>`)
3. **Server Validation Bridge** (`@/lib/validation.ts`):
   ```typescript
   export function applyServerErrors<T extends FieldValues>(
     form: UseFormReturn<T>,
     error: unknown,
     pathMap?: Record<string, Path<T>>
   ): boolean
   ```
   - Automatically maps backend 422 `{ errors: { field: ["msg"] } }` to `form.setError(field, { message })`.
   - Displays unmapped/general errors via `toast.error()`.

---

## Form Inventory & Migration Checklist

### 1. Capabilities & Custom Tools (6 forms)
- [ ] `frontend/app/(platform)/app/capabilities/_components/http-tool-dialog.tsx`
- [ ] `frontend/app/(dashboard)/capabilities/_components/http-tool-dialog.tsx`
- [ ] `frontend/app/(platform)/app/capabilities/_components/mcp-tool-dialog.tsx`
- [ ] `frontend/app/(dashboard)/capabilities/_components/mcp-tool-dialog.tsx`
- [ ] `frontend/app/(platform)/app/capabilities/_components/database-tool-dialog.tsx`
- [ ] `frontend/app/(platform)/app/capabilities/_components/tool-config-dialog.tsx`

### 2. Knowledge Bases (4 forms)
- [ ] `frontend/app/(platform)/app/kb/_components/kb-dialog.tsx`
- [ ] `frontend/app/(dashboard)/knowledge-bases/_components/knowledge-base-dialog.tsx`
- [ ] `frontend/app/(platform)/app/kb/[id]/_components/import-url-dialog.tsx`
- [ ] `frontend/app/(dashboard)/knowledge-bases/[id]/_components/import-url-dialog.tsx`

### 3. Authentication & Account (5 forms)
- [ ] `frontend/app/(auth)/login/_components/login-form.tsx`
- [ ] `frontend/app/(auth)/register/_components/register-form.tsx`
- [ ] `frontend/app/(auth)/change-password/page.tsx`
- [ ] `frontend/app/(auth)/forgot-password/_components/forgot-password-form.tsx`
- [ ] `frontend/app/(auth)/reset-password/_components/reset-password-by-token-form.tsx`

### 4. Access & User Administration (9 forms)
- [ ] `frontend/app/(dashboard)/users/_components/user-dialog.tsx`
- [ ] `frontend/app/(dashboard)/users/_components/send-notification-dialog.tsx`
- [ ] `frontend/app/(dashboard)/roles/_components/role-dialog.tsx`
- [ ] `frontend/app/(dashboard)/permissions/_components/permission-dialog.tsx`
- [ ] `frontend/app/(dashboard)/teams/_components/team-dialog.tsx`
- [ ] `frontend/app/(dashboard)/teams/_components/team-models-tab.tsx`
- [ ] `frontend/app/(dashboard)/api-keys/_components/api-key-dialog.tsx`
- [ ] `frontend/app/(platform)/app/api-keys/_components/api-key-dialog.tsx`
- [ ] `frontend/app/(dashboard)/memories/_components/entity-dialog.tsx`

### 5. Site Settings (11 forms)
- [ ] `frontend/app/(dashboard)/site-settings/page.tsx` (General settings)
- [ ] `frontend/app/(dashboard)/site-settings/security/page.tsx` (Security & allowlists)
- [ ] `frontend/app/(dashboard)/site-settings/storage/page.tsx` (Storage settings)
- [ ] `frontend/app/(dashboard)/site-settings/memory/page.tsx` (Memory settings)
- [ ] `frontend/app/(dashboard)/site-settings/sso/_components/provider-dialog.tsx` (SSO provider)
- [ ] `frontend/app/(dashboard)/site-settings/notifications/_components/email-settings.tsx`
- [ ] `frontend/app/(dashboard)/site-settings/notifications/_components/dingtalk-settings.tsx`
- [ ] `frontend/app/(dashboard)/site-settings/notifications/_components/feishu-settings.tsx`
- [ ] `frontend/app/(dashboard)/site-settings/notifications/_components/wechat-settings.tsx`
- [ ] `frontend/app/(dashboard)/site-settings/notifications/_components/slack-settings.tsx`
- [ ] `frontend/app/(dashboard)/site-settings/notifications/_components/webhook-settings.tsx`

### 6. AI Models (1 form)
- [ ] `frontend/app/(dashboard)/models/_components/model-dialog.tsx`

### 7. Apps & Workflows (13 forms)
- [ ] `frontend/app/(platform)/app/apps/_components/app-create-dialog.tsx`
- [ ] `frontend/app/(platform)/app/apps/[id]/_components/agent-config-form.tsx`
- [ ] `frontend/app/(platform)/app/apps/[id]/_components/embed-config-dialog.tsx`
- [ ] `frontend/app/(platform)/app/apps/[id]/_components/variable-editor.tsx`
- [ ] `frontend/app/(platform)/app/apps/workflow/[id]/_components/workflow-settings-drawer.tsx`
- [ ] `frontend/app/(platform)/app/apps/workflow/[id]/_components/workflow-run-drawer.tsx`
- [ ] `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config-drawer.tsx`
- [ ] `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/dialogs/parameter-edit-dialog.tsx`
- [ ] `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/dialogs/code-input-dialog.tsx`
- [ ] `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/dialogs/template-input-dialog.tsx`
- [ ] `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/dialogs/file-to-url-input-dialog.tsx`
- [ ] `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/configs/loop-node-config.tsx`
- [ ] `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/configs/pause-node-config.tsx`

---

## Execution Standards for Each Form Migration

1. Define Zod schema matching API contracts.
2. Replace `useState` bundles with `useForm<FormValues>({ resolver: zodResolver(schema), defaultValues })`.
3. Wrap form fields with `<FormField control={form.control} name="..." render={({ field }) => (...) } />`.
4. Ensure `<FormMessage />` renders errors inline.
5. In submission `catch`, call `applyServerErrors(form, error, pathMap)`.
6. Run corresponding test file to verify 100% pass rate and coverage invariant.
