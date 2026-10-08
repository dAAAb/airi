"""Plot two additional saved MotionGPT outputs with unchanged joint coordinates."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('skeleton_previews', ROOT / 'render-skeleton-previews.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)
np, plt = preview.np, preview.plt


def render(name, source=None):
    source = source or ROOT / 'novel' / f'{name}-cpu.json'
    raw = source.read_bytes()
    data = json.loads(raw)
    joints = np.asarray(data['joints'], dtype=float)
    assert joints.shape[1:] == (22, 3) and np.isfinite(joints).all()
    assert data['coordinate_system'] == 'right-handed-y-up'
    assert data['initial_forward'] == '+Z' and data['anatomical_left'] == '+X'
    left_reach = np.linalg.norm(joints[:, 20] - joints[:, 16], axis=1)
    right_reach = np.linalg.norm(joints[:, 21] - joints[:, 17], axis=1)
    if name == 'stretch':
        peak = int(np.minimum(joints[:, 20, 1], joints[:, 21, 1]).argmax())
        frames = sorted({0, len(joints) // 4, peak, 3 * len(joints) // 4, len(joints) - 1})
    else:
        frames = sorted({0, int(left_reach.argmax()), int(right_reach.argmax()), 3 * len(joints) // 4, len(joints) - 1})
    bounds = preview.limits(joints)
    fig, axes = plt.subplots(2, len(frames), figsize=(17.5, 8.2), dpi=110)
    fig.subplots_adjust(top=0.84, bottom=0.12, hspace=0.48, wspace=0.32)
    fig.suptitle(f'{data["prompt"]}\n{data["device"].upper()} · seed {data["seed"]} · {len(joints)} original frames · {len(joints) / data["fps"]:.1f}s at {data["fps"]} fps', fontsize=13, y=0.97)
    for axis in range(2):
        for col, frame in enumerate(frames):
            ax = axes[axis, col]
            preview.make_axes(ax, axis, bounds, f'{"Front" if axis == 0 else "Left side"} · #{frame + 1} · {frame / data["fps"]:.2f}s')
            preview.update(preview.make_artists(ax, data['joint_names']), joints[frame], axis)
    legend = [preview.Line2D([0], [0], color=preview.COLORS[key], linewidth=3, label=label)
              for key, label in [('right', 'Anatomical right'), ('left', 'Anatomical left'), ('center', 'Spine')]]
    fig.legend(handles=legend, loc='lower center', bbox_to_anchor=(0.5, 0.035), ncol=3, frameon=False)
    fig.text(0.5, 0.012, 'Original coordinates · front camera +Z / left-side camera +X · no pose edits', ha='center', fontsize=9)
    output = ROOT / f'{source.stem}-keyframes.png'
    fig.savefig(output)
    plt.close(fig)
    metrics = preview.compute_metrics(data, joints)
    metrics.update({
        'both_wrists_above_head_frames': int(((joints[:, 20, 1] > joints[:, 15, 1]) & (joints[:, 21, 1] > joints[:, 15, 1])).sum()),
        'left_shoulder_to_wrist_reach_range_m': [float(left_reach.min()), float(left_reach.max())],
        'right_shoulder_to_wrist_reach_range_m': [float(right_reach.min()), float(right_reach.max())],
        'keyframe_indices_zero_based': frames,
    })
    return {
        'source': str(source.relative_to(ROOT)), 'source_sha256': hashlib.sha256(raw).hexdigest(),
        'prompt': data['prompt'], 'seed': data['seed'], 'device': data['device'],
        'generation_seconds': data['generation_seconds'], 'truncated': data['truncated'], 'metrics': metrics,
        'output': {'path': output.name, 'bytes': output.stat().st_size,
                   'sha256': hashlib.sha256(output.read_bytes()).hexdigest()},
    }


if __name__ == '__main__':
    plt.rcParams.update({'font.size': 9, 'axes.titlesize': 10, 'axes.labelsize': 8})
    records = [render(name) for name in ('stretch', 'boxing')]
    result = {'method': 'Fixed orthographic projections of original 22-joint coordinates. No new GIFs or generated motion.',
              'limitation': 'No fingers, contacts, forces, native UI, or VRM retargeting were tested.', 'records': records}
    (ROOT / 'novel-keyframe-provenance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, indent=2))
