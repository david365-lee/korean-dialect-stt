> persona 저장소의 설계 메모를 옮긴 문서. 경로 `deploy/litellm/register_jaewon_audio.py` → `litellm/register_jaewon_audio.py`, `samples/dialect-stt/` → 저장소 루트. 최신 결과는 README 참고.

# 사투리·한영 혼용 STT 파이프라인 — 2026-10-29

목표: 경상·전라·충청·강원·제주 사투리와 한국어·영어 기술 용어 혼용을 인식하는 범용 STT. 예) "야, Kubernetes Pod가 와 이래 자꾸 죽노? 로그 좀 봐도." → "Kubernetes Pod가 왜 계속 종료되는지 로그를 확인해 주세요."

## 1. 두 단계 분리

| 단계 | 입력 → 출력 | 담당 |
| --- | --- | --- |
| A. 방언 전사 | 음성 → 들린 그대로의 방언 문장 | `jaewon-stt` (Whisper, 이후 파인튜닝 모델로 교체) |
| B. 표준어 변환·의도 해석 | A 결과 → 표준어 요청 + `{action, target, symptom}` | LLM (`gemini-3.5-flash-lite` 기준선) |

Whisper가 표준어를 바로 출력하도록 학습하지 않는다. 발화와 정답이 달라져 CER 평가가 불가능하고, 환각이 늘며, "죽노"(종료/재시작 반복) 같은 해석 문제가 STT 오류와 섞인다.

## 2. LiteLLM 모델 (2026-10-29 등록)

| 이름 | 현재 백엔드 | 상태 |
| --- | --- | --- |
| `jaewon-stt` | `groq/whisper-large-v3`, `language=ko`, 방언·기술 용어 편향 prompt | 활성, 검증 완료 |
| `jaewon-tts` | `vertex_ai/chirp` + `ko-KR-Standard-A` (Google Cloud TTS Standard) | 활성, 검증 완료 |

호출자가 바뀌지 않도록 고정 이름(alias)으로 만들었다. 파인튜닝 모델이 준비되면 `jaewon-stt`의 `litellm_params`만 클러스터 밖 엔드포인트로 교체한다. 자격증명은 기존 `groq-whisper-large-v3`, `google-cloud-tts-standard` 항목에서 서버 내부로 복사했고 출력하지 않았다. 등록·검증 소스: `deploy/litellm/register_jaewon_audio.py`.

첫 왕복 검증(TTS → STT): 원문 "야, Kubernetes Pod가 와 이래 자꾸 죽노? 로그 좀 봐도." → 전사 "야, 키버넷 POD가 와 이래 자꾸 죽노? 로그 좀 봐도." (CER 0.37). 사투리 어미는 정확했지만 한국어 발음으로 읽힌 기술 용어가 무너졌다. 같은 전사를 B단계 LLM에 넣으면 "Kubernetes Pod가 왜 이렇게 자꾸 종료되나요? 로그를 좀 봐주세요." / `{action: 로그 확인, target: Kubernetes Pod, symptom: 잦은 종료}`로 복원됐다. 합성 음성 1건이므로 기준 성능이 아니라 동작 확인이다.

## 3. 데이터

- 실제 방언 음성(핵심): AI Hub 지역별 방언 발화(경상·전라·충청·강원·제주), 중·노년층 방언 데이터. 방언형/표준형 병기 전사가 있어 A 정답과 B 학습 쌍을 동시에 얻는다. 신청 자격·이용 조건 확인 필요.
- 표준어 유지: KsponSpeech 혼합(망각 방지).
- 한영 혼용: 공개 데이터가 가장 부족 → TTS 증강 집중.
- 표기 규칙: 영어 기술 용어는 라틴 문자(`Kubernetes Pod`)로 통일. 정답 표기가 섞이면 모델 출력도 섞인다.

## 4. TTS 증강 원칙

- TTS는 방언 억양을 재현하지 못한다. 방언 학습용이 아니라 기술 용어 노출용으로 쓴다(`samples/dialect-stt/data/templates.json` × `terms.json`).
- 합성 비율 전체의 20~30% 이하. 합성 음성은 평가셋 금지(`evaluate_baseline.py`가 `synthetic: true` 행을 거부).
- 실제 녹음에는 속도·잡음·RIR 증강.
- 약관: 학습 데이터 생성 목적의 TTS 출력 사용 조건을 사용 전에 확인한다(Gemini API의 경쟁 모델 개발 조항 등). 실존 화자 음성 복제는 동의 필수.
- 비용: Cloud TTS는 무료 체험 크레딧을 소비한다. 증강 스크립트는 기본 dry run이며 `--execute --limit N`이 필요하다.

## 5. 학습·평가

- 기반: `whisper-large-v3` / `large-v3-turbo` + LoRA. 학습·서빙 모두 클러스터 밖 GPU. LiteLLM에는 외부 엔드포인트만 등록하며, 삭제한 클러스터 내 모델 Deployment를 재생성하지 않는다.
- 지표: 지역별 CER, 기술 용어 재현율, 한영 혼용 구간 오류율, B단계 표준어 CER·의도 일치율. 화자 단위로 학습/평가 분리.

## 6. 진행 순서

1. **기준선** (도구 준비 완료): 실제 방언 음성 평가셋으로 `samples/dialect-stt/evaluate_baseline.py` 실행.
2. 기준선에서 CER·용어 재현율이 나쁜 지역과 혼용 구간만 골라 파인튜닝 데이터 구성.
3. 파인튜닝 모델을 같은 평가셋으로 비교한 뒤 `jaewon-stt` 백엔드 교체 결정.

미구현: 실제 방언 평가셋 확보, GPU 학습 환경, 파인튜닝 코드. 이 문서는 제안이 아니라 1단계 도구와 두 모델 등록까지가 배포된 범위다.
