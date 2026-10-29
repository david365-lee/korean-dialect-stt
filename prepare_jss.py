"""Build a real-speech Jeju evaluation set from Kakao Brain JSS + JIT (CC BY-NC-SA 4.0).

Non-commercial evaluation only: do not use these clips to train a commercial model and
do not redistribute them. Only the transcript and a random sample of clips are fetched
from the 4.4GB archive through HTTP range requests; the standard-Korean reference comes
from the JIT Jejueo-Korean parallel corpus when the exact Jejueo sentence is found.
"""
import argparse
import io
import json
import random
import re
import zipfile
from pathlib import Path
import requests
from remotezip import RemoteZip
from evaluate_baseline import compact

JSS = 'https://www.kaggle.com/api/v1/datasets/download/bryanpark/jejueo-single-speaker-speech-dataset'
JIT = 'https://www.kaggle.com/api/v1/datasets/download/bryanpark/jit-dataset'


def resolve(url):
    # Kaggle redirects to a signed storage URL that supports range requests.
    return requests.get(url, allow_redirects=False, timeout=60).headers.get('location', url)


def detokenize(text):
    # JIT is tokenized with spaces before punctuation ("가게 ." -> "가게.").
    return re.sub(r'\s+([.,?!])', r'\1', text).strip()


def jit_pairs():
    archive = zipfile.ZipFile(io.BytesIO(requests.get(resolve(JIT), timeout=300).content))
    pairs = {}
    for split in ('train', 'dev', 'test'):
        jeju = archive.read('je.' + split).decode('utf-8').splitlines()
        standard = archive.read('ko.' + split).decode('utf-8').splitlines()
        pairs.update((compact(j), detokenize(k)) for j, k in zip(jeju, standard) if j.strip())
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', default='runs/2026-10-29-jeju')
    parser.add_argument('--count', type=int, default=150)
    parser.add_argument('--seed', type=int, default=29)
    parser.add_argument('--max-seconds', type=float, default=15)
    args = parser.parse_args()

    out = Path(args.out)
    (out / 'clips').mkdir(parents=True, exist_ok=True)
    pairs = jit_pairs()
    with RemoteZip(resolve(JSS)) as archive:
        transcript = next(n for n in archive.namelist() if n.endswith('.tsv'))
        rows = []
        for line in archive.read(transcript).decode('utf-8').splitlines():
            path, text, _, seconds = line.split('\t')[:4]
            if float(seconds) <= args.max_seconds:
                rows.append((path, text.strip(), float(seconds)))
        names = {Path(n).name: n for n in archive.namelist()}
        random.Random(args.seed).shuffle(rows)
        with open(out / 'manifest.jsonl', 'w', encoding='utf-8') as manifest:
            for path, text, seconds in rows[:args.count]:
                member = names[Path(path).name]
                target = out / 'clips' / Path(path).name
                if not target.exists():
                    target.write_bytes(archive.read(member))
                row = {'audio': 'clips/' + target.name, 'region': 'jeju', 'speaker': 'jss-1',
                       'verbatim': text, 'terms': [], 'synthetic': False, 'seconds': seconds,
                       'source': 'Kakao Brain JSS (CC BY-NC-SA 4.0)'}
                if compact(text) in pairs:
                    row['standard'] = pairs[compact(text)]
                manifest.write(json.dumps(row, ensure_ascii=False) + '\n')
    matched = sum(1 for line in open(out / 'manifest.jsonl', encoding='utf-8') if '"standard"' in line)
    print(json.dumps({'clips': min(args.count, len(rows)), 'with_standard_reference': matched,
                      'jit_pairs': len(pairs), 'eligible': len(rows)}))


if __name__ == '__main__':
    main()
