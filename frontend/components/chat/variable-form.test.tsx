import { afterEach, beforeEach, describe, expect, it, mock } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'

GlobalRegistrator.register()

import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import * as React from 'react'

const uploadFile = mock(async (file: File) => ({ url: `/uploads/${file.name}` }))

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) => {
    const messages: Record<string, string> = {
      'chat.variables.fileTooLarge': `File is too large. Max ${values?.maxSize} MB`,
      'chat.variables.fileUploadFailed': 'Upload failed',
      'chat.variables.selectFiles': 'Select files',
      'chat.variables.selectFile': 'Select file',
      'chat.variables.startChat': 'Start chat',
      'chat.variables.tooManyFiles': `Too many files. Max ${values?.maxFiles}`,
      'chat.variables.uploading': 'Uploading',
      'common.invalidFileType': 'Invalid file type',
      'common.invalidFileTypeWithAllowed': `Invalid file type. Allowed: ${values?.allowed}`,
      'common.invalidJSON': 'Invalid JSON',
      'common.required': 'Required',
    }

    return messages[`${namespace}.${key}`] ?? key
  },
}))

mock.module('@/lib/api/upload', () => ({
  uploadApi: { uploadFile },
}))

import { VariableForm } from './variable-form'

afterEach(() => {
  cleanup()
  uploadFile.mockClear()
})

type Variable = React.ComponentProps<typeof VariableForm>['variables'][number]

function StatefulForm({
  variables,
  initialValues = {},
  fieldErrors,
  onSubmit,
}: {
  variables: Variable[]
  initialValues?: Record<string, unknown>
  fieldErrors?: Record<string, string>
  onSubmit?: () => void
}) {
  const [values, setValues] = React.useState(initialValues)

  return (
    <VariableForm
      variables={variables}
      values={values}
      onChange={setValues}
      onSubmit={onSubmit}
      fieldErrors={fieldErrors}
    />
  )
}

function fileInput(container: HTMLElement) {
  const input = container.querySelector('input[type="file"]')
  if (!(input instanceof HTMLInputElement)) {
    throw new Error('file input not found')
  }
  return input
}

describe('VariableForm', () => {
  beforeEach(() => {
    uploadFile.mockImplementation(async (file: File) => ({ url: `/uploads/${file.name}` }))
  })

  it('blocks submit for a missing required text value and renders field errors', () => {
    const onSubmit = mock()
    const variables: Variable[] = [{ name: 'prompt', label: 'Prompt', type: 'text', required: true }]
    const onChange = mock()

    const view = render(
      <VariableForm
        variables={variables}
        values={{}}
        onChange={onChange}
        fieldErrors={{ prompt: 'Server rejected prompt' }}
        onSubmit={onSubmit}
      />
    )

    const submit = view.getByRole('button', { name: 'Start chat' })
    expect(submit).toHaveProperty('disabled', true)
    expect(view.getAllByText('Server rejected prompt')).toHaveLength(1)

    fireEvent.click(submit)

    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('updates submit readiness for required text and array validation', () => {
    const onSubmit = mock()
    const onChange = mock()
    const variables: Variable[] = [
      { name: 'prompt', label: 'Prompt', type: 'text', required: true },
      { name: 'items', label: 'Items', type: 'array', required: true },
    ]

    const view = render(
      <VariableForm variables={variables} values={{ prompt: '', items: 'not json' }} onChange={onChange} onSubmit={onSubmit} />
    )

    expect(view.getByRole('button', { name: 'Start chat' })).toHaveProperty('disabled', true)

    view.rerender(
      <VariableForm variables={variables} values={{ prompt: 'hello', items: ['one'] }} onChange={onChange} onSubmit={onSubmit} />
    )

    const submit = view.getByRole('button', { name: 'Start chat' })
    expect(submit).toHaveProperty('disabled', false)
    fireEvent.click(submit)

    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('enforces multi-image count and size limits before upload', async () => {
    const { container } = render(
      <StatefulForm
        variables={[{
          name: 'photos',
          label: 'Photos',
          type: 'images',
          required: true,
          fileConfig: { maxFiles: 2, maxSize: 1 },
        }]}
        initialValues={{ photos: ['/uploads/existing.png'] }}
      />
    )

    const input = fileInput(container)

    fireEvent.change(input, {
      target: { files: [new File(['a'], 'one.png'), new File(['b'], 'two.png')] },
    })

    expect(container.ownerDocument.body.textContent).toContain('Too many files. Max 2')
    expect(uploadFile).not.toHaveBeenCalled()

    fireEvent.change(input, {
      target: { files: [new File([new Uint8Array(1024 * 1024 + 1)], 'huge.png', { type: 'image/png' })] },
    })

    expect(container.ownerDocument.body.textContent).toContain('File is too large. Max 1 MB')
    expect(uploadFile).not.toHaveBeenCalled()
  })

  it('uploads multiple files, disables at max count, and removal restores submit readiness', async () => {
    const onSubmit = mock()
    const view = render(
      <StatefulForm
        variables={[{
          name: 'docs',
          label: 'Docs',
          type: 'files',
          required: true,
          fileConfig: { maxFiles: 2, maxSize: 1 },
        }]}
        onSubmit={onSubmit}
      />
    )
    const { container } = view

    const submit = view.getByRole('button', { name: 'Start chat' })
    expect(submit).toHaveProperty('disabled', true)

    fireEvent.change(fileInput(container), {
      target: { files: [new File(['a'], 'a.txt'), new File(['b'], 'b.txt')] },
    })

    await waitFor(() => expect(uploadFile).toHaveBeenCalledTimes(2))
    await view.findByText('a.txt')
    await view.findByText('b.txt')
    expect(view.getByRole('button', { name: 'Select files (2/2)' })).toHaveProperty('disabled', true)
    expect(submit).toHaveProperty('disabled', false)

    fireEvent.click(container.querySelectorAll('button[type="button"]')[1])

    await waitFor(() => expect(view.queryByText('a.txt')).toBeNull())
    expect(view.getByRole('button', { name: 'Select files (1/2)' })).toHaveProperty('disabled', false)
    expect(submit).toHaveProperty('disabled', false)

    fireEvent.click(container.querySelectorAll('button[type="button"]')[1])

    await waitFor(() => expect(view.queryByText('b.txt')).toBeNull())
    expect(submit).toHaveProperty('disabled', true)
  })
})
