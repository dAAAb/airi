import process from 'node:process'

import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

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

  const [clipPath, ...modelPaths] = process.argv.slice(2)
  if (!clipPath || !modelPaths.length)
    throw new Error('Pass one generated clip JSON and at least one VRM path.')
  const clipBytes = await readFile(resolve(clipPath))
  const clip = JSON.parse(clipBytes)
  if (!isGeneratedMotionClip(clip))
    throw new Error('Invalid generated motion schema.')
  const reports = []
  for (const path of modelPaths) {
    const vrm = await loadSkeleton(resolve(path))
    const controller = createVrmGeneratedMotion()
    const rootBone = vrm.humanoid.getNormalizedBoneNode('hips')
    const rootBefore = rootBone.position.clone()
    const initial = Object.values(vrm.humanoid.normalizedHumanBones).map(({ node }) => [node, node.quaternion.clone()])
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
    let finite = true
    controller.play(clip)
    for (let frame = 1; frame < clip.joints.length; frame++) {
      controller.update(vrm, 1 / clip.fps)
      vrm.humanoid.update()
      vrm.scene.updateMatrixWorld(true)
      finite &&= initial.every(([node]) => node.quaternion.toArray().every(Number.isFinite))
      if (frame / clip.fps < 0.3 || (clip.joints.length - 1 - frame) / clip.fps < 0.4)
        continue
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
    const checks = {
      finite_rotations: finite,
      source_limb_directions_preserved: Math.min(...dots) > 0.999,
      root_translation_unchanged: rootBone.position.distanceTo(rootBefore) < 1e-8,
      restored_idle_rotations: initial.every(([node, rotation]) => node.quaternion.angleTo(rotation) < 1e-7),
      stopped: !controller.active,
    }
    reports.push({ model: relative(root, resolve(path)), sha256: vrm.sha256, meta_version: vrm.meta.metaVersion, compared_segments: dots.length, minimum_direction_cosine: Math.min(...dots), checks })
  }
  const report = {
    scope: 'Real MotionGPT joint sequence retargeted onto actual VRM node transforms with three-vrm. No rendered images or semantic-quality score.',
    checked_at: new Date().toISOString(),
    clip: relative(root, resolve(clipPath)),
    clip_sha256: createHash('sha256').update(clipBytes).digest('hex'),
    prompt: clip.prompt,
    frames: clip.joints.length,
    fps: clip.fps,
    models: reports,
  }
  const output = resolve(root, 'course/ntu-vh2026/results/motiongpt/retarget-real-wave.json')
  await writeFile(output, `${JSON.stringify(report, null, 2)}\n`)
  console.info(JSON.stringify(report, null, 2))
  if (reports.some(model => Object.values(model.checks).some(ok => !ok)))
    process.exitCode = 1
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
