import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'
import { parseDocument } from 'yaml'

describe('motion settings locale paths', () => {
  it.each([
    ['en', 'Motion', 'Modules'],
    ['zh-Hant', '動作', '模組'],
  ])('places %s motion keys in modules without changing data reset labels', (locale, title, dataTitle) => {
    const document = parseDocument(readFileSync(new URL(`../src/locales/${locale}/settings.yaml`, import.meta.url), 'utf8'))
    expect(document.errors).toEqual([])
    expect(document.getIn(['pages', 'modules', 'motion', 'title'])).toBe(title)
    expect(document.getIn(['pages', 'modules', 'motion', 'status', 'ready'])).toBeTypeOf('string')
    expect(document.getIn(['pages', 'modules', 'motion', 'decisions', 'enable'])).toBeTypeOf('string')
    expect(document.getIn(['pages', 'modules', 'motion', 'decisions', 'confidence'])).toBeTypeOf('string')
    expect(document.getIn(['pages', 'data', 'sections', 'modules', 'title'])).toBe(dataTitle)
    expect(document.getIn(['pages', 'data', 'motion'])).toBeUndefined()
  })
})
