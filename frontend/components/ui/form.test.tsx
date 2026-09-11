import { describe, expect, test } from "bun:test"
import * as React from "react"
import { useForm } from "react-hook-form"
import { renderToStaticMarkup } from "react-dom/server"
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
  useFormField,
} from "@/components/ui/form"

function TestForm({ defaultValues = { username: "testuser" }, hasError = false }: { defaultValues?: { username: string }, hasError?: boolean }) {
  const form = useForm({
    defaultValues,
    errors: hasError ? { username: { type: "required", message: "Username is required" } } : {},
  })

  return (
    <Form {...form}>
      <form>
        <FormField
          control={form.control}
          name="username"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Username</FormLabel>
              <FormControl>
                <input {...field} placeholder="Enter username" />
              </FormControl>
              <FormDescription>Your public username.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </form>
    </Form>
  )
}

function BareControlTest() {
  const form = useForm({ defaultValues: { bio: "" } })
  return (
    <Form {...form}>
      <FormField
        control={form.control}
        name="bio"
        render={() => (
          <FormItem>
            <FormControl>
              plain text string
            </FormControl>
          </FormItem>
        )}
      />
    </Form>
  )
}

function InnerProbe() {
  useFormField()
  return <div>probe</div>
}

function OutOfContextTest() {
  const form = useForm()
  return (
    <Form {...form}>
      <InnerProbe />
    </Form>
  )
}
describe("Form UI primitives", () => {
  test("renders form control with associated id, aria, and label", () => {
    const html = renderToStaticMarkup(<TestForm />)
    expect(html).toContain("Username")
    expect(html).toContain("Your public username.")
    expect(html).toContain("placeholder=\"Enter username\"")
    expect(html).toContain("aria-invalid=\"false\"")
    expect(html).toContain("aria-describedby=")
  })

  test("renders form message when validation fails", () => {
    const html = renderToStaticMarkup(<TestForm hasError />)
    expect(html).toContain("Username is required")
    expect(html).toContain("aria-invalid=\"true\"")
  })
  test("renders fallback div when children is not a valid element", () => {
    const html = renderToStaticMarkup(<BareControlTest />)
    expect(html).toContain("plain text string")
    expect(html).toContain("data-slot=\"form-control\"")
  })

  test("throws error when useFormField is called out of context", () => {
    expect(() => {
      renderToStaticMarkup(<OutOfContextTest />)
    }).toThrow("useFormField should be used within <FormField>")
  })
})
