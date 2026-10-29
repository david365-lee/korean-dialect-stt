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
// One LLM call interprets both transcripts of the same recording and judges whether they agree.
const PROMPT = `같은 녹음을 두 STT가 받아쓴 결과 A와 B가 주어진다. 사투리와 영어 기술 용어가 섞여 있고 인식 오류가 있을 수 있다.
각 문장을 받아쓴 그대로 읽고 해석한다(다른 쪽 문장으로 보정하지 않는다).
- meaning: 말한 사람이 원하는 것을 아주 간략히 한 문장(30자 이내)
- standard: 표준어 문장. 영어 기술 용어는 영어 표기로, 한글로 잘못 받아쓴 용어(예: 키버넷 → Kubernetes)는 바로잡는다
- intent: {"action", "target", "symptom"} (짧은 한국어)
마지막으로 A와 B의 해석이 같은 의미인지(same_meaning)와 다르면 핵심 차이(difference, 20자 이내)를 적는다.
JSON만 출력한다: {"A": {"meaning": "", "standard": "", "intent": {}}, "B": {"meaning": "", "standard": "", "intent": {}}, "same_meaning": true, "difference": ""}`;
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

async function interpret(tuned, plain) {
  const result = await call('/chat/completions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: LLM, temperature: 0, max_tokens: 600, messages: [
      { role: 'system', content: PROMPT },
      { role: 'user', content: `A: ${tuned || '(인식된 말 없음)'}\nB: ${plain || '(인식된 말 없음)'}` }] }),
  });
  if (!result.data) return { error: result.error, ms: result.ms };
  const content = result.data.choices?.[0]?.message?.content || '';
  try {
    const parsed = JSON.parse((content.match(/\{[\s\S]*\}/) || ['{}'])[0]);
    const pick = (x) => ({ meaning: String(x?.meaning || ''), standard: String(x?.standard || ''), intent: x?.intent || null });
    return { tuned: pick(parsed.A), plain: pick(parsed.B), same_meaning: parsed.same_meaning === true,
      difference: String(parsed.difference || ''), ms: result.ms };
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
    let interpretation = null;
    if (url.searchParams.get('interpret') === '1' && results.some((r) => r.text)) {
      interpretation = await interpret(results[0].text, results[1].text);
    }
    send(res, 200, { bytes: audio.length, llm_model: LLM, results, interpretation });
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
