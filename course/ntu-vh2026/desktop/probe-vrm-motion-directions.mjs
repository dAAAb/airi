import process from 'node:process'

import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

async function main() {
  // The probe runs the TypeScript controller directly with Node 22.18+.
  const { createVrmSemanticMotion } = await import(new URL('../../../packages/stage-ui-three/src/composables/vrm/semantic-motion.ts', import.meta.url).href)
  const require = createRequire(new URL('../../../packages/stage-ui-three/package.json', import.meta.url))
  const { AnimationMixer, Matrix4, Object3D, Vector3 } = await import(require.resolve('three').replace(/\.cjs$/, '.module.js'))
  const { VRMHumanoid } = await import(require.resolve('@pixiv/three-vrm').replace(/\.cjs$/, '.module.js'))
  const { createVRMAnimationClip, VRMAnimationLoaderPlugin } = await import(require.resolve('@pixiv/three-vrm-animation').replace(/\.cjs$/, '.module.js'))
  const { GLTFLoader } = await import(require.resolve('three/addons/loaders/GLTFLoader.js'))
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

  const animationBytes = await readFile(resolve(root, 'packages/stage-ui-three/src/assets/vrm/animations/idle_loop.vrma'))
  const loader = new GLTFLoader().register(parser => new VRMAnimationLoaderPlugin(parser))
  const animationGltf = await loader.parseAsync(animationBytes.buffer.slice(animationBytes.byteOffset, animationBytes.byteOffset + animationBytes.byteLength), '')
  const idle = animationGltf.userData.vrmAnimations[0]
  const paths = process.argv.slice(2)
  if (!paths.length)
    throw new Error('Pass one or more local .vrm files. Run with Node 22.18+ for TypeScript support.')
  const reports = []
  for (const path of paths) {
    const vrm = await loadSkeleton(resolve(path))
    const mixer = new AnimationMixer(vrm.scene)
    mixer.clipAction(createVRMAnimationClip(idle, vrm)).play()
    const front = new Vector3(0, 0, vrm.meta.metaVersion === '0' ? -1 : 1)
    const right = new Vector3().crossVectors(front, new Vector3(0, 1, 0))
    function position(name) {
      return vrm.humanoid.getRawBoneNode(name).getWorldPosition(new Vector3())
    }
    function snapshot() {
      vrm.humanoid.update()
      vrm.scene.updateMatrixWorld(true)
      const shoulder = position('rightUpperArm')
      return {
        head: position('head'),
        rightHand: position('rightHand'),
        leftHand: position('leftHand'),
        rightHandSide: position('rightHand').clone().sub(shoulder).dot(right),
        rightHandFront: position('rightHand').clone().sub(shoulder).dot(front),
      }
    }
    const samples = []
    for (const name of ['bow', 'wave', 'celebrate', 'dance']) {
      for (const legacyAxes of [true, false]) {
        const controller = createVrmSemanticMotion()
        mixer.setTime(0.6)
        const before = snapshot()
        controller.play(name)
        controller.update(legacyAxes ? { ...vrm, meta: { metaVersion: '1' } } : vrm, 0.6)
        const after = snapshot()
        samples.push({
          motion: name,
          legacy_axes: legacyAxes,
          head_forward_delta_m: after.head.clone().sub(before.head).dot(front),
          right_hand_up_delta_m: after.rightHand.y - before.rightHand.y,
          right_hand_side_m: after.rightHandSide,
          right_hand_forward_m: after.rightHandFront,
          left_hand_motion_m: after.leftHand.distanceTo(before.leftHand),
        })
        controller.stop()
      }
    }
    const current = samples.filter(sample => !sample.legacy_axes)
    const wave = current.find(sample => sample.motion === 'wave')
    const bow = current.find(sample => sample.motion === 'bow')
    const checks = {
      bow_moves_forward: bow.head_forward_delta_m > 0,
      right_wave_stays_on_right: wave.right_hand_side_m > 0,
      right_wave_lifts: wave.right_hand_up_delta_m > 0,
      left_hand_stays_still_during_wave: wave.left_hand_motion_m < 1e-7,
    }
    reports.push({ model: path, sha256: vrm.sha256, meta_version: vrm.meta.metaVersion, source_front: front.toArray(), checks, samples })
  }
  const report = {
    scope: 'Offline actual model node transforms + three-vrm humanoid + bundled idle animation + source motion controller. No rendered images.',
    checked_at: new Date().toISOString(),
    sources: [
      'https://vrm.dev/api/coordinate/',
      'https://github.com/pixiv/three-vrm/blob/dev/packages/three-vrm-animation/src/createVRMAnimationClip.ts',
    ],
    models: reports,
  }
  const output = resolve(root, 'course/ntu-vh2026/results/desktop-pet-vrm-directions.json')
  await writeFile(output, `${JSON.stringify(report, null, 2)}\n`)
  console.info(JSON.stringify({ output, models: reports.map(({ model, meta_version, checks }) => ({ model, meta_version, checks })) }, null, 2))
  if (reports.some(model => Object.values(model.checks).some(passed => !passed)))
    process.exitCode = 1
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
