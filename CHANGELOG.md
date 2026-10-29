# Changelog

## v0.1.0 — 2026-10-29 · 1차분 (학습 미완료)

기준선 측정과 평가 체계까지 포함한 첫 릴리스. **STT 파인튜닝은 수행하지 않았다.**

### 포함

- 2단계 설계: 방언 그대로 전사(`jaewon-stt`) + LLM 표준어·의도 정규화
- LiteLLM 고정 이름 `jaewon-stt`(Groq whisper-large-v3 + 사투리·기술 용어 prompt, 학습 전 임시 백엔드), `jaewon-tts`(Google Cloud TTS ko-KR-Standard-A)
- 평가 도구 `evaluate_baseline.py`: 방언 CER, 용어 재현율, 정규화 후 용어 복원, 표준어 CER, 의도 JSON 성공률, oracle 모드, 합성 데이터 차단
- 증강 도구 `synthesize_augmentation.py` (기본 dry run), 제주어 실음성 평가셋 `prepare_jss.py`, 그래프 `make_charts.py`
- 결과: 합성 진단 120건(①②③), 실제 제주어 150건 기준선(④⑤⑥, 집계만)

### 주요 수치 (학습 전)

| 지표 | 값 |
| --- | --- |
| 합성 CER (기본 → jaewon-stt) | 47.8% → 25.3% |
| 용어 재현율 (기본 → STT → LLM 후) | 1.7% → 34.2% → 68.3% |
| 실제 제주어 CER (기본 → jaewon-stt) | 30.1% → 28.5% |
| STT 오류 비용 (표준어 CER) | 합성 +11.5%p, 제주 +8.4%p |

### 미완료 (2차 이후)

- 경상·전라·충청·강원 실음성 기준선 (AI Hub 데이터 필요)
- 학습 데이터 구성, Whisper LoRA 파인튜닝 (외부 GPU 필요)
- 정규화 LLM 개선, 파인튜닝 모델 비교·카나리 교체, Dialect Gateway API 구현
