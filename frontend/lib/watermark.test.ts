import { describe, expect, test } from 'bun:test'
import { DEFAULT_WATERMARK_CONTENT, renderWatermarkText } from './watermark'

const now = new Date(2024, 0, 5, 9, 7)

describe('renderWatermarkText', () => {
  test('replaces every supported placeholder with local date and time', () => {
    expect(
      renderWatermarkText(
        '{username}|{email}|{site_name}|{date}|{time}',
        { username: 'alice', email: 'alice@example.com', siteName: 'Acme', now }
      )
    ).toBe('alice|alice@example.com|Acme|2024-01-05|09:07')
  })

  test('leaves unknown placeholders literal and collapses whitespace', () => {
    expect(
      renderWatermarkText('  {username}   {role}  ', {
        username: 'alice',
        email: null,
        siteName: 'Acme',
        now,
      })
    ).toBe('alice {role}')
  })

  test('drops empty substitutions and falls back to the site name', () => {
    expect(
      renderWatermarkText('{username} {email}', { username: '', email: null, siteName: 'Acme', now })
    ).toBe('Acme')
    expect(
      renderWatermarkText('{username}', { username: null, email: null, siteName: '  ', now })
    ).toBe('Clouisle')
  })

  test('renders the default template when the template is empty', () => {
    expect(
      renderWatermarkText('', { username: 'alice', email: null, siteName: 'Acme', now })
    ).toBe(`alice 2024-01-05 09:07`)
    expect(DEFAULT_WATERMARK_CONTENT).toBe('{username} {date} {time}')
  })

  test('zero-pads single digit month, day, hour and minute', () => {
    expect(
      renderWatermarkText('{date} {time}', {
        username: null,
        email: null,
        siteName: null,
        now: new Date(2024, 8, 9, 3, 4),
      })
    ).toBe('2024-09-09 03:04')
  })
})
