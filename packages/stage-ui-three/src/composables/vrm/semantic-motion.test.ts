import type { VRM } from '@pixiv/three-vrm'

import { VRMHumanoid } from '@pixiv/three-vrm'
import { Object3D, Quaternion, Vector3 } from 'three'
import { describe, expect, it } from 'vitest'

import { createVrmSemanticMotion, semanticMotionDurations } from './semantic-motion'

function fixture() {
  const bones = new Map<string, Object3D>()
  for (const name of ['head', 'spine', 'chest', 'leftUpperArm', 'rightUpperArm', 'leftLowerArm', 'rightLowerArm', 'rightHand'])
    bones.set(name, new Object3D())
  return {
    bones,
    vrm: { meta: { metaVersion: '1' }, humanoid: { getNormalizedBoneNode: (name: string) => bones.get(name) ?? null } } as Pick<VRM, 'humanoid' | 'meta'>,
  }
}

function sameRotation(actual: Quaternion, expected: Quaternion) {
  expect(Math.abs(actual.dot(expected))).toBeCloseTo(1, 8)
}

function directionFixture(version: '0' | '1', yaw = 0) {
  const scene = new Object3D()
  const rightSign = version === '0' ? 1 : -1
  const bones: Record<string, { node: Object3D }> = {}
  function add(name: string, parent: string | undefined, x: number, y: number, z = 0) {
    const node = new Object3D()
    node.name = name
    node.position.set(x, y, z)
    ;(parent ? bones[parent].node : scene).add(node)
    bones[name] = { node }
  }
  add('hips', undefined, 0, 1)
  add('spine', 'hips', 0, 0.2)
  add('chest', 'spine', 0, 0.2)
  add('head', 'chest', 0, 0.25)
  for (const side of ['left', 'right']) {
    const direction = side === 'right' ? rightSign : -rightSign
    add(`${side}UpperArm`, 'chest', direction * 0.15, 0.1)
    add(`${side}LowerArm`, `${side}UpperArm`, direction * 0.3, 0)
    add(`${side}Hand`, `${side}LowerArm`, direction * 0.25, 0)
    add(`${side}UpperLeg`, 'hips', direction * 0.1, -0.05)
    add(`${side}LowerLeg`, `${side}UpperLeg`, 0, -0.4)
    add(`${side}Foot`, `${side}LowerLeg`, 0, -0.4, -rightSign * 0.05)
  }
  scene.updateMatrixWorld(true)
  const humanoid = new VRMHumanoid({
    ...bones,
    hips: bones.hips,
    spine: bones.spine,
    head: bones.head,
    leftUpperArm: bones.leftUpperArm,
    leftLowerArm: bones.leftLowerArm,
    leftHand: bones.leftHand,
    rightUpperArm: bones.rightUpperArm,
    rightLowerArm: bones.rightLowerArm,
    rightHand: bones.rightHand,
    leftUpperLeg: bones.leftUpperLeg,
    leftLowerLeg: bones.leftLowerLeg,
    leftFoot: bones.leftFoot,
    rightUpperLeg: bones.rightUpperLeg,
    rightLowerLeg: bones.rightLowerLeg,
    rightFoot: bones.rightFoot,
  })
  scene.add(humanoid.normalizedHumanBonesRoot)
  // Match equivalent relaxed arm poses in each version's source coordinate system.
  humanoid.getNormalizedBoneNode('rightUpperArm')!.rotation.z = -rightSign * 1.2
  humanoid.getNormalizedBoneNode('leftUpperArm')!.rotation.z = rightSign * 1.2
  scene.rotation.y = yaw
  const front = new Vector3(0, 0, -rightSign).applyQuaternion(scene.quaternion)
  const right = new Vector3(rightSign, 0, 0).applyQuaternion(scene.quaternion)
  function position(name: string) {
    humanoid.update()
    scene.updateMatrixWorld(true)
    return bones[name].node.getWorldPosition(new Vector3())
  }
  return {
    bones,
    front,
    right,
    position,
    vrm: { humanoid, meta: { metaVersion: version } } as Pick<VRM, 'humanoid' | 'meta'>,
  }
}

describe('local semantic VRM motion', () => {
  it('ignores unknown actions and non-finite intensity without interrupting a valid gesture', () => {
    const motion = createVrmSemanticMotion()
    expect(motion.play('wave')).toBe(true)
    expect(motion.play('https://example.org/dance.vrma')).toBe(false)
    expect(motion.play('toString')).toBe(false)
    expect(motion.play('dance', Number.NaN)).toBe(false)
    expect(motion.play('dance', Number.POSITIVE_INFINITY)).toBe(false)
    expect(motion.activeMotion).toBe('wave')
  })

  it('returns to the exact current idle pose, without accumulating rotations over repeated gestures', () => {
    const { bones, vrm } = fixture()
    const head = bones.get('head')!
    head.rotation.set(0.02, 0.03, 0.04)
    const baseline = head.quaternion.clone()
    const motion = createVrmSemanticMotion()
    for (let repeat = 0; repeat < 20; repeat++) {
      motion.play('nod')
      for (let i = 0; i < 130; i++) {
        motion.restore() // The animation mixer would write the idle pose here.
        motion.update(vrm, 1 / 60)
      }
      sameRotation(head.quaternion, baseline)
      expect(motion.activeMotion).toBeUndefined()
    }
  })

  it('lays the motion over newly animated idle rotations instead of freezing the pose', () => {
    const { bones, vrm } = fixture()
    const head = bones.get('head')!
    const motion = createVrmSemanticMotion()
    motion.play('nod')
    motion.update(vrm, 0.3)
    motion.restore()
    head.rotation.set(0.12, 0.15, 0.07)
    const animatedBaseline = head.quaternion.clone()
    motion.update(vrm, 0.05)
    expect(head.quaternion.angleTo(animatedBaseline)).toBeGreaterThan(0.01)
    motion.stop()
    sameRotation(head.quaternion, animatedBaseline)
  })

  it('clamps amplitude and leaves root position, scales and missing bones alone', () => {
    const { bones, vrm } = fixture()
    bones.delete('chest')
    const rootPosition = bones.get('spine')!.position.clone()
    const a = createVrmSemanticMotion()
    const b = createVrmSemanticMotion()
    a.play('dance', 10)
    a.update(vrm, 0.5)
    const clamped = bones.get('spine')!.quaternion.clone()
    a.stop()
    b.play('dance', 1)
    b.update(vrm, 0.5)
    sameRotation(bones.get('spine')!.quaternion, clamped)
    expect(bones.get('spine')!.position.equals(rootPosition)).toBe(true)
    expect(bones.get('spine')!.scale.toArray()).toEqual([1, 1, 1])
  })

  it.each(Object.keys(semanticMotionDurations))('bounds %s and restores all touched joints on idle', (name) => {
    const { bones, vrm } = fixture()
    const motion = createVrmSemanticMotion()
    expect(motion.play(name)).toBe(true)
    motion.update(vrm, 0.45)
    expect([...bones.values()].some(bone => bone.quaternion.angleTo(new Quaternion()) > 0.01)).toBe(true)
    motion.play(name) // The same ACT does not reset its timer.
    motion.update(vrm, 10)
    expect(motion.activeMotion).toBeUndefined()
    for (const bone of bones.values())
      sameRotation(bone.quaternion, new Quaternion())
  })

  it('stops immediately and can switch gesture without carrying the previous overlay', () => {
    const { bones, vrm } = fixture()
    const motion = createVrmSemanticMotion()
    motion.play('wave')
    motion.update(vrm, 0.5)
    motion.play('nod')
    sameRotation(bones.get('rightUpperArm')!.quaternion, new Quaternion())
    motion.update(vrm, 0.5)
    motion.play('stop')
    sameRotation(bones.get('head')!.quaternion, new Quaternion())
    expect(motion.activeMotion).toBeUndefined()
  })

  it.each(['0', '1'] as const)('moves the anatomical right hand upward on its own side in VRM%s, at any model yaw', (version) => {
    for (const yaw of [0, Math.PI / 2, Math.PI]) {
      const fixture = directionFixture(version, yaw)
      const rightBefore = fixture.position('rightHand')
      const leftBefore = fixture.position('leftHand')
      const motion = createVrmSemanticMotion()
      motion.play('wave')
      motion.update(fixture.vrm, 0.6)
      const hand = fixture.position('rightHand')
      expect(hand.y - rightBefore.y).toBeGreaterThan(0.5)
      expect(hand.clone().sub(fixture.position('rightUpperArm')).dot(fixture.right)).toBeGreaterThan(0.3)
      expect(fixture.position('leftHand').distanceTo(leftBefore)).toBeLessThan(1e-8)
    }
  })

  it.each(['0', '1'] as const)('bows toward the character front in VRM%s, independently of the camera or model yaw', (version) => {
    for (const yaw of [0, Math.PI / 2, Math.PI]) {
      const fixture = directionFixture(version, yaw)
      const before = fixture.position('head')
      const motion = createVrmSemanticMotion()
      motion.play('bow')
      motion.update(fixture.vrm, 0.6)
      expect(fixture.position('head').sub(before).dot(fixture.front)).toBeGreaterThan(0.09)
    }
  })

  it.each(Object.keys(semanticMotionDurations))('produces matching world-space %s poses for equivalent VRM0 and VRM1 avatars', (name) => {
    const v0 = directionFixture('0')
    const v1 = directionFixture('1', Math.PI)
    const a = createVrmSemanticMotion()
    const b = createVrmSemanticMotion()
    a.play(name)
    b.play(name)
    for (const delta of [0.2, 0.4, 0.5]) {
      a.update(v0.vrm, delta)
      b.update(v1.vrm, delta)
      for (const bone of ['head', 'rightHand', 'leftHand'])
        expect(v0.position(bone).distanceTo(v1.position(bone))).toBeLessThan(1e-7)
    }
  })
})
