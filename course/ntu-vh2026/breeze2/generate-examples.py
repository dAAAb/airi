"""Exercise the local HTTP adapter and save new WAVs plus measured timings."""
import argparse
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8881)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'local/tts')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cases = json.loads((Path(__file__).resolve().parents[1] / 'testcases.json').read_text())['tts']
    results = []
    for case in cases:
        payload = {'model': 'breeze2-vits', 'voice': 'breeze2-zh-tw', 'input': case['text'], 'response_format': 'wav'}
        request = urllib.request.Request(f'http://127.0.0.1:{args.port}/v1/audio/speech',
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        started = time.perf_counter()
        try:
            response = urllib.request.urlopen(request, timeout=60)
        except urllib.error.HTTPError as error:
            response = error
        data = response.read()
        elapsed = time.perf_counter() - started
        if response.status != case['expect_status']:
            raise RuntimeError(f'{case["id"]}: expected {case["expect_status"]}, received {response.status}: {data[:300]!r}')
        row = {'id': case['id'], 'status': response.status, 'text': case['text'], 'http_seconds': elapsed}
        if response.status == 200:
            with wave.open(io.BytesIO(data)) as audio:
                row['audio_seconds'] = audio.getnframes() / audio.getframerate()
                row['sample_rate'] = audio.getframerate()
            filename = case['id'] + '.wav'
            (args.output / filename).write_bytes(data)
            row['file'] = filename
        else:
            row['error'] = json.loads(data)
        results.append(row)
        print(case['id'], response.status, round(elapsed, 3), 'seconds')
    (args.output / 'results.json').write_text(json.dumps({'scope': 'HTTP wall time. Not first-audio or conversation latency. No listening score.', 'results': results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
