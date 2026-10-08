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

/** Retarget joint positions in place. No root travel, finger synthesis, collision or foot IK. */
export function createVrmGeneratedMotion() {
  let active: { clip: GeneratedMotionClip, elapsed: number, owner?: MotionVrm } | undefined
  const previousPose = new Map<Object3D, Quaternion>()
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

  function restore() {
    for (const [bone, rotation] of previousPose)
      bone.quaternion.copy(rotation)
    previousPose.clear()
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
    active = { clip: { ...clip, joints: clip.joints.map(f => f.map(j => [...j])) }, elapsed: 0 }
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
