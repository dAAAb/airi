"""Reuse fixed skeleton projections for actual saved MLX outputs."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('novel_keyframes', ROOT / 'render-novel-keyframes.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


if __name__ == '__main__':
    preview.plt.rcParams.update({'font.size': 9, 'axes.titlesize': 10, 'axes.labelsize': 8})
    records = [preview.render(name, ROOT / 'backends' / f'{name}-mlx-2.json') for name in ('stretch', 'boxing')]
    for record in records:
        data = json.loads((ROOT / record['source']).read_text())
        joints = preview.np.asarray(data['joints'], dtype=float)
        record.update(backend=data['backend'], precision=data['precision'])
        record['metrics']['minimum_joint_y_m'] = float(joints[:, :, 1].min())
        record['metrics']['left_ankle_peak_y_m'] = float(joints[:, 7, 1].max())
        record['metrics']['right_ankle_peak_y_m'] = float(joints[:, 8, 1].max())
    result = {
        'method': 'Original MLX-2 joint frames in fixed +Z front and +X left-side projections. No coordinate changes.',
        'limitation': 'Output skeleton QA only. No native App, VRM retargeting, fingers, physics or contact validation.',
        'records': records,
    }
    (ROOT / 'mlx-keyframe-provenance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    total = sum(p.stat().st_size for pattern in ('*.gif', '*.png') for p in ROOT.glob(pattern))
    assert total < 10_000_000, total
    print(json.dumps({'total_preview_bytes': total, 'records': records}, indent=2))
