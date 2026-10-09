import type { VRM } from '@pixiv/three-vrm'
import type { Object3D } from 'three'

import { Matrix4, Quaternion, Vector3 } from 'three'

export interface GeneratedMotionClip {
  format: 'humanml3d-22'
  fps: number
  coordinate_system: 'right-handed-y-up'
  joints: number[][][]
}

type BoneName = Parameters<VRM['humanoid']['getNormalizedBoneNode']>[0]
type MotionVrm = Pick<VRM, 'humanoid' | 'meta'>

// HumanML3D uses +X anatomical left, +Y up and initial facing +Z.
// Each entry maps a VRM segment to two HumanML3D joints and its rest-direction child.
const segments: readonly [BoneName, number, number, BoneName | undefined][] = [
  ['spine', 3, 6, 'chest'],
  ['chest', 6, 9, 'upperChest'],
  ['upperChest', 9, 12, 'neck'],
  ['neck', 12, 15, 'head'],
  ['leftUpperLeg', 1, 4, 'leftLowerLeg'],
  ['leftLowerLeg', 4, 7, 'leftFoot'],
  ['leftFoot', 7, 10, 'leftToes'],
  ['rightUpperLeg', 2, 5, 'rightLowerLeg'],
  ['rightLowerLeg', 5, 8, 'rightFoot'],
  ['rightFoot', 8, 11, 'rightToes'],
  ['leftUpperArm', 16, 18, 'leftLowerArm'],
  ['leftLowerArm', 18, 20, 'leftHand'],
  ['rightUpperArm', 17, 19, 'rightLowerArm'],
  ['rightLowerArm', 19, 21, 'rightHand'],
]

// Support can move from feet to knees, hands, pelvis or torso during floor poses.
const supportJoints: readonly [BoneName, number][] = [
  ['hips', 0],
  ['leftUpperLeg', 1],
  ['rightUpperLeg', 2],
  ['spine', 3],
  ['leftLowerLeg', 4],
  ['rightLowerLeg', 5],
  ['chest', 6],
  ['leftFoot', 7],
  ['rightFoot', 8],
  ['upperChest', 9],
  ['leftToes', 10],
  ['rightToes', 11],
  ['neck', 12],
  ['leftShoulder', 13],
  ['rightShoulder', 14],
  ['head', 15],
  ['leftUpperArm', 16],
  ['rightUpperArm', 17],
  ['leftLowerArm', 18],
  ['rightLowerArm', 19],
  ['leftHand', 20],
  ['rightHand', 21],
]

interface TargetSupport {
  legLength: number
  floor: number
  joints: { bone: Object3D, source: number }[]
}

function measureTargetSupport(vrm: MotionVrm, hips: Object3D): TargetSupport {
  const rest = vrm.humanoid.normalizedRestPose
  const names = new Map<Object3D, BoneName>()
  const joints: TargetSupport['joints'] = []
  for (const [name, source] of supportJoints) {
    const bone = vrm.humanoid.getNormalizedBoneNode(name)
    if (bone) {
      names.set(bone, name)
      joints.push({ bone, source })
    }
  }
  const legBones: BoneName[] = ['leftLowerLeg', 'leftFoot', 'rightLowerLeg', 'rightFoot']
  const legLength = legBones.reduce((sum, name) => {
    const position = rest[name]?.position
    return sum + (position ? Math.hypot(...position) : 0)
  }, 0) / 2
  // Normalized rest bones have identity rotations. Sum their offsets in the hips parent's frame.
  // Keep the avatar's resting foot/toe plane, rather than moving its ankle joints to world Y=0.
  const soleBones: BoneName[] = ['leftFoot', 'rightFoot', 'leftToes', 'rightToes']
  const heights = soleBones.flatMap((name) => {
    let bone = vrm.humanoid.getNormalizedBoneNode(name)
    if (!bone)
      return []
    let height = 0
    while (bone && bone !== hips.parent) {
      const boneName = names.get(bone)
      if (!boneName)
        return []
      height += rest[boneName]?.position?.[1] ?? 0
      bone = bone.parent
    }
    return [height]
  })
  return { legLength, floor: heights.length ? Math.min(...heights) : Number.NaN, joints }
}

/** Keep the renderer safe even when a caller bypasses the network schema. */
export function isGeneratedMotionClip(value: GeneratedMotionClip) {
  return value?.format === 'humanml3d-22'
    && value.coordinate_system === 'right-handed-y-up'
    && value.fps === 20
    && Array.isArray(value.joints) && value.joints.length >= 2 && value.joints.length <= 196
    && value.joints.every(frame => Array.isArray(frame) && frame.length === 22
      && frame.every(joint => Array.isArray(joint) && joint.length === 3
        && joint.every(v => Number.isFinite(v) && Math.abs(v) <= 100)))
}

/** Retarget with a skeleton support plane and bounded airtime. No mesh collision, planar travel or foot IK. */
export function createVrmGeneratedMotion() {
  let active: { clip: GeneratedMotionClip, elapsed: number, sourceLegLength: number, support?: TargetSupport, owner?: MotionVrm } | undefined
  const previousPose = new Map<Object3D, Quaternion>()
  let previousPosition: { bone: Object3D, position: Vector3 } | undefined
  const frame = Array.from({ length: 22 }, () => new Vector3())
  const parentRotation = new Quaternion()
  const rootRotation = new Quaternion()
  const targetRotation = new Quaternion()
  const direction = new Vector3()
  const restDirection = new Vector3()
  const left = new Vector3()
  const up = new Vector3()
  const front = new Vector3()
  const basis = new Matrix4()
  const parentInverse = new Matrix4()
  const supportPosition = new Vector3()

  function restore() {
    for (const [bone, rotation] of previousPose)
      bone.quaternion.copy(rotation)
    previousPose.clear()
    if (previousPosition) {
      previousPosition.bone.position.copy(previousPosition.position)
      previousPosition = undefined
    }
  }

  function stop() {
    restore()
    active = undefined
  }

  function play(clip: GeneratedMotionClip) {
    if (!isGeneratedMotionClip(clip))
      return false
    stop()
    // Own a plain snapshot so UI or transport mutation cannot change a running clip.
    const first = clip.joints[0]
    const distance = (a: number, b: number) => Math.hypot(...first[a].map((value, axis) => value - first[b][axis]))
    const sourceLegLength = (distance(1, 4) + distance(4, 7) + distance(2, 5) + distance(5, 8)) / 2
    active = { clip: { ...clip, joints: clip.joints.map(f => f.map(j => [...j])) }, elapsed: 0, sourceLegLength }
    return true
  }

  function update(vrm: MotionVrm, delta: number) {
    restore()
    if (!active || !Number.isFinite(delta) || delta < 0)
      return
    if (active.owner && active.owner !== vrm) {
      stop()
      return
    }
    active.owner = vrm
    active.elapsed += delta
    const { clip, elapsed } = active
    const duration = (clip.joints.length - 1) / clip.fps
    if (elapsed >= duration) {
      stop()
      return
    }
    const hips = vrm.humanoid.getNormalizedBoneNode('hips')
    if (!hips?.parent) {
      stop()
      return
    }
    const offset = elapsed * clip.fps
    const index = Math.floor(offset)
    const blend = offset - index
    for (let j = 0; j < 22; j++) {
      frame[j].fromArray(clip.joints[index][j])
      direction.fromArray(clip.joints[Math.min(index + 1, clip.joints.length - 1)][j])
      frame[j].lerp(direction, blend)
    }
    const edge = Math.min(1, elapsed / 0.25, (duration - elapsed) / 0.35)
    const envelope = edge * edge * (3 - 2 * edge)
    const vrm0 = vrm.meta.metaVersion === '0'
    hips.parent.getWorldQuaternion(rootRotation)

    active.support ??= measureTargetSupport(vrm, hips)
    const targetSupport = active.support
    hips.parent.updateWorldMatrix(true, true)
    parentInverse.copy(hips.parent.matrixWorld).invert()
    const lowestTargetSupport = () => {
      let lowest = Infinity
      for (const { bone } of targetSupport.joints) {
        bone.getWorldPosition(supportPosition).applyMatrix4(parentInverse)
        lowest = Math.min(lowest, supportPosition.y)
      }
      return lowest
    }
    const baselineLowest = lowestTargetSupport()

    // Body basis preserves the generated turn. Joint positions alone cannot recover axial twist.
    left.subVectors(frame[1], frame[2]).add(direction.subVectors(frame[16], frame[17]))
    up.subVectors(frame[12], frame[0])
    front.crossVectors(left, up)
    if (left.lengthSq() > 1e-8 && front.lengthSq() > 1e-8) {
      left.normalize()
      front.normalize()
      up.crossVectors(front, left).normalize()
      targetRotation.setFromRotationMatrix(basis.makeBasis(left, up, front))
      if (vrm0) {
        targetRotation.x *= -1
        targetRotation.z *= -1
      }
      previousPose.set(hips, hips.quaternion.clone())
      hips.quaternion.slerp(targetRotation, envelope)
      hips.updateWorldMatrix(false, true)
    }

    for (const [name, start, end, childName] of segments) {
      const bone = vrm.humanoid.getNormalizedBoneNode(name)
      if (!bone?.parent)
        continue
      direction.subVectors(frame[end], frame[start])
      if (direction.lengthSq() < 1e-8)
        continue
      if (vrm0) {
        direction.x *= -1
        direction.z *= -1
      }
      direction.normalize().applyQuaternion(rootRotation)
      bone.parent.getWorldQuaternion(parentRotation)
      direction.applyQuaternion(parentRotation.invert())
      const child = childName ? vrm.humanoid.getNormalizedBoneNode(childName) : null
      if (child?.parent === bone && child.position.lengthSq() > 1e-8) {
        restDirection.copy(child.position).normalize()
      }
      else {
        // Optional chest/toe nodes can be absent in valid VRMs.
        restDirection.set(0, name.endsWith('Foot') ? 0 : 1, name.endsWith('Foot') ? (vrm0 ? -1 : 1) : 0)
      }
      targetRotation.setFromUnitVectors(restDirection, direction)
      previousPose.set(bone, bone.quaternion.clone())
      bone.quaternion.slerp(targetRotation, envelope)
      bone.updateWorldMatrix(false, true)
    }

    const { support, sourceLegLength } = active
    if (sourceLegLength > 1e-4 && support.legLength > 1e-4 && Number.isFinite(support.floor)) {
      const targetLowest = lowestTargetSupport()
      // Missing optional target toes must not turn the source ankle height into false airtime.
      const sourceLowest = Math.min(...frame.map(joint => joint.y))
      // HumanML3D's training floor is Y=0. Predicted negative joints are noise, not a new floor.
      // Source: MotionGPT 001aaca, mGPT/data/humanml/scripts/motion_process.py:178-187.
      // Preserve airborne clearance. Never ground every frame or assume the first pelvis is standing.
      const clearance = Math.min(1.5, Math.max(0, sourceLowest) / sourceLegLength) * support.legLength
      const desiredLowest = baselineLowest * (1 - envelope) + (support.floor + clearance) * envelope
      const displacement = desiredLowest - targetLowest
      const bounded = Math.max(-2 * support.legLength, Math.min(2 * support.legLength, displacement))
      previousPosition = { bone: hips, position: hips.position.clone() }
      hips.position.y += bounded
      hips.updateWorldMatrix(false, true)
    }
  }

  return {
    play,
    stop,
    restore,
    update,
    get active() {
      return !!active
    },
  }
}
