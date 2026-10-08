"""Plot saved MotionGPT joint frames without resampling, mirroring, or synthesis."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'airi-motiongpt-matplotlib'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
NAMES = ('right-wave-cpu', 'bow-cpu', 'dance-cpu')
PARENTS = (-1, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9, 12, 13, 14, 16, 17, 18, 19)
COLORS = {'right': '#d95f02', 'left': '#008c95', 'center': '#697386'}


def joint_color(name):
    return COLORS['right' if name.startswith('right_') else 'left' if name.startswith('left_') else 'center']


def limits(joints):
    # Keep global translation and equal world-unit scale. Only camera projections differ.
    lo = joints.min(axis=(0, 1))
    hi = joints.max(axis=(0, 1))
    width = max(2.05, hi[0] - lo[0] + 0.4, hi[2] - lo[2] + 0.4)
    height = max(2.0, hi[1] + 0.16)
    return [((lo[a] + hi[a] - width) / 2, (lo[a] + hi[a] + width) / 2) for a in (0, 2)], (-0.08, height)


def make_axes(ax, axis, bounds, title):
    ax.set(xlim=bounds[0][axis], ylim=bounds[1], title=title,
           xlabel='+X = initial anatomical left' if axis == 0 else '+Z = initial forward',
           ylabel='Y up (m)')
    ax.set_aspect('equal', adjustable='box')
    ax.grid(alpha=0.18)
    ax.axhline(0, color='#939ba7', linewidth=1)
    for spine in ax.spines.values():
        spine.set_visible(False)


def make_artists(ax, names):
    bones = [ax.plot([], [], color=joint_color(names[i]), linewidth=3.2,
                     marker='o', markersize=3.5)[0] for i in range(1, 22)]
    root, = ax.plot([], [], 'o', color='#252b35', markersize=5)
    return bones, root


def update(artists, pose, axis):
    horizontal = 0 if axis == 0 else 2
    for index, line in enumerate(artists[0], start=1):
        pair = pose[[PARENTS[index], index]]
        line.set_data(pair[:, horizontal], pair[:, 1])
    artists[1].set_data([pose[0, horizontal]], [pose[0, 1]])


def compute_metrics(data, joints):
    names = data['joint_names']
    right = joints[:, names.index('right_wrist')]
    left = joints[:, names.index('left_wrist')]
    spine = joints[:, names.index('neck')] - joints[:, names.index('pelvis')]
    lean = np.degrees(np.arctan2(spine[:, 2], spine[:, 1]))
    return {
        'frames': len(joints), 'fps': data['fps'], 'playback_seconds': len(joints) / data['fps'],
        'right_wrist_y_range_m': [float(right[:, 1].min()), float(right[:, 1].max())],
        'left_wrist_y_range_m': [float(left[:, 1].min()), float(left[:, 1].max())],
        'right_wrist_peak_y_frame': int(right[:, 1].argmax()),
        'root_displacement_m': (joints[-1, 0] - joints[0, 0]).tolist(),
        'root_range_xyz_m': np.ptp(joints[:, 0], axis=0).tolist(),
        'neck_to_pelvis_forward_lean_degrees': {
            'first': float(lean[0]), 'maximum': float(lean.max()),
            'maximum_frame': int(lean.argmax()), 'last': float(lean[-1]),
        },
    }


def render(name):
    source = ROOT / f'{name}.json'
    raw = source.read_bytes()
    data = json.loads(raw)
    joints = np.asarray(data['joints'], dtype=float)
    assert joints.shape[1:] == (22, 3) and np.isfinite(joints).all()
    assert data['coordinate_system'] == 'right-handed-y-up'
    assert data['initial_forward'] == '+Z' and data['anatomical_left'] == '+X'
    bounds = limits(joints)
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 6.3), dpi=85)
    fig.subplots_adjust(top=0.76, bottom=0.17, wspace=0.28)
    fig.suptitle(f'MotionGPT Base · {name}\n{data["prompt"]}', fontsize=13, y=0.98)
    time_label = fig.text(0.5, 0.83, '', ha='center', fontsize=11, family='monospace')
    artists = []
    for axis, (ax, title) in enumerate(zip(axes, ('Front · camera at +Z', 'Left side · camera at +X'))):
        make_axes(ax, axis, bounds, title)
        artists.append(make_artists(ax, data['joint_names']))
    legend = [Line2D([0], [0], color=COLORS[key], linewidth=3, label=label)
              for key, label in [('right', 'Anatomical right'), ('left', 'Anatomical left'), ('center', 'Spine')]]
    fig.legend(handles=legend, loc='lower center', bbox_to_anchor=(0.5, 0.075), ncol=3, frameon=False)
    fig.text(0.5, 0.025, 'Original 22-joint frames · fixed world axes · no mirror / retiming / motion edits',
             ha='center', fontsize=9, color='#596170')
    images = []
    for frame, pose in enumerate(joints):
        for axis in range(2):
            update(artists[axis], pose, axis)
        time_label.set_text(f'frame {frame + 1:03d}/{len(joints)}    t = {frame / data["fps"]:.2f} s    {data["fps"]} fps')
        fig.canvas.draw()
        images.append(Image.fromarray(np.asarray(fig.canvas.buffer_rgba())[:, :, :3]).convert('P', palette=Image.Palette.ADAPTIVE, colors=64))
    target = ROOT / f'{name}-skeleton.gif'
    images[0].save(target, save_all=True, append_images=images[1:], duration=1000 // data['fps'],
                   loop=0, optimize=True, disposal=2)
    plt.close(fig)
    metrics = compute_metrics(data, joints)
    key = metrics['right_wrist_peak_y_frame'] if name.startswith('right-wave') else metrics['neck_to_pelvis_forward_lean_degrees']['maximum_frame'] if name.startswith('bow') else len(joints) // 2
    frames = [0, key, len(joints) - 1]
    fig, axes = plt.subplots(2, 3, figsize=(12.8, 8.4), dpi=120)
    fig.subplots_adjust(top=0.85, bottom=0.12, hspace=0.48, wspace=0.25)
    fig.suptitle(f'{data["prompt"]}\nOriginal frames: start / {"peak right wrist" if name.startswith("right-wave") else "maximum forward lean" if name.startswith("bow") else "midpoint"} / end', fontsize=12, y=0.97)
    for axis in range(2):
        for col, frame in enumerate(frames):
            ax = axes[axis, col]
            make_axes(ax, axis, bounds, f'{"Front" if axis == 0 else "Left side"} · frame {frame + 1} · {frame / data["fps"]:.2f}s')
            update(make_artists(ax, data['joint_names']), joints[frame], axis)
    fig.legend(handles=legend, loc='lower center', bbox_to_anchor=(0.5, 0.015), ncol=3, frameon=False)
    contact = ROOT / f'{name}-keyframes.png'
    fig.savefig(contact)
    plt.close(fig)
    return {
        'source': source.name, 'source_sha256': hashlib.sha256(raw).hexdigest(),
        'prompt': data['prompt'], 'model': data['model'], 'seed': data['seed'],
        'device': data['device'], 'generation_seconds': data['generation_seconds'],
        'metrics': metrics,
        'outputs': [{'path': p.name, 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                    for p in (target, contact)],
    }


def main():
    plt.rcParams.update({'font.size': 10, 'axes.titlesize': 11, 'axes.labelsize': 9,
                         'figure.facecolor': '#ffffff', 'axes.facecolor': '#ffffff'})
    records = [render(name) for name in NAMES]
    report = {
        'method': 'Orthographic front (+Z camera) and left-side (+X camera) projections of original HumanML3D-22 joint coordinates.',
        'playback': 'One GIF frame for each saved joint frame, original 20 fps. Loops only at the end.',
        'transformations': 'Projection only. No mirrored axes, model rotations, root centering, interpolation, filtering, or resampling.',
        'units': 'Model coordinate meters, no independent physical scale calibration.',
        'limitation': 'Skeleton-output audit only. Does not validate native App or VRM retargeting.',
        'records': records,
    }
    total = sum(p['bytes'] for record in records for p in record['outputs'])
    assert total < 10_000_000, total
    report['preview_total_bytes'] = total
    (ROOT / 'skeleton-preview-provenance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'preview_total_bytes': total, 'sources': [r['source'] for r in records]}, indent=2))


if __name__ == '__main__':
    main()
