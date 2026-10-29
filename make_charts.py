"""Render README charts as static SVG (light + dark) from results/ and the phase-2 estimates.

python make_charts.py  ->  docs/charts/<name>-light.svg, <name>-dark.svg
Stdlib only. Colors follow the entity, not the chart: the same configuration keeps
the same hue everywhere. Palette validated (adjacent CVD/normal-vision, both modes).
"""
import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / 'docs' / 'charts'
SYN = ROOT / 'results' / '2026-10-29-synthetic'
JEJU = ROOT / 'results' / '2026-10-29-jeju' / 'summary.json'

THEMES = {
    'light': {'surface': '#fcfcfb', 'band': '#f3f2ee', 'text': '#0b0b0b', 'muted': '#52514e', 'grid': '#e4e3df',
              'axis': '#b9b8b2', 'base': '#eb6834', 'jaewon': '#2a78d6', 'oracle': '#1baf7a', 'llm': '#6250d6',
              'target': '#8a8984', 'good': '#0a7d0a', 'bad': '#b42323', 'accent1': '#2a78d6', 'accent2': '#6250d6'},
    'dark': {'surface': '#1a1a19', 'band': '#232321', 'text': '#f0efec', 'muted': '#c3c2b7', 'grid': '#2e2e2c',
             'axis': '#57564f', 'base': '#d95926', 'jaewon': '#3987e5', 'oracle': '#199e70', 'llm': '#9085e9',
             'target': '#9a9991', 'good': '#5fd35f', 'bad': '#ff9b93', 'accent1': '#3987e5', 'accent2': '#9085e9'},
}
NAMES = {'base': 'Whisper 기본 (prompt 없음)', 'jaewon': 'jaewon-stt (prompt 튜닝)', 'llm': 'jaewon-stt + LLM',
         'oracle': '정답 전사 + LLM (oracle)', 'target': '파인튜닝 목표', 'gpu': '외부 GPU', 'cpu': '로컬 CPU'}
FONT = "Pretendard, 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif"
REGIONS = [('gyeongsang', '경상'), ('gangwon', '강원'), ('jeju', '제주'), ('chungcheong', '충청'), ('jeolla', '전라'), ('ALL', '전체')]
WIDTH = 820


def bar_path(x, y, width, height, radius=5):
    # Flat at the baseline, rounded data-end.
    if width <= 0:
        return ''
    r = min(radius, width, height / 2)
    return (f'M{x},{y} H{x + width - r} Q{x + width},{y} {x + width},{y + r} '
            f'V{y + height - r} Q{x + width},{y + height} {x + width - r},{y + height} H{x} Z')


def frame(theme, height, title, subtitle, uid):
    # Card with a gradient accent band and a bold title.
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" '
            f'font-family="{FONT}" role="img" aria-label="{escape(title)}">',
            f'<defs><linearGradient id="g{uid}" x1="0" x2="1"><stop offset="0" stop-color="{theme["accent1"]}"/>'
            f'<stop offset="1" stop-color="{theme["accent2"]}"/></linearGradient></defs>',
            f'<rect width="100%" height="100%" rx="12" fill="{theme["surface"]}" stroke="{theme["grid"]}"/>',
            f'<rect x="0" y="0" width="{WIDTH}" height="6" rx="3" fill="url(#g{uid})"/>',
            f'<text x="24" y="40" font-size="19" font-weight="700" fill="{theme["text"]}">{escape(title)}</text>',
            f'<text x="24" y="62" font-size="12.5" fill="{theme["muted"]}">{escape(subtitle)}</text>']


def hbar_chart(name, title, subtitle, categories, series, domain=100, unit='%', note=None, lower_better=False,
               fmt=None, badges=None, colors=None, tick=None):
    """series: [(entity_key, values, dashed)]; colors: per-category override for single-series charts;
    badges: {category_index: text} shown right of the group (e.g. a delta)."""
    fmt = fmt or (lambda v: f'{v:g}{unit}')
    for mode, theme in THEMES.items():
        left, right = 168, 120
        bar, gap, group_gap = 20, 3, 20
        legend = len(series) > 1 or any(dashed for *_, dashed in series)
        top = 108 if legend else 86
        group_h = len(series) * bar + (len(series) - 1) * gap
        plot_w = WIDTH - left - right
        height = top + len(categories) * (group_h + group_gap) + 36 + (22 if note else 0)
        direction = '낮을수록 좋음 ↓' if lower_better else '높을수록 좋음 ↑'
        parts = frame(theme, height, title, f'{subtitle} · {direction}', name.replace('-', ''))
        if legend:
            lx = 24
            for key, _, dashed in series:
                label = NAMES[key]
                swatch = (f'<rect x="{lx}" y="76" width="14" height="14" rx="3" fill="none" stroke="{theme[key]}" '
                          f'stroke-width="2" stroke-dasharray="3 2"/>' if dashed else
                          f'<rect x="{lx}" y="76" width="14" height="14" rx="3" fill="{theme[key]}"/>')
                parts.append(swatch + f'<text x="{lx + 20}" y="87.5" font-size="12.5" fill="{theme["muted"]}">{escape(label)}</text>')
                lx += 20 + 7.6 * len(label) + 26
        plot_bottom = height - 30 - (22 if note else 0)
        step = tick or (25 if domain == 100 else max(domain // 4, 1))
        for t in range(0, domain + 1, step):
            x = left + plot_w * t / domain
            parts.append(f'<line x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{plot_bottom}" stroke="{theme["grid"]}"/>')
            parts.append(f'<text x="{x:.1f}" y="{plot_bottom + 17}" font-size="11" text-anchor="middle" fill="{theme["muted"]}">{escape(fmt(t))}</text>')
        parts.append(f'<line x1="{left}" y1="{top - 8}" x2="{left}" y2="{plot_bottom}" stroke="{theme["axis"]}"/>')
        for index, category in enumerate(categories):
            gy = top + index * (group_h + group_gap)
            parts.append(f'<text x="{left - 14}" y="{gy + group_h / 2 + 5}" font-size="13.5" font-weight="600" text-anchor="end" '
                         f'fill="{theme["text"]}">{escape(category)}</text>')
            ends = []
            for s_index, (key, values, dashed) in enumerate(series):
                value = values[index]
                if value is None:
                    continue
                color = theme[colors[index]] if colors else theme[key]
                y = gy + s_index * (bar + gap)
                w = plot_w * min(value, domain) / domain
                label = f'{escape(NAMES[key])}: {escape(fmt(value))}'
                if dashed:
                    parts.append(f'<path d="{bar_path(left, y + 1, w, bar - 2)}" fill="none" stroke="{color}" '
                                 f'stroke-width="2" stroke-dasharray="5 3"><title>{label}</title></path>')
                else:
                    parts.append(f'<path d="{bar_path(left, y, max(w, 2), bar)}" fill="{color}"><title>{label}</title></path>')
                parts.append(f'<text x="{left + w + 7:.1f}" y="{y + bar - 5}" font-size="13" font-weight="700" '
                             f'fill="{theme["text"]}">{escape(fmt(value))}</text>')
                ends.append(left + w + 7 + 7.5 * len(fmt(value)))
            if badges and index in badges:
                text = badges[index]
                bx = max(ends) + 10
                good = text.startswith('−') if lower_better else text.startswith('+')
                tone = theme['good'] if good else theme['muted']
                parts.append(f'<rect x="{bx:.1f}" y="{gy + group_h / 2 - 11}" width="{8.2 * len(text) + 14:.1f}" height="22" rx="11" '
                             f'fill="none" stroke="{tone}"/><text x="{bx + 7:.1f}" y="{gy + group_h / 2 + 4.5}" font-size="12" '
                             f'font-weight="700" fill="{tone}">{escape(text)}</text>')
        if note:
            parts.append(f'<text x="24" y="{height - 14}" font-size="12" fill="{theme["muted"]}">{escape(note)}</text>')
        parts.append('</svg>')
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f'{name}-{mode}.svg').write_text('\n'.join(parts), encoding='utf-8')


def kpi_card(name, tiles):
    """tiles: [(label, big, sub, entity_key)] — a hero row of headline numbers."""
    for mode, theme in THEMES.items():
        height = 190
        parts = frame(theme, height, 'korean-dialect-stt 1차 핵심 지표', 'v0.1.1 · 파인튜닝 전 기준선 · 2026-10-29', 'kpi')
        w = (WIDTH - 48 - 3 * 14) / 4
        for i, (label, big, sub, key) in enumerate(tiles):
            x = 24 + i * (w + 14)
            parts.append(f'<rect x="{x:.1f}" y="80" width="{w:.1f}" height="92" rx="10" fill="{theme["band"]}"/>')
            parts.append(f'<rect x="{x:.1f}" y="80" width="5" height="92" rx="2.5" fill="{theme[key]}"/>')
            parts.append(f'<text x="{x + 18:.1f}" y="104" font-size="12.5" fill="{theme["muted"]}">{escape(label)}</text>')
            parts.append(f'<text x="{x + 18:.1f}" y="140" font-size="26" font-weight="800" fill="{theme["text"]}">{escape(big)}</text>')
            parts.append(f'<text x="{x + 18:.1f}" y="161" font-size="12" fill="{theme["muted"]}">{escape(sub)}</text>')
        parts.append('</svg>')
        (OUT / f'{name}-{mode}.svg').write_text('\n'.join(parts), encoding='utf-8')


def pct(value):
    return None if value is None else round(value * 100, 1)


def won(v):
    return f'{v:g}만 원'


def main():
    load = lambda f: json.loads((SYN / f).read_text(encoding='utf-8'))['summary']
    jaewon, base, oracle = load('report-jaewon-stt.json'), load('report-whisper-noprompt.json'), load('report-oracle-normalize.json')
    jeju = json.loads(JEJU.read_text(encoding='utf-8'))
    j_all, b_all, o_all = (jeju[k]['summary'] for k in ('jaewon-stt+llm', 'whisper-noprompt', 'oracle-normalize'))
    labels = [label for _, label in REGIONS]
    delta = lambda a, b: f'{(b - a) * 100:+.1f}%p'.replace('-', '−')

    OUT.mkdir(parents=True, exist_ok=True)
    kpi_card('kpi', [('prompt 효과 · 합성 CER', f'{pct(base["ALL"]["mean_cer"])}→{pct(jaewon["ALL"]["mean_cer"])}%', '기술 용어 문장, −22.5%p', 'jaewon'),
                     ('기술 용어 재현율', f'{pct(base["ALL"]["term_recall"])}→{pct(jaewon["ALL"]["normalized_term_recall"])}%', 'STT + LLM 복원', 'llm'),
                     ('실제 제주어 CER', f'{pct(j_all["mean_cer"])}%', '원어민 150문장 기준선', 'base'),
                     ('의도 JSON 성공률', f'{pct(jaewon["ALL"]["intent_json_rate"]):g}%', '후속 자동화 연결 가능', 'oracle')])

    hbar_chart('dataset-cer', '방언 전사 CER — prompt 효과는 데이터에 따라 다르다', '같은 모델, 합성 진단 vs 실제 제주어',
               ['합성 진단 120건', '실제 제주어 150건'],
               [('base', [pct(base['ALL']['mean_cer']), pct(b_all['mean_cer'])], False),
                ('jaewon', [pct(jaewon['ALL']['mean_cer']), pct(j_all['mean_cer'])], False)],
               lower_better=True, badges={0: delta(base['ALL']['mean_cer'], jaewon['ALL']['mean_cer']),
                                          1: delta(b_all['mean_cer'], j_all['mean_cer'])})
    hbar_chart('stage-term-funnel', '기술 용어가 살아남는 비율 — 단계별', '합성 진단셋 120건 · 영어 표기 그대로 남은 비율',
               ['STT 결과', 'LLM 해석 후'],
               [('base', [pct(base['ALL']['term_recall']), None], False),
                ('jaewon', [pct(jaewon['ALL']['term_recall']), None], False),
                ('llm', [None, pct(jaewon['ALL']['normalized_term_recall'])], False),
                ('oracle', [100.0, pct(oracle['ALL']['normalized_term_recall'])], False)],
               note='oracle의 STT 결과 100%는 정답 전사를 그대로 넣었다는 뜻(측정값 아님).')
    hbar_chart('syn-cer-by-region', '권역별 방언 전사 CER', '합성 진단셋 (권역당 24건)', labels,
               [('base', [pct(base[r]['mean_cer']) for r, _ in REGIONS], False),
                ('jaewon', [pct(jaewon[r]['mean_cer']) for r, _ in REGIONS], False)], lower_better=True,
               badges={i: delta(base[r]['mean_cer'], jaewon[r]['mean_cer']) for i, (r, _) in enumerate(REGIONS)})
    hbar_chart('syn-term-by-region', '권역별 기술 용어 재현율', '합성 진단셋 · STT → LLM 복원', labels,
               [('base', [pct(base[r]['term_recall']) for r, _ in REGIONS], False),
                ('jaewon', [pct(jaewon[r]['term_recall']) for r, _ in REGIONS], False),
                ('llm', [pct(jaewon[r]['normalized_term_recall']) for r, _ in REGIONS], False)])
    hbar_chart('std-cer-stt-cost', '표준어 CER — STT 오류 비용', 'LLM 결과 vs 정답 표준어 (gemma4-26b-a4b)',
               ['합성 진단', '실제 제주어'],
               [('llm', [pct(jaewon['ALL']['mean_standard_cer']), pct(j_all['mean_standard_cer'])], False),
                ('oracle', [pct(oracle['ALL']['mean_standard_cer']), pct(o_all['mean_standard_cer'])], False)],
               lower_better=True, badges={0: '+11.5%p', 1: '+8.4%p'},
               note='배지 = 두 막대의 차이 = STT 오류가 더한 비용.')
    hist = jeju['cer_histogram']
    buckets = list(hist['jaewon-stt'])
    hbar_chart('jeju-cer-histogram', '실제 제주어 문장별 CER 분포', 'JSS 150문장 · 구간별 문장 수', buckets,
               [('base', [hist['whisper-noprompt'][b] for b in buckets], False),
                ('jaewon', [hist['jaewon-stt'][b] for b in buckets], False)], domain=50, unit='건', tick=10,
               lower_better=True, note='오류 40% 이상 문장: 45건 → 32건.')

    # Phase 2 estimates (A100 80GB, 500 h data, +20% on GPU hours and cost). Kept here so README and charts agree.
    models = ['whisper-small', 'whisper-medium', 'large-v3-turbo LoRA', 'large-v3 LoRA', 'large-v3 전체 학습']
    hours = [7, 22, 47, 56, 84]
    costs = [16, 21, 30, 33, 42]
    pick = ['target', 'target', 'jaewon', 'target', 'target']
    hbar_chart('gpu-cost-by-model', '외부 GPU — 모델별 총비용 (20% 상향)', 'A100 80GB · 학습+스토리지+서빙 테스트+예비비',
               models, [('gpu', costs, False)], domain=50, unit='', fmt=won, tick=10, lower_better=True, colors=pick,
               badges={i: f'{h}시간' for i, h in enumerate(hours)}, note='파랑 = 권장(large-v3-turbo LoRA). 배지 = GPU 사용 시간.')
    gpus = ['H100 80GB', 'A100 80GB', 'L40S 48GB', 'L4 24GB']
    hbar_chart('gpu-cost-by-type', '외부 GPU — GPU 종류별 총비용 (20% 상향)', 'large-v3-turbo LoRA 기준',
               gpus, [('gpu', [26, 30, 33, 33], False)], domain=50, unit='', fmt=won, tick=10, lower_better=True,
               colors=['jaewon', 'jaewon', 'target', 'target'],
               badges={0: '22시간', 1: '47시간', 2: '94시간', 3: '187시간'}, note='총비용은 비슷하고 차이는 대기 시간 — 빠른 GPU가 일정에 유리.')
    hbar_chart('gpu-vs-cpu-days', '학습 완료까지 걸리는 기간 — GPU vs CPU', '실험 포함 · 일 단위 (CPU는 범위의 중간값)',
               ['GPU H100 (turbo)', 'GPU A100 (turbo)', 'CPU 디코더만', 'CPU 데이터 축소', 'CPU 전체 LoRA'],
               [('gpu', [1, 2, 6, 5, 42], False)], domain=60, unit='일', tick=10, lower_better=True,
               colors=['jaewon', 'jaewon', 'base', 'base', 'base'],
               badges={0: '약 22시간', 1: '약 47시간', 2: '5–7일', 3: '4–6일', 4: '4주–2개월'},
               note='파랑 = 외부 GPU, 주황 = 로컬 CPU. CPU는 같은 PC의 클러스터 서비스에 영향.')
    hbar_chart('targets-higher', '현재 vs 파인튜닝 목표 — 높을수록 좋은 지표', '목표치는 계획이며 측정값이 아님',
               ['STT 용어 재현율', 'LLM 후 용어 복원', '의도 JSON'],
               [('jaewon', [pct(jaewon['ALL']['term_recall']), pct(jaewon['ALL']['normalized_term_recall']),
                            pct(jaewon['ALL']['intent_json_rate'])], False),
                ('target', [90, 95, 100], True)])
    hbar_chart('targets-lower', '현재 vs 파인튜닝 목표 — 낮을수록 좋은 지표', '목표치는 계획이며 측정값이 아님',
               ['실제 제주어 CER', '합성 표준어 CER'],
               [('jaewon', [pct(j_all['mean_cer']), pct(jaewon['ALL']['mean_standard_cer'])], False),
                ('target', [17.5, 22.2], True)], lower_better=True)
    print(sorted(p.name for p in OUT.glob('*.svg')))


if __name__ == '__main__':
    main()
