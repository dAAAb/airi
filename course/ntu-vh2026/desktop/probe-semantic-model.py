"""Probe local LLM action choices. Does not prove that a VRM rendered the action."""
import argparse
import datetime
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
CASES = [
    ('celebration', '我終於通過期中考了，替我跳支舞慶祝吧！', ['dance', 'celebrate']),
    ('negative_context', '我今天很難過，考試沒有過，不要跳舞。', ['idle', 'nod']),
    ('greeting', '早安！跟我揮揮手。', ['wave']),
    ('slow_motion', '我想看慢慢左右搖擺的舞。', ['sway']),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', default='http://127.0.0.1:12434')
    parser.add_argument('--model', default='qwen3.5:0.8b')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--language', choices=['mandarin', 'taigi'], default='mandarin')
    parser.add_argument('--cases', nargs='+', choices=[row[0] for row in CASES])
    args = parser.parse_args()
    url = urllib.parse.urlsplit(args.endpoint)
    if url.scheme != 'http' or url.hostname not in ('localhost', '127.0.0.1', '::1') or url.username or url.password:
        raise SystemExit('This classroom probe uses local HTTP endpoints only.')
    source = (ROOT / 'packages/stage-ui/src/constants/local-character-motion.ts').read_text()
    motion_prompt = source.split('`', 2)[1]
    base_prompt = ('你是親切的台語助理。請用自然的臺灣台語漢字回答，毋通用華語。說話正文每擺一到兩句，總共三十五字以內。正文毋通用英文字、數字、羅馬字、表情符號或 Markdown。數量請用漢字。若無把握就講無把握，毋通假仙。直接回答問題，毋免重複自我介紹。'
                   if args.language == 'taigi' else '你是親切的虛擬人課程助理。使用繁體中文，簡短回答一到兩句。不要輸出工具指令、Markdown 或思考過程。')
    report = {'tested_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
              'model': args.model, 'endpoint': args.endpoint, 'language': args.language, 'base_prompt': base_prompt, 'options': {'temperature': 0.2, 'num_ctx': 4096, 'num_predict': 160},
              'scope': 'Synthetic single-turn semantic selection. Not native rendering or a general benchmark.',
              'message_layout': 'system + user text followed by AIRI runtime-context block',
              'runtime_prompt': motion_prompt, 'cases': []}
    for name, text, expected in CASES:
        if args.cases and name not in args.cases:
            continue
        request = {'model': args.model, 'stream': False, 'think': False, 'options': report['options'],
                   'messages': [{'role': 'system', 'content': base_prompt},
                                {'role': 'user', 'content': text + '\n[Context]\n- system:airi-runtime-prompt: ' + motion_prompt}]}
        started = time.perf_counter()
        try:
            req = urllib.request.Request(args.endpoint.rstrip('/') + '/api/chat',
                                         json.dumps(request).encode(), {'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=180) as response:
                result = json.load(response)
            content = result.get('message', {}).get('content', '')
            match = re.search(r'<\|ACT\s+(\{.*?\})\|>', content, re.DOTALL)
            action = json.loads(match.group(1)) if match else None
            row = {'case': name, 'input': text, 'expected_motion': expected, 'response': content, 'act': action,
                   'motion_matches': isinstance(action, dict) and action.get('motion') in expected,
                   'elapsed_seconds': round(time.perf_counter() - started, 3),
                   'eval_count': result.get('eval_count'), 'eval_duration_ns': result.get('eval_duration')}
        except Exception as error:
            row = {'case': name, 'input': text, 'error': str(error), 'elapsed_seconds': round(time.perf_counter() - started, 3)}
        report['cases'].append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
