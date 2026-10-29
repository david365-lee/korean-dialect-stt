# STT 비교 테스트 — stt-test.test-ai.cloud

한 번의 녹음을 두 STT에 동시에 보내 결과를 나란히 비교하는 테스트 페이지 (2026-10-29 사용자 요청).

| 카드 | LiteLLM 모델 | 설정 |
| --- | --- | --- |
| jaewon-stt (튜닝) | `jaewon-stt` | Whisper large-v3 + 사투리·기술 용어 prompt. v0.1, **파인튜닝 전** |
| Whisper large-v3 (순수) | `groq-whisper-large-v3` | `language=ko`만 지정 (1차 평가 ②와 동일) |

- 정답 문장을 입력하면 각 결과의 CER과 틀린 글자를 표시한다(`evaluate_baseline.py`와 같은 계산).
- "LLM 의미 해석도 보기"를 켜면 두 전사를 **한 번의** `gemma4-26b-a4b` 호출에 함께 넣어, 카드마다 아주 짧은 의미 해석(30자 이내)·표준어·의도를 표시하고, 두 판독의 의미가 같은지(다르면 핵심 차이)를 상단 배너로 보여 준다. 각 전사는 다른 쪽으로 보정하지 않고 받아쓴 그대로 해석한다.
- 녹음 최대 60초, 파일 10MB(Ingress 11m). 녹음은 저장하지 않는다.
- 서버는 의존성 없는 Node 22(`server.js`), 페이지는 `index.html`. 둘 다 ConfigMap `stt-test-app`으로 마운트한다.
- 남용 방지: IP당 분당 8회(`RATE_PER_MINUTE`), 동시 2건, 같은 Origin만 허용. Groq 무료 한도를 MDAI와 공유하므로 완화하지 않는다.
- 외부 노출은 공유 F5 NGINX Ingress(`nginx`)와 기존 `*.test-ai.cloud` 와일드카드 DNS를 쓴다. Cloudflare 변경 없음.

## 배포

```powershell
kubectl apply -k web/stt-test                                                        # 전체 배포·코드 갱신
powershell -NoProfile -ExecutionPolicy Bypass -File web/stt-test/Set-SttTestKey.ps1   # 최초 1회 (키 Secret)
```

- `kustomization.yaml`의 `configMapGenerator`가 `server.js`/`index.html`로 내용 해시가 붙은 ConfigMap을 만든다. 코드를 고치고 `apply -k`만 다시 하면 Deployment가 자동으로 롤링 업데이트된다.
- Pod는 Deployment(replicas 1)가 관리한다. Pod 삭제·노드/클러스터 재시작 후에도 자동으로 다시 뜬다(2026-10-29 Pod 삭제 → 2초 내 재생성 확인). Secret이 없으면 kubelet이 대기하다가 Secret이 생기면 자동 시작한다.
- API 키는 별도 가상 키를 만들지 않고, 사용자가 통합한 단일 가상 키(`rag-test/rag-mcp-client`의 `API_KEY`)를 `stt-test/stt-test-litellm`으로 복사한다. 이 키를 바꾸는 경우에만 `Set-SttTestKey.ps1`을 다시 실행한다.
- Argo CD GitOps(다른 앱과 같은 GitLab 저장소 + 자동 동기화)는 GitLab 프로젝트 생성 권한이 필요해 적용하지 않았다.

검증(2026-10-29): 공개 URL `/healthz` 200, 합성 음성 1건 실제 비교 호출 성공(jaewon-stt 0.75초, Whisper 0.56초, 표준어 변환 포함).
