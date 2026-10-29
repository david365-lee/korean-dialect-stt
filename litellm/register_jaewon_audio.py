"""Register jaewon-stt / jaewon-tts as stable aliases over existing native audio routes.

Credentials are copied server-side from the already connected routes and never printed.
One short TTS -> STT round trip verifies both; a failing alias is left paused.
"""
import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
from prisma import Prisma
from litellm.proxy.common_utils.encrypt_decrypt_utils import decrypt_value_helper

STT, TTS = 'jaewon-stt', 'jaewon-tts'
STT_SOURCE, TTS_SOURCE = 'groq-whisper-large-v3', 'google-cloud-tts-standard'
VOICE = 'ko-KR-Standard-A'
# Whisper prompt: biases toward verbatim dialect spelling and Latin-script technical terms.
STT_PROMPT = ('야, Kubernetes Pod가 와 이래 자꾸 죽노? 로그 좀 봐도. 우째 이라노, 머라카노, 했심더, 했당께, 했슈, 했드래요, 했수다. '
              'kubectl, Deployment, CrashLoopBackOff, OOMKilled, Ingress, Helm, Argo CD, LiteLLM, Dify.')
SAMPLE = '야, Kubernetes Pod가 와 이래 자꾸 죽노? 로그 좀 봐도.'
session = requests.Session()
session.headers['Authorization'] = 'Bearer ' + os.environ['LITELLM_MASTER_KEY']
base = 'http://localhost:4000'


def call(method, path, **kwargs):
    response = session.request(method, base + path, timeout=90, **kwargs)
    if not response.ok:
        raise RuntimeError(f'{method} {path}: HTTP {response.status_code}')
    return response.json()


def digest(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()


async def stored_params(database, alias, keys):
    row = await database.litellm_proxymodeltable.find_first(where={'model_name': alias})
    values = row.litellm_params
    if isinstance(values, str):
        values = json.loads(values)
    result = {}
    for key in keys:
        if values.get(key) is None:
            continue
        value = decrypt_value_helper(value=values[key], key=key, exception_type='debug', return_original_value=True)
        assert value and not str(value).startswith('os.environ/'), f'{alias}: {key} not connected'
        result[key] = value
    return result


def set_blocked(model_id, blocked, **extra):
    call('PATCH', f'/model/{model_id}/update', json={'blocked': blocked, 'model_info': {'blocked': blocked, **extra}})


def retry(request, attempts=6):
    # The router reloads DB models on a short poll interval.
    for attempt in range(attempts):
        response = request()
        if response.ok or response.status_code not in (400, 404):
            return response
        time.sleep(5)
    return response


async def main():
    before = call('GET', '/v1/model/info')['data']
    mapping = {row['model_name']: row for row in before}
    for alias in (STT, TTS):
        if alias in mapping:
            assert mapping[alias]['model_info'].get('mdai_jaewon_audio'), 'Unmanaged alias conflict'
    directory = Path('/tmp/mdai-jaewon-audio-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    directory.mkdir(mode=0o700)
    (directory / 'before.json').write_text(json.dumps(before))
    (directory / 'before.json').chmod(0o600)

    database = Prisma()
    await database.connect()
    try:
        groq = await stored_params(database, STT_SOURCE, ['api_key', 'api_base'])
        vertex = await stored_params(database, TTS_SOURCE, ['vertex_credentials', 'vertex_project', 'vertex_location'])
    finally:
        await database.disconnect()

    common = {'blocked': True, 'mdai_jaewon_audio': True, 'mdai_inference_tested': False,
              'mdai_pipeline_doc': 'docs/DIALECT-STT-PIPELINE.md'}
    rows = {
        STT: {'litellm_params': {'model': 'groq/whisper-large-v3', **groq, 'language': 'ko', 'prompt': STT_PROMPT},
              'model_info': {**common, 'mode': 'audio_transcription', 'display_name': 'jaewon STT · 사투리/한영 혼용',
                             'mdai_backend': STT_SOURCE, 'mdai_provider': 'Groq',
                             'mdai_registration_note': 'Stable alias. Baseline backend is Groq Whisper Large V3 with a '
                                                       'dialect/tech-term prompt; replace with the fine-tuned external Whisper endpoint later.'}},
        TTS: {'litellm_params': {'model': 'vertex_ai/chirp', **vertex, 'voice': VOICE},
              'model_info': {**common, 'mode': 'audio_speech', 'display_name': 'jaewon TTS · 한국어',
                             'health_check_voice': VOICE, 'health_check_params': {'voice': VOICE},
                             'mdai_backend': TTS_SOURCE, 'mdai_provider': 'Google Cloud Text-to-Speech',
                             'mdai_default_voice': VOICE,
                             'mdai_registration_note': 'Stable alias over Cloud TTS Standard. Used for code-switching augmentation '
                                                       'text; synthetic audio must never enter evaluation sets.'}},
    }
    for alias, row in rows.items():
        if alias not in mapping:
            call('POST', '/model/new', json={'model_name': alias, 'blocked': True, **row})
    ids = {row['model_name']: row['model_info']['id'] for row in call('GET', '/v1/model/info')['data']
           if row['model_name'] in rows}

    result = {}
    set_blocked(ids[TTS], False)
    speech = retry(lambda: session.post(base + '/v1/audio/speech', timeout=90,
                                        json={'model': TTS, 'input': SAMPLE, 'voice': VOICE, 'response_format': 'mp3'}))
    tts_ok = speech.ok and len(speech.content) > 1000
    result[TTS] = {'status': speech.status_code, 'audio_bytes': len(speech.content) if tts_ok else 0, 'enabled': tts_ok}
    if tts_ok:
        set_blocked(ids[TTS], False, mdai_inference_tested=True)
        set_blocked(ids[STT], False)
        text = retry(lambda: session.post(base + '/v1/audio/transcriptions', timeout=90, data={'model': STT},
                                          files={'file': ('sample.mp3', speech.content, 'audio/mpeg')}))
        transcript = text.json().get('text', '') if text.ok else ''
        stt_ok = bool(transcript.strip())
        result[STT] = {'status': text.status_code, 'transcript': transcript, 'enabled': stt_ok}
        if stt_ok:
            set_blocked(ids[STT], False, mdai_inference_tested=True)
        else:
            set_blocked(ids[STT], True)
    else:
        set_blocked(ids[TTS], True)
        result[STT] = {'enabled': False, 'reason': 'no_tts_sample'}

    after = call('GET', '/v1/model/info')['data']
    after_map = {row['model_name']: row for row in after}
    preserved = [row for row in before if row['model_name'] not in rows]
    assert all(digest(row) == digest(after_map[row['model_name']]) for row in preserved), 'Existing model changed'
    summary = {'sample': SAMPLE, 'results': result, 'existing_models_unchanged': len(preserved),
               'before': len(before), 'after': len(after), 'backup': str(directory)}
    (directory / 'result.json').write_text(json.dumps(summary, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as error:
        # Avoid echoing exception text: it may contain decrypted credentials.
        print(json.dumps({'failed': type(error).__name__}), flush=True)
        raise SystemExit(1)
