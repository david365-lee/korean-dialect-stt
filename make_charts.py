"""Render README comparison charts as static SVG (light + dark) from results/.

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
    'light': {'surface': '#fcfcfb', 'text': '#0b0b0b', 'muted': '#52514e', 'grid': '#e4e3df', 'axis': '#b9b8b2',
              'base': '#eb6834', 'jaewon': '#2a78d6', 'oracle': '#1baf7a', 'llm': '#6250d6', 'target': '#8a8984'},
    'dark': {'surface': '#1a1a19', 'text': '#f0efec', 'muted': '#c3c2b7', 'grid': '#2e2e2c', 'axis': '#57564f',
             'base': '#d95926', 'jaewon': '#3987e5', 'oracle': '#199e70', 'llm': '#9085e9', 'target': '#9a9991'},
}
NAMES = {'base': 'Whisper 기본 (prompt 없음)', 'jaewon': 'jaewon-stt (STT)', 'llm': 'jaewon-stt + LLM 정규화',
         'oracle': '정답 전사 + LLM (oracle, 상한)', 'target': '파인튜닝 목표'}
FONT = "Pretendard, 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif"
REGIONS = [('gyeongsang', '경상'), ('gangwon', '강원'), ('jeju', '제주'), ('chungcheong', '충청'), ('jeolla', '전라'), ('ALL', '전체')]


def bar_path(x, y, width, height, radius=4):
    # Flat at the baseline, 4px rounded data-end.
    if width <= 0:
        return ''
    r = min(radius, width, height / 2)
    return (f'M{x},{y} H{x + width - r} Q{x + width},{y} {x + width},{y + r} '
            f'V{y + height - r} Q{x + width},{y + height} {x + width - r},{y + height} H{x} Z')


def hbar_chart(name, title, subtitle, categories, series, domain=100, unit='%', note=None, lower_better=False):
    """categories: labels; series: [(entity_key, [values per category], dashed?)]."""
    for mode, theme in THEMES.items():
        left, right, width = 156, 64, 760
        bar, gap, group_gap = 14, 2, 18
        top = 92
        group_h = len(series) * bar + (len(series) - 1) * gap
        plot_w = width - left - right
        height = top + len(categories) * (group_h + group_gap) + 40 + (18 if note else 0)
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
                 f'font-family="{FONT}" role="img" aria-label="{escape(title)}">',
                 f'<rect width="100%" height="100%" rx="8" fill="{theme["surface"]}"/>',
                 f'<text x="20" y="30" font-size="16" font-weight="600" fill="{theme["text"]}">{escape(title)}</text>',
                 f'<text x="20" y="50" font-size="12" fill="{theme["muted"]}">{escape(subtitle)}'
                 f'{" · 낮을수록 좋음" if lower_better else " · 높을수록 좋음"}</text>']
        # Legend (always for >= 2 series); text stays in text ink, the swatch carries identity.
        lx = 20
        for key, _, dashed in series:
            label = NAMES[key]
            swatch = (f'<rect x="{lx}" y="62" width="12" height="12" rx="3" fill="none" stroke="{theme[key]}" '
                      f'stroke-width="2" stroke-dasharray="3 2"/>' if dashed else
                      f'<rect x="{lx}" y="62" width="12" height="12" rx="3" fill="{theme[key]}"/>')
            parts.append(swatch + f'<text x="{lx + 18}" y="72.5" font-size="12" fill="{theme["muted"]}">{escape(label)}</text>')
            lx += 18 + 7.2 * len(label) + 22
        plot_bottom = height - 30 - (18 if note else 0)
        for tick in range(0, domain + 1, 25 if domain == 100 else max(domain // 4, 1)):
            x = left + plot_w * tick / domain
            parts.append(f'<line x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" y2="{plot_bottom}" stroke="{theme["grid"]}" stroke-width="1"/>')
            parts.append(f'<text x="{x:.1f}" y="{plot_bottom + 16}" font-size="11" text-anchor="middle" fill="{theme["muted"]}">{tick}{unit}</text>')
        parts.append(f'<line x1="{left}" y1="{top - 6}" x2="{left}" y2="{plot_bottom}" stroke="{theme["axis"]}" stroke-width="1"/>')
        for index, category in enumerate(categories):
            gy = top + index * (group_h + group_gap)
            parts.append(f'<text x="{left - 12}" y="{gy + group_h / 2 + 4.5}" font-size="13" text-anchor="end" '
                         f'fill="{theme["text"]}">{escape(category)}</text>')
            for s_index, (key, values, dashed) in enumerate(series):
                value = values[index]
                if value is None:
                    continue
                y = gy + s_index * (bar + gap)
                w = plot_w * min(value, domain) / domain
                if dashed:
                    parts.append(f'<path d="{bar_path(left, y + 1, w, bar - 2)}" fill="none" stroke="{theme[key]}" '
                                 f'stroke-width="2" stroke-dasharray="4 3"><title>{escape(NAMES[key])}: {value:g}{unit}</title></path>')
                else:
                    parts.append(f'<path d="{bar_path(left, y, max(w, 1.5), bar)}" fill="{theme[key]}">'
                                 f'<title>{escape(NAMES[key])}: {value:g}{unit}</title></path>')
                parts.append(f'<text x="{left + w + 6:.1f}" y="{y + bar - 3}" font-size="11.5" fill="{theme["muted"]}">{value:g}{unit}</text>')
        if note:
            parts.append(f'<text x="20" y="{height - 14}" font-size="11.5" fill="{theme["muted"]}">{escape(note)}</text>')
        parts.append('</svg>')
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f'{name}-{mode}.svg').write_text('\n'.join(parts), encoding='utf-8')


def pct(value):
    return None if value is None else round(value * 100, 1)


def main():
    load = lambda f: json.loads((SYN / f).read_text(encoding='utf-8'))['summary']
    jaewon, base, oracle = load('report-jaewon-stt.json'), load('report-whisper-noprompt.json'), load('report-oracle-normalize.json')
    jeju = json.loads(JEJU.read_text(encoding='utf-8'))
    j_all, b_all, o_all = (jeju[k]['summary'] for k in ('jaewon-stt+llm', 'whisper-noprompt', 'oracle-normalize'))
    labels = [label for _, label in REGIONS]

    hbar_chart('syn-cer-by-region', '권역별 방언 전사 CER — prompt 효과', '합성 진단셋 120건 (권역당 24건)', labels,
               [('base', [pct(base[r]['mean_cer']) for r, _ in REGIONS], False),
                ('jaewon', [pct(jaewon[r]['mean_cer']) for r, _ in REGIONS], False)], lower_better=True)
    hbar_chart('syn-term-by-region', '권역별 기술 용어 재현율 — STT → LLM 복원', '합성 진단셋 · 라틴 표기 그대로 포함된 비율', labels,
               [('base', [pct(base[r]['term_recall']) for r, _ in REGIONS], False),
                ('jaewon', [pct(jaewon[r]['term_recall']) for r, _ in REGIONS], False),
                ('llm', [pct(jaewon[r]['normalized_term_recall']) for r, _ in REGIONS], False)])
    hbar_chart('stage-term-funnel', '기술 용어가 살아남는 비율 — 단계별', '합성 진단셋 전체 120건',
               ['STT 결과', 'LLM 정규화 후'],
               [('base', [pct(base['ALL']['term_recall']), None], False),
                ('jaewon', [pct(jaewon['ALL']['term_recall']), None], False),
                ('llm', [None, pct(jaewon['ALL']['normalized_term_recall'])], False),
                ('oracle', [100.0, pct(oracle['ALL']['normalized_term_recall'])], False)],
               note='oracle의 STT 결과 100%는 정답 전사를 그대로 넣었다는 뜻(측정값 아님).')
    hbar_chart('std-cer-stt-cost', '표준어 변환 CER — STT 오류 비용', 'LLM 정규화 결과 vs 정답 표준어 (gemma4-26b-a4b)',
               ['합성 진단 (request)', '실제 제주어 (faithful)'],
               [('llm', [pct(jaewon['ALL']['mean_standard_cer']), pct(j_all['mean_standard_cer'])], False),
                ('oracle', [pct(oracle['ALL']['mean_standard_cer']), pct(o_all['mean_standard_cer'])], False)],
               lower_better=True, note='두 막대의 차이 = STT 오류가 더한 비용 (합성 +11.5%p, 제주 +8.4%p).')
    hbar_chart('dataset-cer', '방언 전사 CER — 합성 진단 vs 실제 제주어', '같은 모델, 다른 데이터',
               ['합성 진단 120건', '실제 제주어 150건'],
               [('base', [pct(base['ALL']['mean_cer']), pct(b_all['mean_cer'])], False),
                ('jaewon', [pct(jaewon['ALL']['mean_cer']), pct(j_all['mean_cer'])], False)],
               lower_better=True, note='prompt 효과: 기술 용어 문장 −22.5%p, 일상 제주어 −1.6%p.')
    hist = jeju['cer_histogram']
    buckets = list(hist['jaewon-stt'])
    hbar_chart('jeju-cer-histogram', '실제 제주어 문장별 CER 분포', 'JSS 150문장 · 구간별 문장 수', buckets,
               [('base', [hist['whisper-noprompt'][b] for b in buckets], False),
                ('jaewon', [hist['jaewon-stt'][b] for b in buckets], False)], domain=50, unit='건',
               note='jaewon-stt는 40% 이상 고오류 문장을 45건 → 32건으로 줄였다.')
    hbar_chart('targets-higher', '현재 vs 파인튜닝 목표 — 높을수록 좋은 지표', '목표치는 계획이며 측정값이 아님',
               ['STT 용어 재현율', '정규화 후 용어 복원', '의도 JSON 성공률'],
               [('jaewon', [pct(jaewon['ALL']['term_recall']), pct(jaewon['ALL']['normalized_term_recall']),
                            pct(jaewon['ALL']['intent_json_rate'])], False),
                ('target', [90, 95, 100], True)])
    hbar_chart('targets-lower', '현재 vs 파인튜닝 목표 — 낮을수록 좋은 지표', '목표치는 계획이며 측정값이 아님',
               ['실제 제주어 CER', '합성 표준어 CER'],
               [('jaewon', [pct(j_all['mean_cer']), pct(jaewon['ALL']['mean_standard_cer'])], False),
                ('target', [17.5, 22.2], True)], lower_better=True,
               note='제주 CER 목표 = 기준선 대비 상대 30~50% 감소의 중간값, 표준어 CER 목표 = oracle 수준.')
    print(sorted(p.name for p in OUT.glob('*.svg')))


if __name__ == '__main__':
    main()
