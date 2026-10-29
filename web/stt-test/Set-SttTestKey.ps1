# Copies the shared LiteLLM virtual key (rag-test/rag-mcp-client API_KEY, the single consolidated
# application key) into stt-test/stt-test-litellm and restarts the page. The key is never printed.
# Rerun after Consolidate-VirtualKeys.ps1 rotates the shared key.
$ErrorActionPreference = 'Stop'
$encoded = kubectl -n rag-test get secret rag-mcp-client -o jsonpath='{.data.API_KEY}'
if ($LASTEXITCODE -or -not $encoded) { throw 'Cannot read rag-test/rag-mcp-client' }
$secret = @{
  apiVersion = 'v1'; kind = 'Secret'; type = 'Opaque'
  metadata = @{ name = 'stt-test-litellm'; namespace = 'stt-test' }
  data = @{ 'api-key' = $encoded }
}
$secret | ConvertTo-Json -Depth 5 -Compress | kubectl apply -f -
if ($LASTEXITCODE) { throw 'Secret apply failed' }
kubectl -n stt-test rollout restart deployment/stt-test
kubectl -n stt-test rollout status deployment/stt-test --timeout=180s
