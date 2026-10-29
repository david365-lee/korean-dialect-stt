"""Generate training-only code-switching audio with jaewon-tts.

Fills dialect sentence templates with English technical terms. Output rows are marked
synthetic=true and must never be used for evaluation. Dry run by default: each
synthesis consumes provider credit, so pass --execute with an explicit --limit.
"""
import argparse
import itertools
import json
import os
import random
import time
from pathlib import Path
import requests

HERE = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--templates', default=HERE / 'data' / 'templates.json')
    parser.add_argument('--terms', default=HERE / 'data' / 'terms.json')
    parser.add_argument('--out', default='augmented')
    parser.add_argument('--model', default='jaewon-tts')
    parser.add_argument('--voices', default='ko-KR-Standard-A,ko-KR-Standard-B,ko-KR-Standard-C,ko-KR-Standard-D')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--seed', type=int, default=29)
    parser.add_argument('--delay', type=float, default=0.5)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()

    templates = json.loads(Path(args.templates).read_text(encoding='utf-8'))
    terms = json.loads(Path(args.terms).read_text(encoding='utf-8'))
    pairs = list(itertools.product(templates, terms))
    random.Random(args.seed).shuffle(pairs)
    voices = args.voices.split(',')
    rows = []
    for index, (template, term) in enumerate(pairs[:args.limit]):
        rows.append({'audio': f'clips/syn-{index:05d}.mp3', 'region': template['region'],
                     'voice': voices[index % len(voices)], 'synthetic': True, 'terms': [term],
                     'verbatim': template['verbatim'].format(term=term),
                     'standard': template['standard'].format(term=term)})
    if not args.execute:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
        print(f'# dry run: {len(rows)} rows; add --execute to synthesize.')
        return

    out = Path(args.out)
    (out / 'clips').mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers['Authorization'] = 'Bearer ' + os.environ['LITELLM_API_KEY']
    base = os.environ['LITELLM_BASE_URL'].rstrip('/')
    with open(out / 'manifest.jsonl', 'a', encoding='utf-8') as manifest:
        for row in rows:
            target = out / row['audio']
            if target.exists():
                continue
            response = session.post(base + '/audio/speech', timeout=120, json={
                'model': args.model, 'input': row['verbatim'], 'voice': row['voice'], 'response_format': 'mp3'})
            response.raise_for_status()
            target.write_bytes(response.content)
            manifest.write(json.dumps(row, ensure_ascii=False) + '\n')
            print(row['audio'], len(response.content), flush=True)
            time.sleep(args.delay)


if __name__ == '__main__':
    main()
