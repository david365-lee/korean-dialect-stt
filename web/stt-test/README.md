# web/stt-test

STT 비교 테스트 페이지(https://stt-test.test-ai.cloud) 소스. 기능·구성·운영 설명은 저장소 [README 2장](../../README.md#2-비교-테스트-페이지)에 있다.

```powershell
kubectl apply -k web/stt-test                                                        # 배포·코드 갱신 (자동 롤링)
powershell -NoProfile -ExecutionPolicy Bypass -File web/stt-test/Set-SttTestKey.ps1   # 최초 1회 / 키 교체 시
```
