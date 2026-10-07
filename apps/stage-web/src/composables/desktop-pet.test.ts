import type { EffectScope } from 'vue'

import type { AiriDesktopBridge, DesktopPetState } from './desktop-pet'

import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick } from 'vue'

import { useDesktopPet } from './desktop-pet'

describe('native desktop pet state', () => {
  let scope: EffectScope | undefined

  afterEach(() => {
    scope?.stop()
    scope = undefined
    delete window.airiDesktop
    window.history.replaceState({}, '', '/')
  })

  function mountDesktop(bridge?: AiriDesktopBridge) {
    window.airiDesktop = bridge
    scope = effectScope()
    return scope.run(() => useDesktopPet())!
  }

  function createBridge(initialMode: DesktopPetState['mode'] = 'window') {
    let current: DesktopPetState = { mode: initialMode, alwaysOnTop: true, clickThrough: false }
    let listener: ((next: DesktopPetState) => void) | undefined
    const unsubscribe = vi.fn()
    const publish = (next: Partial<DesktopPetState>) => {
      current = { ...current, ...next }
      listener?.(current)
    }
    const bridge: AiriDesktopBridge = {
      getState: vi.fn(async () => current),
      setMode: vi.fn(async mode => publish({ mode })),
      setAlwaysOnTop: vi.fn(async alwaysOnTop => publish({ alwaysOnTop })),
      setClickThrough: vi.fn(async clickThrough => publish({ clickThrough })),
      openSettings: vi.fn(async () => publish({ mode: 'window', clickThrough: false })),
      onStateChanged: vi.fn((callback) => {
        listener = callback
        return unsubscribe
      }),
    }
    return { bridge, publish, unsubscribe }
  }

  it('does not expose native pet controls for a URL parameter in an ordinary browser', async () => {
    window.history.replaceState({}, '', '/?desktopPet=1')
    const desktop = mountDesktop()
    await nextTick()
    expect(desktop.available).toBe(false)
    expect(desktop.isDesktopPet.value).toBe(false)
    expect(document.documentElement.classList.contains('airi-desktop-pet')).toBe(false)
  })

  it('follows native menu mode changes without navigation or localStorage changes', async () => {
    const native = createBridge()
    const desktop = mountDesktop(native.bridge)
    const storageBefore = { ...window.localStorage }
    await nextTick()
    expect(document.documentElement.classList.contains('airi-desktop-window')).toBe(true)
    native.publish({ mode: 'pet' })
    await nextTick()
    expect(desktop.isDesktopPet.value).toBe(true)
    expect(document.documentElement.classList.contains('airi-desktop-pet')).toBe(true)
    expect(document.documentElement.classList.contains('airi-desktop-window')).toBe(false)
    expect(window.location.pathname).toBe('/')
    expect({ ...window.localStorage }).toEqual(storageBefore)
    scope?.stop()
    expect(native.unsubscribe).toHaveBeenCalledOnce()
    expect(document.documentElement.classList.contains('airi-desktop-pet')).toBe(false)
  })

  it('reads back click-through and pin changes from the native window', async () => {
    const native = createBridge('pet')
    const desktop = mountDesktop(native.bridge)
    await nextTick()
    await desktop.setAlwaysOnTop(false)
    await desktop.setClickThrough(true)
    expect(desktop.state.value.alwaysOnTop).toBe(false)
    expect(desktop.state.value.clickThrough).toBe(true)
    native.publish({ clickThrough: false })
    expect(desktop.state.value.clickThrough).toBe(false)
    await desktop.openSettings()
    expect(desktop.state.value.mode).toBe('window')
  })

  it('keeps native errors visible and releases the pending action', async () => {
    const native = createBridge()
    native.bridge.setMode = vi.fn().mockRejectedValue(new Error('Native window unavailable'))
    const desktop = mountDesktop(native.bridge)
    await nextTick()
    await desktop.setMode('pet')
    expect(desktop.error.value).toBe('Native window unavailable')
    expect(desktop.busy.value).toBe(false)
    expect(desktop.isDesktopPet.value).toBe(false)
  })
})
