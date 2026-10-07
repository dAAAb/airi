import type { VRM } from '@pixiv/three-vrm'
import type { Object3D } from 'three'

import { Euler, Quaternion } from 'three'

/** Authored, local choreography. The LLM selects a name; it never writes joint code. */
export const semanticMotionDurations = {
  nod: 1.8,
  shake: 1.8,
  wave: 3,
  bow: 2.4,
  celebrate: 3,
  dance: 4.8,
  sway: 4,
} as const
export type SemanticMotionName = keyof typeof semanticMotionDurations

type BoneName = Parameters<VRM['humanoid']['getNormalizedBoneNode']>[0]
type JointRotation = readonly [BoneName, number, number, number]

// Choreography uses VRM1 coordinates: +Z forward, -X character-right, +Y up.
function sampleMotion(name: SemanticMotionName, t: number): JointRotation[] {
  const beat = Math.sin(t * Math.PI * 3)
  switch (name) {
    case 'nod':
      return [['head', 0.22 * Math.sin(t * Math.PI * 3), 0, 0]]
    case 'shake':
      return [['head', 0, 0.28 * Math.sin(t * Math.PI * 3), 0]]
    case 'bow':
      return [['spine', 0.22, 0, 0], ['head', 0.18, 0, 0]]
    case 'wave':
      return [
        ['rightUpperArm', 0, -0.25, -1.45],
        ['rightLowerArm', 0, -0.55, -0.5],
        ['rightHand', 0.25 * beat, 0, 0.2 * beat],
        ['head', 0, 0, -0.06],
      ]
    case 'celebrate':
      return [
        ['leftUpperArm', 0, 0.15, 1.35 + 0.1 * beat],
        ['rightUpperArm', 0, -0.15, -1.35 - 0.1 * beat],
        ['leftLowerArm', 0, 0.2, 0.5],
        ['rightLowerArm', 0, -0.2, -0.5],
        ['spine', 0, 0, 0.05 * beat],
      ]
    case 'dance': {
      // Short side-to-side groove: hips stay in place, no jumps or foot translation.
      const groove = Math.sin(t * Math.PI * 2.5)
      return [
        ['spine', 0.04 * beat, 0.14 * groove, 0.1 * groove],
        ['chest', 0, -0.08 * groove, -0.05 * groove],
        ['head', 0, -0.06 * groove, -0.06 * groove],
        ['leftUpperArm', 0.1 * groove, 0, 0.7 + 0.18 * groove],
        ['rightUpperArm', -0.1 * groove, 0, -0.7 + 0.18 * groove],
        ['leftLowerArm', 0, 0.25, 0.35 + 0.12 * beat],
        ['rightLowerArm', 0, -0.25, -0.35 + 0.12 * beat],
      ]
    }
    case 'sway':
      return [['spine', 0, 0.08 * Math.sin(t * Math.PI), 0.1 * Math.sin(t * Math.PI)], ['head', 0, 0, -0.05 * Math.sin(t * Math.PI)]]
  }
}

function isMotionName(name: string): name is SemanticMotionName {
  return Object.hasOwn(semanticMotionDurations, name)
}

/**
 * Overlay joint rotations on the current idle pose without accumulating offsets.
 * Call restore() before the animation mixer, then update() before humanoid.update().
 * Missing optional bones are skipped. No expressions, root positions or scales are changed.
 */
export function createVrmSemanticMotion() {
  let active: { name: SemanticMotionName, elapsed: number, intensity: number } | undefined
  const previousPose = new Map<Object3D, Quaternion>()
  const rotation = new Euler()
  const offset = new Quaternion()

  function restore() {
    for (const [bone, quaternion] of previousPose)
      bone.quaternion.copy(quaternion)
    previousPose.clear()
  }

  function stop() {
    restore()
    active = undefined
  }

  function play(name: string, intensity = 1) {
    const normalized = name.trim().toLowerCase()
    if (normalized === 'idle' || normalized === 'stop') {
      stop()
      return true
    }
    if (!isMotionName(normalized) || !Number.isFinite(intensity) || intensity <= 0)
      return false

    // A repeated ACT within the same utterance must not restart a gesture forever.
    if (active?.name === normalized)
      return true
    restore()
    active = { name: normalized, elapsed: 0, intensity: Math.min(1, intensity) }
    return true
  }

  function update(vrm: Pick<VRM, 'humanoid' | 'meta'>, delta: number) {
    // Also make direct callers safe if they do not run a mixer between frames.
    restore()
    if (!active || !Number.isFinite(delta) || delta < 0)
      return
    active.elapsed += delta
    const duration = semanticMotionDurations[active.name]
    if (active.elapsed >= duration) {
      active = undefined
      return
    }
    const edge = Math.min(1, active.elapsed / 0.3, (duration - active.elapsed) / 0.45)
    const envelope = edge * edge * (3 - 2 * edge) * active.intensity
    for (const [name, x, y, z] of sampleMotion(active.name, active.elapsed)) {
      const bone = vrm.humanoid.getNormalizedBoneNode(name)
      if (!bone)
        continue
      previousPose.set(bone, bone.quaternion.clone())
      offset.setFromEuler(rotation.set(x * envelope, y * envelope, z * envelope))
      // Match three-vrm-animation's VRM0 retargeting: its forward/right axes are reversed.
      // Normalized bones remove rest rotations, but preserve this version-dependent coordinate frame.
      if (vrm.meta.metaVersion === '0') {
        offset.x *= -1
        offset.z *= -1
      }
      bone.quaternion.multiply(offset)
    }
  }

  return {
    play,
    update,
    restore,
    stop,
    get activeMotion() {
      return active?.name
    },
  }
}
