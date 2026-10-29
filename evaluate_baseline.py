"""Baseline evaluation: jaewon-stt verbatim transcription + LLM standard-Korean normalization.

Manifest (JSONL), one utterance per line:
  {"audio": "clips/gs-0001.wav", "region": "gyeongsang", "speaker": "gs-17",
   "verbatim": "야, Kubernetes Pod가 와 이래 자꾸 죽노? 로그 좀 봐도.",
   "standard": "Kubernetes Pod가 왜 계속 종료되는지 로그를 확인해 주세요.",
   "terms": ["Kubernetes", "Pod"], "synthetic": false}

Synthetic (TTS) rows are rejected: evaluation must use real speech only. --diagnostic
allows them for a separately labelled pipeline diagnostic that is never a baseline.
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
import requests

NORMALIZE_PROMPT = """너는 한국어 방언 음성 인식 결과를 표준어 요청으로 바꾸는 변환기다.
입력은 방언을 그대로 받아쓴 문장이며 영어 기술 용어가 섞여 있을 수 있다.
규칙:
- 의미를 바꾸지 말고 표준어 존댓말 요청문으로 바꾼다. 감탄사·호칭("야")은 뺀다.
- 영어 기술 용어는 원래 영어 표기로 유지한다. 한글로 잘못 받아쓴 용어(예: 키버넷 → Kubernetes)는 바로잡는다.
- 맥락상 "죽다"는 Pod/프로세스의 종료·재시작을 뜻한다.
JSON만 출력한다: {"standard": "...", "intent": {"action": "...", "target": "...", "symptom": "..."}}"""

# Everyday dialect speech (e.g. Jeju JSS): translate faithfully, keeping sentence type and politeness.
FAITHFUL_PROMPT = """너는 한국어 방언(제주어 포함) 문장을 표준어로 옮기는 번역기다.
입력은 방언을 들리는 대로 받아쓴 문장이며 인식 오류가 있을 수 있다.
규칙:
- 뜻을 그대로 표준어로 옮긴다. 문장 종류(평서·의문·명령)와 높임 수준을 유지하고, 요청문으로 바꾸거나 내용을 덧붙이지 않는다.
- 영어 기술 용어가 있으면 영어 표기로 유지한다.
JSON만 출력한다: {"standard": "...", "intent": {"action": "...", "target": "...", "symptom": "..."}}"""
PROMPTS = {'request': NORMALIZE_PROMPT, 'faithful': FAITHFUL_PROMPT}


ARCHAIC = re.compile('([ᄀ-ᄒ])([ᆞᆢ])([ᆨ-ᇂ]?)')


def modernize(text):
    # Jeju transcripts use arae-a (ᆞ/ᆢ), which ASR never emits; map to the nearest modern vowel (ㅏ/ㅕ).
    def compose(match):
        lead = ord(match.group(1)) - 0x1100
        vowel = 0 if match.group(2) == 'ᆞ' else 6
        tail = ord(match.group(3)) - 0x11A7 if match.group(3) else 0
        return chr(0xAC00 + (lead * 21 + vowel) * 28 + tail)
    return ARCHAIC.sub(compose, unicodedata.normalize('NFD', text))


def compact(text):
    # CER is computed on letters/digits only, case-folded, so spacing/punctuation conventions do not count.
    text = unicodedata.normalize('NFC', modernize(text)).casefold()
    return re.sub(r'[\W_]+', '', text)


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def cer(reference, hypothesis):
    reference, hypothesis = compact(reference), compact(hypothesis)
    return edit_distance(reference, hypothesis) / max(len(reference), 1)


class Gateway:
    def __init__(self, base_url, api_key):
        self.base = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers['Authorization'] = 'Bearer ' + api_key

    def post(self, path, **kwargs):
        # Provider free tiers return 429 under bursts; back off instead of failing the run.
        for attempt in range(5):
            response = self.session.post(self.base + path, timeout=120, **kwargs)
            if response.status_code != 429:
                break
            time.sleep(20 * (attempt + 1))
        response.raise_for_status()
        return response.json()

    def transcribe(self, model, path, language=None):
        data = {'model': model, **({'language': language} if language else {})}
        with open(path, 'rb') as audio:
            return self.post('/audio/transcriptions', data=data, files={'file': (Path(path).name, audio)})['text'].strip()

    def normalize(self, model, verbatim, style='request'):
        content = self.post('/chat/completions', json={
            'model': model, 'temperature': 0, 'max_tokens': 300,
            'messages': [{'role': 'system', 'content': PROMPTS[style]}, {'role': 'user', 'content': verbatim}]
        })['choices'][0]['message']['content'] or ''
        match = re.search(r'\{.*\}', content, re.S)
        try:
            return json.loads(match.group(0)) if match else {'standard': ''}
        except json.JSONDecodeError:
            return {'standard': ''}


def term_recall(terms, text):
    return sum(term.casefold() in text.casefold() for term in terms)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('manifest')
    parser.add_argument('--stt-model', default='jaewon-stt')
    parser.add_argument('--llm-model', default='gemini-3.5-flash-lite')
    parser.add_argument('--language', help='Send an explicit language (e.g. ko) with each transcription.')
    parser.add_argument('--skip-normalize', action='store_true')
    parser.add_argument('--prompt', choices=sorted(PROMPTS), default='request',
                        help='request: tech-support request rewrite; faithful: plain standard-Korean translation.')
    parser.add_argument('--oracle', action='store_true',
                        help='Skip STT; normalize the reference transcript to measure stage B alone.')
    parser.add_argument('--diagnostic', action='store_true', help='Allow synthetic rows (diagnostic, not a baseline).')
    parser.add_argument('--delay', type=float, default=0, help='Seconds between rows (provider rate limits).')
    parser.add_argument('--limit', type=int, default=0, help='Evaluate at most N rows (provider quota).')
    parser.add_argument('--out', default='baseline-report.json')
    args = parser.parse_args()

    rows = [json.loads(line) for line in Path(args.manifest).read_text(encoding='utf-8').splitlines() if line.strip()]
    synthetic = any(row.get('synthetic') for row in rows)
    if synthetic and not args.diagnostic:
        sys.exit('Manifest contains synthetic rows; evaluation sets must be real speech only.')
    if args.limit:
        rows = rows[:args.limit]
    gateway = Gateway(os.environ['LITELLM_BASE_URL'], os.environ['LITELLM_API_KEY'])
    root = Path(args.manifest).parent
    results = []
    for row in rows:
        terms = row.get('terms', [])
        if args.oracle:
            hypothesis = row['verbatim']
        else:
            hypothesis = gateway.transcribe(args.stt_model, root / row['audio'], args.language)
        item = {'audio': row['audio'], 'region': row['region'], 'reference': row['verbatim'],
                'hypothesis': hypothesis, 'cer': round(cer(row['verbatim'], hypothesis), 4),
                'terms': len(terms), 'terms_found': term_recall(terms, hypothesis)}
        if not args.skip_normalize:
            normalized = gateway.normalize(args.llm_model, hypothesis, args.prompt)
            standard = str(normalized.get('standard', ''))
            item['normalized'] = normalized
            item['normalized_terms_found'] = term_recall(terms, standard)
            item['intent_present'] = isinstance(normalized.get('intent'), dict) and bool(normalized['intent'].get('action'))
            if row.get('standard'):
                item['standard_cer'] = round(cer(row['standard'], standard), 4)
        results.append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)
        time.sleep(args.delay)

    def aggregate(items):
        terms = sum(i['terms'] for i in items)
        stats = {'utterances': len(items),
                 'mean_cer': round(sum(i['cer'] for i in items) / len(items), 4),
                 'term_recall': round(sum(i['terms_found'] for i in items) / terms, 4) if terms else None}
        scored = [i for i in items if 'normalized' in i]
        if scored:
            stats['normalized_term_recall'] = round(sum(i['normalized_terms_found'] for i in scored) / terms, 4) if terms else None
            stats['intent_json_rate'] = round(sum(i['intent_present'] for i in scored) / len(scored), 4)
            cers = [i['standard_cer'] for i in scored if 'standard_cer' in i]
            if cers:
                stats['mean_standard_cer'] = round(sum(cers) / len(cers), 4)
        return stats

    regions = defaultdict(list)
    for item in results:
        regions[item['region']].append(item)
    summary = {region: aggregate(items) for region, items in sorted(regions.items())}
    summary['ALL'] = aggregate(results)
    report = {'set_type': 'synthetic-diagnostic' if synthetic else 'real-speech',
              'stt_model': 'reference-transcript (oracle)' if args.oracle else args.stt_model,
              'language': args.language, 'llm_model': None if args.skip_normalize else args.llm_model,
              'prompt': None if args.skip_normalize else args.prompt,
              'summary': summary, 'results': results}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
