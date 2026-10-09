import type { VRM } from '@pixiv/three-vrm'

import type { GeneratedMotionClip } from './generated-motion'

import { readFileSync } from 'node:fs'

import { VRMHumanoid } from '@pixiv/three-vrm'
import { Object3D, Vector3 } from 'three'
import { describe, expect, it } from 'vitest'

import { createVrmGeneratedMotion } from './generated-motion'

function fixture(version: '0' | '1', yaw = 0, sceneScale = 1, bodyScale = 1) {
  const scene = new Object3D()
  const sign = version === '1' ? 1 : -1
  const bones: Record<string, { node: Object3D }> = {}
  function add(name: string, parent: string | undefined, x: number, y: number, z = 0) {
    const node = new Object3D()
    node.position.set(x * sign, y, z * sign).multiplyScalar(bodyScale)
    ;(parent ? bones[parent].node : scene).add(node)
    bones[name] = { node }
  }
  add('hips', undefined, 0, 1)
  add('spine', 'hips', 0, 0.15)
  add('chest', 'spine', 0, 0.15)
  add('neck', 'chest', 0, 0.25)
  add('head', 'neck', 0, 0.15)
  for (const side of ['left', 'right']) {
    const x = side === 'left' ? 1 : -1
    add(`${side}UpperArm`, 'chest', x * 0.2, 0.2)
    add(`${side}LowerArm`, `${side}UpperArm`, x * 0.3, 0)
    add(`${side}Hand`, `${side}LowerArm`, x * 0.3, 0)
    add(`${side}UpperLeg`, 'hips', x * 0.1, 0)
    add(`${side}LowerLeg`, `${side}UpperLeg`, 0, -0.45)
    add(`${side}Foot`, `${side}LowerLeg`, 0, -0.45)
    add(`${side}Toes`, `${side}Foot`, 0, -0.03, 0.15)
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
  scene.rotation.y = yaw
  scene.scale.setScalar(sceneScale)
  const vrm = { humanoid, meta: { metaVersion: version } } as Pick<VRM, 'humanoid' | 'meta'>
  function position(name: string) {
    humanoid.update()
    scene.updateMatrixWorld(true)
    return bones[name].node.getWorldPosition(new Vector3())
  }
  return {
    vrm,
    position,
    bones,
    scene,
    right: new Vector3(-sign, 0, 0).applyQuaternion(scene.quaternion),
    front: new Vector3(0, 0, sign).applyQuaternion(scene.quaternion),
  }
}

function clip(transform?: (frame: number[][]) => void): GeneratedMotionClip {
  const frame = [
    [0, 1, 0],
    [0.1, 1, 0],
    [-0.1, 1, 0],
    [0, 1.15, 0],
    [0.1, 0.55, 0],
    [-0.1, 0.55, 0],
    [0, 1.3, 0],
    [0.1, 0.1, 0],
    [-0.1, 0.1, 0],
    [0, 1.45, 0],
    [0.1, 0.07, 0.15],
    [-0.1, 0.07, 0.15],
    [0, 1.55, 0],
    [0.1, 1.5, 0],
    [-0.1, 1.5, 0],
    [0, 1.7, 0],
    [0.2, 1.5, 0],
    [-0.2, 1.5, 0],
    [0.5, 1.5, 0],
    [-0.5, 1.5, 0],
    [0.8, 1.5, 0],
    [-0.8, 1.5, 0],
  ]
  transform?.(frame)
  return { format: 'humanml3d-22', coordinate_system: 'right-handed-y-up', fps: 20, joints: Array.from({ length: 81 }, () => frame.map(v => [...v])) }
}

function jumpingClip(height = 0.4) {
  const data = clip()
  for (let index = 0; index < data.joints.length; index++) {
    const time = index / data.fps
    const vertical = time >= 0.5 && time <= 2.5 ? height * Math.sin((time - 0.5) * Math.PI / 2) : 0
    for (const joint of data.joints[index]) {
      joint[0] += time * 2
      joint[1] += vertical
      joint[2] -= time
    }
  }
  return data
}

function squattingClip() {
  const data = clip()
  for (let index = 0; index < data.joints.length; index++) {
    const depth = index <= 40 ? 0.3 * Math.sin(index * Math.PI / 40) : 0
    const frame = data.joints[index]
    for (const joint of [0, 1, 2, 3, 6, 9, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21])
      frame[joint][1] -= depth
    for (const joint of [4, 5]) {
      frame[joint][1] = 0.55 - depth / 2
      frame[joint][2] = Math.sqrt(0.45 ** 2 - (0.45 - depth / 2) ** 2)
    }
  }
  return data
}

describe('humanML3D joint positions to VRM', () => {
  it.each(['0', '1'] as const)('raises the anatomical right arm in VRM %s at different scene headings', (version) => {
    for (const yaw of [0, 0.8, Math.PI]) {
      const { vrm, position, right } = fixture(version, yaw)
      const before = position('rightHand')
      const leftBefore = position('leftHand')
      const motion = createVrmGeneratedMotion()
      motion.play(clip((frame) => {
        frame[19] = [-0.2, 1.8, 0]
        frame[21] = [-0.2, 2.1, 0]
      }))
      motion.update(vrm, 0.5)
      const after = position('rightHand')
      expect(after.y - before.y).toBeGreaterThan(0.4)
      expect(after.clone().sub(position('hips')).dot(right)).toBeGreaterThan(0.1)
      expect(position('leftHand').distanceTo(leftBefore)).toBeLessThan(0.01)
    }
  })

  it.each(['0', '1'] as const)('bends toward the character front in VRM %s', (version) => {
    const { vrm, position, front } = fixture(version, 0.6)
    const before = position('head')
    const motion = createVrmGeneratedMotion()
    motion.play(clip((frame) => {
      for (const j of [3, 6, 9, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]) {
        const y = frame[j][1] - 1
        frame[j][1] = 1 + y * Math.cos(0.4)
        frame[j][2] = y * Math.sin(0.4)
      }
    }))
    motion.update(vrm, 0.5)
    expect(position('head').sub(before).dot(front)).toBeGreaterThan(0.15)
  })

  it('restores every touched rotation and never accumulates offsets or moves the root', () => {
    const { vrm } = fixture('0')
    const hip = vrm.humanoid.getNormalizedBoneNode('hips')!
    const arm = vrm.humanoid.getNormalizedBoneNode('rightUpperArm')!
    arm.rotation.z = 0.7
    const baseline = arm.quaternion.clone()
    const origin = hip.position.clone()
    const motion = createVrmGeneratedMotion()
    for (let cycle = 0; cycle < 20; cycle++) {
      motion.play(clip())
      for (let i = 0; i < 300; i++)
        motion.update(vrm, 1 / 60)
      expect(arm.quaternion.angleTo(baseline)).toBeLessThan(1e-7)
      expect(hip.position.equals(origin)).toBe(true)
      expect(motion.active).toBe(false)
    }
  })

  it('cancels on a different model and restores the old pose', () => {
    const first = fixture('1')
    const second = fixture('0')
    const bone = first.vrm.humanoid.getNormalizedBoneNode('rightUpperArm')!
    bone.rotation.z = 0.4
    const baseline = bone.quaternion.clone()
    const motion = createVrmGeneratedMotion()
    motion.play(clip())
    motion.update(first.vrm, 0.5)
    motion.update(second.vrm, 0.02)
    expect(motion.active).toBe(false)
    expect(bone.quaternion.angleTo(baseline)).toBeLessThan(1e-7)
  })

  it('rejects nonfinite, excessive and malformed clips without interrupting playback', () => {
    const motion = createVrmGeneratedMotion()
    expect(motion.play(clip())).toBe(true)
    const invalid = clip()
    invalid.joints[0][0][0] = Number.NaN
    expect(motion.play(invalid)).toBe(false)
    expect(motion.play({ ...clip(), fps: 60 })).toBe(false)
    expect(motion.play({ ...clip(), joints: [clip().joints[0]] })).toBe(false)
    expect(motion.play({ ...clip(), joints: Array.from({ length: 197 }, () => clip().joints[0]) })).toBe(false)
    expect(motion.active).toBe(true)
  })

  it('owns clip data and restores immediately when cancelled', () => {
    const { vrm } = fixture('1')
    const bone = vrm.humanoid.getNormalizedBoneNode('rightUpperArm')!
    bone.rotation.z = 0.4
    const baseline = bone.quaternion.clone()
    const motion = createVrmGeneratedMotion()
    const data = clip()
    motion.play(data)
    data.joints[10][17][0] = Number.NaN
    motion.update(vrm, 0.5)
    expect(bone.quaternion.toArray().every(Number.isFinite)).toBe(true)
    motion.stop()
    expect(bone.quaternion.angleTo(baseline)).toBeLessThan(1e-7)
  })

  it.each(['0', '1'] as const)('keeps a jump airborne, scaled and in place in VRM %s, then lands without drift', (version) => {
    for (const sceneScale of [0.5, 2]) {
      for (const bodyScale of [0.4, 1.7]) {
        const { vrm, position, scene } = fixture(version, 0.9, sceneScale, bodyScale)
        const origin = position('hips')
        const feet = [position('leftFoot'), position('rightFoot')]
        const modelPosition = scene.position.clone()
        const motion = createVrmGeneratedMotion()
        for (let repeat = 0; repeat < 5; repeat++) {
          expect(motion.play(jumpingClip())).toBe(true)
          motion.update(vrm, 1.5)
          expect(position('hips').y - origin.y).toBeCloseTo(0.4 * sceneScale * bodyScale, 6)
          expect(position('hips').x).toBeCloseTo(origin.x, 7)
          expect(position('hips').z).toBeCloseTo(origin.z, 7)
          for (const [index, name] of ['leftFoot', 'rightFoot'].entries())
            expect(position(name).y - feet[index].y).toBeCloseTo(0.4 * sceneScale * bodyScale, 6)
          motion.update(vrm, 1.1)
          expect(position('hips').distanceTo(origin)).toBeLessThan(1e-7)
          motion.update(vrm, 1.5)
          expect(motion.active).toBe(false)
          expect(position('hips').distanceTo(origin)).toBeLessThan(1e-7)
          expect(scene.position.equals(modelPosition)).toBe(true)
        }
      }
    }
  })

  it.each(['0', '1'] as const)('lowers the pelvis during a squat while preserving planted feet in VRM %s', (version) => {
    const { vrm, position, front } = fixture(version, 0.7)
    const hipsBefore = position('hips')
    const feetBefore = [position('leftFoot'), position('rightFoot')]
    const kneesBefore = [position('leftLowerLeg'), position('rightLowerLeg')]
    const motion = createVrmGeneratedMotion()
    motion.play(squattingClip())
    motion.update(vrm, 1)
    expect(position('hips').y - hipsBefore.y).toBeCloseTo(-0.3, 6)
    for (const [index, side] of ['left', 'right'].entries()) {
      expect(position(`${side}Foot`).distanceTo(feetBefore[index])).toBeLessThan(1e-6)
      expect(position(`${side}LowerLeg`).sub(kneesBefore[index]).dot(front)).toBeGreaterThan(0.3)
    }
    motion.stop()
    expect(position('hips').distanceTo(hipsBefore)).toBeLessThan(1e-7)
  })

  it('bounds extreme vertical offsets and restores the current mixer base after cancel or model replacement', () => {
    const { vrm } = fixture('1')
    const hips = vrm.humanoid.getNormalizedBoneNode('hips')!
    const origin = hips.position.clone()
    const motion = createVrmGeneratedMotion()
    motion.play(jumpingClip(90))
    motion.update(vrm, 1.5)
    expect(hips.position.y - origin.y).toBeCloseTo(1.5 * 0.9, 6)
    motion.restore()
    expect(hips.position.equals(origin)).toBe(true)
    hips.position.y += 0.05
    const mixerBase = hips.position.clone()
    motion.update(vrm, 0.1)
    expect(hips.position.y).toBeGreaterThan(mixerBase.y)
    motion.stop()
    expect(hips.position.equals(mixerBase)).toBe(true)
    motion.play(jumpingClip(-90))
    motion.update(vrm, 1.5)
    expect(hips.position.y - mixerBase.y).toBeCloseTo(-0.9 * 0.9, 6)
    motion.update(fixture('0').vrm, 0.1)
    expect(motion.active).toBe(false)
    expect(hips.position.equals(mixerBase)).toBe(true)
  })

  it.each(['0', '1'] as const)('retargets the recorded MotionGPT jump with both feet leaving the ground in VRM %s', (version) => {
    const data: GeneratedMotionClip = JSON.parse(readFileSync(new URL('../../../../../course/ntu-vh2026/results/motiongpt/jump-language/jump-short-mlx-seed42.json', import.meta.url), 'utf8'))
    const { vrm, position } = fixture(version, 0.4)
    const origin = position('hips')
    const feet = [position('leftFoot'), position('rightFoot')]
    const motion = createVrmGeneratedMotion()
    expect(motion.play(data)).toBe(true)
    motion.update(vrm, 29 / data.fps)
    expect(position('hips').y - origin.y).toBeGreaterThan(0.3)
    for (const [index, name] of ['leftFoot', 'rightFoot'].entries())
      expect(position(name).y - feet[index].y).toBeGreaterThan(0.25)
    expect(position('hips').x).toBeCloseTo(origin.x, 7)
    expect(position('hips').z).toBeCloseTo(origin.z, 7)
    motion.update(vrm, data.joints.length / data.fps)
    expect(motion.active).toBe(false)
    expect(position('hips').distanceTo(origin)).toBeLessThan(1e-7)
  })
})
