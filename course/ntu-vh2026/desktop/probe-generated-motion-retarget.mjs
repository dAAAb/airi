import process from 'node:process'

import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// Keep joint names aligned with generated-motion.ts. Missing optional VRM bones are reported.
const supportJointNames = [
  'hips',
  'leftUpperLeg',
  'rightUpperLeg',
  'spine',
  'leftLowerLeg',
  'rightLowerLeg',
  'chest',
  'leftFoot',
  'rightFoot',
  'upperChest',
  'leftToes',
  'rightToes',
  'neck',
  'leftShoulder',
  'rightShoulder',
  'head',
  'leftUpperArm',
  'rightUpperArm',
  'leftLowerArm',
  'rightLowerArm',
  'leftHand',
  'rightHand',
]

async function main() {
  const { createVrmGeneratedMotion, isGeneratedMotionClip } = await import(new URL('../../../packages/stage-ui-three/src/composables/vrm/generated-motion.ts', import.meta.url).href)
  const require = createRequire(new URL('../../../packages/stage-ui-three/package.json', import.meta.url))
  const { Matrix4, Object3D, Quaternion, Vector3 } = await import(require.resolve('three').replace(/\.cjs$/, '.module.js'))
  const { VRMHumanoid } = await import(require.resolve('@pixiv/three-vrm').replace(/\.cjs$/, '.module.js'))
  const root = fileURLToPath(new URL('../../../', import.meta.url))
  // Read only node transforms and the humanoid mapping. No textures, scripts or renderer are loaded.
  async function loadSkeleton(path) {
    const bytes = await readFile(path)
    const jsonLength = bytes.readUInt32LE(12)
    const gltf = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString('utf8'))
    const nodes = gltf.nodes.map((node) => {
      const object = new Object3D()
      object.name = node.name ?? ''
      if (node.matrix) {
        new Matrix4().fromArray(node.matrix).decompose(object.position, object.quaternion, object.scale)
      }
      else {
        if (node.translation)
          object.position.fromArray(node.translation)
        if (node.rotation)
          object.quaternion.fromArray(node.rotation)
        if (node.scale)
          object.scale.fromArray(node.scale)
      }
      return object
    })
    gltf.nodes.forEach((node, index) => {
      for (const child of node.children ?? []) nodes[index].add(nodes[child])
    })
    const scene = new Object3D()
    for (const index of gltf.scenes[gltf.scene ?? 0].nodes) scene.add(nodes[index])
    scene.updateMatrixWorld(true)
    const metaVersion = gltf.extensions.VRMC_vrm ? '1' : '0'
    const source = (gltf.extensions.VRMC_vrm ?? gltf.extensions.VRM).humanoid.humanBones
    const mapping = Array.isArray(source) ? source.map(bone => [bone.bone, bone]) : Object.entries(source)
    const humanoid = new VRMHumanoid(Object.fromEntries(mapping.map(([name, bone]) => [name, { node: nodes[bone.node] }])))
    scene.add(humanoid.normalizedHumanBonesRoot)
    return { scene, humanoid, meta: { metaVersion }, sha256: createHash('sha256').update(bytes).digest('hex') }
  }

  const positional = []
  let output = resolve(root, 'course/ntu-vh2026/results/motiongpt/retarget-real-wave.json')
  const args = process.argv.slice(2)
  for (let index = 0; index < args.length; index++) {
    if (args[index] === '--output') {
      if (!args[index + 1] || args[index + 1].startsWith('--'))
        throw new Error('--output requires a JSON file path.')
      output = resolve(args[++index])
    }
    else if (args[index].startsWith('--')) {
      throw new Error(`Unknown option: ${args[index]}`)
    }
    else {
      positional.push(args[index])
    }
  }
  const [clipPath, ...modelPaths] = positional
  if (!clipPath || !modelPaths.length)
    throw new Error('Pass one generated clip JSON and at least one VRM path.')
  const clipBytes = await readFile(resolve(clipPath))
  const clip = JSON.parse(clipBytes)
  if (!isGeneratedMotionClip(clip))
    throw new Error('Invalid generated motion schema.')
  const range = values => ({ minimum: Math.min(...values), maximum: Math.max(...values) })
  const first = clip.joints[0]
  const distance = (a, b) => new Vector3().fromArray(first[a]).distanceTo(new Vector3().fromArray(first[b]))
  const sourceLegLength = (distance(1, 4) + distance(4, 7) + distance(2, 5) + distance(5, 8)) / 2
  const sourceMinimumY = clip.joints.map(frame => Math.min(...frame.map(joint => joint[1])))
  const reports = []
  for (const path of modelPaths) {
    const vrm = await loadSkeleton(resolve(path))
    const controller = createVrmGeneratedMotion()
    const rootBone = vrm.humanoid.getNormalizedBoneNode('hips')
    const rootBefore = rootBone.position.clone()
    vrm.scene.updateMatrixWorld(true)
    const rootWorldBefore = rootBone.getWorldPosition(new Vector3())
    const initial = Object.values(vrm.humanoid.normalizedHumanBones).map(({ node }) => [node, node.quaternion.clone(), node.position.clone()])
    const parentInverse = rootBone.parent.matrixWorld.clone().invert()
    const parentPosition = bone => bone.getWorldPosition(new Vector3()).applyMatrix4(parentInverse)
    const support = supportJointNames.flatMap((name, source) => {
      const bone = vrm.humanoid.getNormalizedBoneNode(name)
      return bone ? [{ name, source, bone }] : []
    })
    const floorBones = support.filter(({ name }) => ['leftFoot', 'rightFoot', 'leftToes', 'rightToes'].includes(name))
    const restPlane = Math.min(...floorBones.map(({ bone }) => parentPosition(bone).y))
    const targetLegLength = ['left', 'right'].reduce((sum, side) => {
      const [hip, knee, foot] = ['UpperLeg', 'LowerLeg', 'Foot'].map(suffix => parentPosition(vrm.humanoid.getNormalizedBoneNode(`${side}${suffix}`)))
      return sum + hip.distanceTo(knee) + knee.distanceTo(foot)
    }, 0) / 2
    const lowestSupport = () => support.reduce((lowest, joint) => {
      const height = parentPosition(joint.bone).y
      return height < lowest.height ? { name: joint.name, height } : lowest
    }, { name: '', height: Infinity })
    const feet = ['leftFoot', 'rightFoot'].map(name => vrm.humanoid.getRawBoneNode(name))
    const feetBefore = feet.map(bone => bone.getWorldPosition(new Vector3()).y)
    const basisRotation = rootBone.parent.getWorldQuaternion(new Quaternion())
    const segments = [
      ['leftUpperArm', 'leftLowerArm', 16, 18],
      ['leftLowerArm', 'leftHand', 18, 20],
      ['rightUpperArm', 'rightLowerArm', 17, 19],
      ['rightLowerArm', 'rightHand', 19, 21],
      ['leftUpperLeg', 'leftLowerLeg', 1, 4],
      ['leftLowerLeg', 'leftFoot', 4, 7],
      ['rightUpperLeg', 'rightLowerLeg', 2, 5],
      ['rightLowerLeg', 'rightFoot', 5, 8],
    ]
    const dots = []
    const rootLocalY = []
    const rootWorldY = []
    const footDeltas = []
    const rootPlanarDeltas = []
    const supportSamples = []
    let finiteRotations = true
    let finitePositions = true
    controller.play(clip)
    for (let frame = 1; frame < clip.joints.length; frame++) {
      controller.update(vrm, 1 / clip.fps)
      vrm.humanoid.update()
      vrm.scene.updateMatrixWorld(true)
      finiteRotations &&= initial.every(([node]) => node.quaternion.toArray().every(Number.isFinite))
      finitePositions &&= initial.every(([node]) => node.position.toArray().every(Number.isFinite)
        && node.getWorldPosition(new Vector3()).toArray().every(Number.isFinite))
      rootPlanarDeltas.push(Math.hypot(rootBone.position.x - rootBefore.x, rootBone.position.z - rootBefore.z))
      rootLocalY.push(rootBone.position.y - rootBefore.y)
      rootWorldY.push(rootBone.getWorldPosition(new Vector3()).y - rootWorldBefore.y)
      footDeltas.push(feet.map((bone, index) => bone.getWorldPosition(new Vector3()).y - feetBefore[index]))
      if (frame / clip.fps < 0.3 || (clip.joints.length - 1 - frame) / clip.fps < 0.4)
        continue
      // Source floor clearance cannot change when the target omits optional toe bones.
      const sourceLowest = Math.min(...clip.joints[frame].map(joint => joint[1]))
      const sourceMappedLowest = Math.min(...support.map(({ source }) => clip.joints[frame][source][1]))
      const actual = lowestSupport()
      const expectedClearance = Math.min(1.5, Math.max(0, sourceLowest) / sourceLegLength) * targetLegLength
      supportSamples.push({
        frame,
        source_lowest_y: sourceLowest,
        source_mapped_lowest_y: sourceMappedLowest,
        source_positive_clearance: Math.max(0, sourceLowest),
        expected_target_clearance: expectedClearance,
        target_lowest_parent_y: actual.height,
        target_lowest_bone: actual.name,
        error: actual.height - restPlane - expectedClearance,
      })
      for (const [bone, child, a, b] of segments) {
        const actual = vrm.humanoid.getRawBoneNode(child).getWorldPosition(new Vector3()).sub(vrm.humanoid.getRawBoneNode(bone).getWorldPosition(new Vector3())).normalize()
        const expected = new Vector3().fromArray(clip.joints[frame][b]).sub(new Vector3().fromArray(clip.joints[frame][a]))
        if (vrm.meta.metaVersion === '0') {
          expected.x *= -1
          expected.z *= -1
        }
        expected.normalize().applyQuaternion(basisRotation)
        dots.push(actual.dot(expected))
      }
    }
    controller.stop()
    vrm.humanoid.update()
    vrm.scene.updateMatrixWorld(true)
    if (!supportSamples.length)
      throw new Error('The clip is too short to measure a full-envelope support pose.')
    const endRestoration = {
      restored_root_position_after_stop: rootBone.position.distanceTo(rootBefore) < 1e-8,
      restored_all_normalized_positions_after_stop: initial.every(([node, , position]) => node.position.distanceTo(position) < 1e-8),
      restored_idle_rotations: initial.every(([node, rotation]) => node.quaternion.angleTo(rotation) < 1e-7),
      stopped_after_completion: !controller.active,
    }
    const lowPose = supportSamples.reduce((lowest, sample) => clip.joints[sample.frame][0][1] < clip.joints[lowest.frame][0][1] ? sample : lowest)
    controller.play(clip)
    controller.update(vrm, lowPose.frame / clip.fps)
    vrm.humanoid.update()
    vrm.scene.updateMatrixWorld(true)
    const midStopActive = controller.active
    const midStopRoot = rootBone.position.clone()
    const midStopSupport = lowestSupport()
    controller.stop()
    vrm.humanoid.update()
    vrm.scene.updateMatrixWorld(true)
    const midStopPositionError = Math.max(...initial.map(([node, , position]) => node.position.distanceTo(position)))
    const midStopRotationError = Math.max(...initial.map(([node, rotation]) => node.quaternion.angleTo(rotation)))
    const checks = {
      finite_rotations: finiteRotations,
      finite_positions: finitePositions,
      source_limb_directions_preserved: Math.min(...dots) > 0.999,
      planar_root_position_unchanged_every_frame: Math.max(...rootPlanarDeltas) < 1e-8,
      ...endRestoration,
      full_envelope_support_alignment: supportSamples.every(sample => Math.abs(sample.error) < 1e-6),
      mid_motion_stop_was_active: midStopActive,
      mid_motion_stop_restores_positions: midStopPositionError < 1e-8,
      mid_motion_stop_restores_rotations: midStopRotationError < 1e-7,
      stopped: !controller.active,
    }
    const lowerFoot = footDeltas.map(values => Math.min(...values))
    const lowerFootPeak = Math.max(...lowerFoot)
    reports.push({
      model: relative(root, resolve(path)),
      sha256: vrm.sha256,
      meta_version: vrm.meta.metaVersion,
      compared_segments: dots.length,
      minimum_direction_cosine: Math.min(...dots),
      measured_frames: rootLocalY.length,
      vertical_motion: {
        units: 'VRM scene units. Raw Foot bone positions are ankle joints, not mesh soles or physical ground contact.',
        baseline: 'Unanimated normalized rest pose before the first controller update.',
        root_local_y_delta: range(rootLocalY),
        root_world_y_delta: range(rootWorldY),
        maximum_root_planar_delta: Math.max(...rootPlanarDeltas),
        left_foot_world_y_delta: range(footDeltas.map(values => values[0])),
        right_foot_world_y_delta: range(footDeltas.map(values => values[1])),
        lower_of_both_feet_world_y_delta: range(lowerFoot),
        lower_of_both_feet_peak_source_frame: lowerFoot.indexOf(lowerFootPeak) + 1,
      },
      support_alignment: {
        scope: 'Normalized joint support plane in hips-parent coordinates. No mesh sole, skin thickness, collision or semantic-quality claim.',
        source_floor: 0,
        source_clearance_scope: 'All 22 source joints, independent of missing optional target bones.',
        target_rest_foot_toe_plane: restPlane,
        target_plane_bones: floorBones.map(({ name }) => name),
        missing_optional_bones: supportJointNames.filter(name => !support.some(joint => joint.name === name)),
        source_leg_length: sourceLegLength,
        target_leg_length: targetLegLength,
        full_envelope_frames_checked: supportSamples.length,
        maximum_absolute_alignment_error: Math.max(...supportSamples.map(sample => Math.abs(sample.error))),
        source_mapped_minimum_y: range(supportSamples.map(sample => sample.source_mapped_lowest_y)),
        source_all_joint_minimum_y: range(supportSamples.map(sample => sample.source_lowest_y)),
        expected_positive_target_clearance: range(supportSamples.map(sample => sample.expected_target_clearance)),
        measured_target_support_clearance: range(supportSamples.map(sample => sample.target_lowest_parent_y - restPlane)),
        lowest_pelvis_sample: lowPose,
        maximum_clearance_sample: supportSamples.reduce((highest, sample) => sample.expected_target_clearance > highest.expected_target_clearance ? sample : highest),
        worst_alignment_sample: supportSamples.reduce((worst, sample) => Math.abs(sample.error) > Math.abs(worst.error) ? sample : worst),
      },
      mid_motion_stop: {
        frame: lowPose.frame,
        source_pelvis_y: clip.joints[lowPose.frame][0][1],
        root_position_before_stop: midStopRoot.toArray(),
        lowest_support_before_stop: midStopSupport,
        maximum_position_restore_error: midStopPositionError,
        maximum_rotation_restore_error: midStopRotationError,
      },
      checks,
    })
  }
  const report = {
    scope: 'Real MotionGPT joint sequence retargeted onto actual VRM node transforms with three-vrm. No rendered images or semantic-quality score.',
    checked_at: new Date().toISOString(),
    clip: relative(root, resolve(clipPath)),
    clip_sha256: createHash('sha256').update(clipBytes).digest('hex'),
    prompt: clip.prompt,
    frames: clip.joints.length,
    fps: clip.fps,
    renderer_source_sha256: createHash('sha256').update(await readFile(new URL('../../../packages/stage-ui-three/src/composables/vrm/generated-motion.ts', import.meta.url))).digest('hex'),
    source_motion: {
      canonical_floor_y: 0,
      first_pelvis_y: first[0][1],
      pelvis_y: range(clip.joints.map(frame => frame[0][1])),
      all_joint_minimum_y: range(sourceMinimumY),
      positive_all_joint_clearance: range(sourceMinimumY.map(height => Math.max(0, height))),
      frames_with_negative_joint_y: sourceMinimumY.filter(height => height < 0).length,
      note: 'Generated source motions can hover or fail the prompt. Alignment preserves positive clearance and does not manufacture a fall.',
    },
    models: reports,
  }
  await writeFile(output, `${JSON.stringify(report, null, 2)}\n`)
  console.info(JSON.stringify(report, null, 2))
  if (reports.some(model => Object.values(model.checks).some(ok => !ok)))
    process.exitCode = 1
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
