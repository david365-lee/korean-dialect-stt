# Changelog

## v0.1.1 — 2026-10-29 · 비교 테스트 페이지, 2차 보류

- README를 한 문서로 통합: 비교 테스트 페이지(화면, 동작 흐름, 실제 사례), 2차 보류 결정(비용·기간·로컬 CPU 추정·재개 조건)을 본문에 포함. `docs/PIPELINE.md`, `docs/PHASE2-DECISION.md`는 README로 흡수해 삭제.
- 테스트 페이지: 두 전사를 한 번의 LLM 호출로 해석해 카드별 의미·표준어·의도와 의미 일치 판정 표시.
- `web/stt-test/`: 한 번의 녹음을 `jaewon-stt`(튜닝)와 순수 Whisper에 동시에 보내 비교하는 웹페이지. 정답 입력 시 CER·틀린 글자 표시, 표준어 변환 옵션. 의존성 없는 Node 22 서버 + kustomize 매니페스트(내용 해시 ConfigMap으로 코드 변경 시 자동 롤링, Deployment가 Pod 자동 복구). API 키는 Kubernetes Secret에서만 읽음.
- README 6장: 2차 파인튜닝 보류 결정 — 비용(권장 약 30만 원)·기간(4~6주)·로컬 CPU 학습 추정(수 주, 운영 서비스 영향)과 재개 조건.

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
