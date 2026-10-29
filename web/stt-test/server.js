// STT side-by-side test: one recording -> jaewon-stt and plain Whisper in parallel.
// Zero dependencies (Node 22 fetch/FormData/Blob). Audio is never written to disk.
'use strict';
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const PORT = Number(process.env.PORT || 8080);
const BASE = (process.env.LITELLM_BASE_URL || 'http://litellm.litellm.svc:4000/v1').replace(/\/$/, '');
const KEY = process.env.LITELLM_API_KEY;
const LLM = process.env.NORMALIZE_MODEL || 'gemma4-26b-a4b';
const MAX_BYTES = 10 * 1024 * 1024;
const PER_MINUTE = Number(process.env.RATE_PER_MINUTE || 8);
const MAX_ACTIVE = 2;
const MODELS = [
  { id: 'tuned', model: 'jaewon-stt', fields: {} },
  { id: 'plain', model: 'groq-whisper-large-v3', fields: { language: 'ko' } },
];
const PROMPT = `너는 한국어 방언 음성 인식 결과를 표준어로 바꾸는 변환기다.
입력은 방언을 들리는 대로 받아쓴 문장이며 영어 기술 용어가 섞여 있을 수 있다.
규칙: 뜻을 바꾸지 말고 표준어로 옮긴다. 영어 기술 용어는 영어 표기로 유지하고, 한글로 잘못 받아쓴 용어(예: 키버넷 → Kubernetes)는 바로잡는다.
JSON만 출력한다: {"standard": "...", "intent": {"action": "...", "target": "...", "symptom": "..."}}`;
const INDEX = fs.readFileSync(path.join(__dirname, 'index.html'));
const hits = new Map();
let active = 0;

function clientIp(req) {
  return req.headers['cf-connecting-ip'] || String(req.headers['x-forwarded-for'] || '').split(',')[0].trim() || req.socket.remoteAddress;
}

function limited(ip) {
  const now = Date.now();
  const recent = (hits.get(ip) || []).filter((t) => now - t < 60000);
  recent.push(now);
  hits.set(ip, recent);
  return recent.length > PER_MINUTE;
}

function send(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(body));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > MAX_BYTES) { reject(Object.assign(new Error('too_large'), { status: 413 })); req.destroy(); return; }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

async function call(pathname, init) {
  // Provider errors are reduced to a status code: raw bodies can echo request details.
  const started = Date.now();
  const response = await fetch(BASE + pathname, { ...init, headers: { Authorization: 'Bearer ' + KEY, ...(init.headers || {}) }, signal: AbortSignal.timeout(90000) });
  const ms = Date.now() - started;
  if (!response.ok) return { error: response.status === 429 ? 'provider_rate_limited' : 'provider_error_' + response.status, ms };
  return { data: await response.json(), ms };
}

function extension(type) {
  // Providers detect the codec from the file name, so map browser/device MIME types explicitly.
  const map = [['m4a', 'm4a'], ['mp4', 'm4a'], ['aac', 'm4a'], ['mpeg', 'mp3'], ['mp3', 'mp3'], ['ogg', 'ogg'],
    ['wav', 'wav'], ['flac', 'flac'], ['webm', 'webm']];
  return (map.find(([needle]) => type.includes(needle)) || [null, 'webm'])[1];
}

async function transcribe(spec, audio, type) {
  const form = new FormData();
  form.append('model', spec.model);
  for (const [k, v] of Object.entries(spec.fields)) form.append(k, v);
  form.append('file', new Blob([audio], { type }), 'recording.' + extension(type));
  const result = await call('/audio/transcriptions', { method: 'POST', body: form });
  return { id: spec.id, model: spec.model, text: result.data ? String(result.data.text || '').trim() : '', ms: result.ms, error: result.error };
}

async function normalize(text) {
  if (!text) return null;
  const result = await call('/chat/completions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: LLM, temperature: 0, max_tokens: 300, messages: [{ role: 'system', content: PROMPT }, { role: 'user', content: text }] }),
  });
  if (!result.data) return { error: result.error, ms: result.ms };
  const content = result.data.choices?.[0]?.message?.content || '';
  try {
    const parsed = JSON.parse((content.match(/\{[\s\S]*\}/) || ['{}'])[0]);
    return { standard: String(parsed.standard || ''), intent: parsed.intent || null, ms: result.ms };
  } catch {
    return { error: 'unparsable', ms: result.ms };
  }
}

async function compare(req, res, url) {
  const origin = req.headers.origin;
  if (origin && new URL(origin).host !== req.headers.host) return send(res, 403, { error: 'origin_mismatch' });
  const type = String(req.headers['content-type'] || '');
  if (!/^audio\/|^video\/webm/.test(type)) return send(res, 415, { error: 'audio_required' });
  if (limited(clientIp(req))) return send(res, 429, { error: 'rate_limited', limit_per_minute: PER_MINUTE });
  if (active >= MAX_ACTIVE) return send(res, 503, { error: 'busy' });
  active += 1;
  try {
    const audio = await readBody(req);
    if (audio.length < 1000) return send(res, 400, { error: 'audio_too_short' });
    const results = await Promise.all(MODELS.map((spec) => transcribe(spec, audio, type.split(';')[0])));
    if (url.searchParams.get('normalize') === '1') {
      const normalized = await Promise.all(results.map((r) => normalize(r.text)));
      results.forEach((r, i) => { r.normalized = normalized[i]; });
    }
    send(res, 200, { bytes: audio.length, normalize_model: LLM, results });
  } catch (error) {
    send(res, error.status || 500, { error: error.status === 413 ? 'too_large' : 'server_error' });
  } finally {
    active -= 1;
  }
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (req.method === 'GET' && (url.pathname === '/' || url.pathname === '/index.html')) {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache',
      'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; media-src 'self' blob:; img-src 'self' data:; connect-src 'self'",
      'Permissions-Policy': 'microphone=(self)' });
    return res.end(INDEX);
  }
  if (req.method === 'GET' && url.pathname === '/healthz') return send(res, 200, { ok: true, models: MODELS.map((m) => m.model) });
  if (req.method === 'POST' && url.pathname === '/api/compare') return compare(req, res, url);
  send(res, 404, { error: 'not_found' });
});
setInterval(() => { const now = Date.now(); for (const [ip, t] of hits) if (!t.some((x) => now - x < 60000)) hits.delete(ip); }, 60000).unref();
if (!KEY) { console.error('LITELLM_API_KEY is required'); process.exit(1); }
server.listen(PORT, () => console.log(`stt-test listening on ${PORT}`));
