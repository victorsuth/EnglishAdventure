#!/usr/bin/env python3
"""Generate the spoken audio for English Adventure with MiniMax TTS.

Reads every word / phrase / letter from the CATS block in index.html,
generates audio/<key>.mp3 for anything missing, then writes the list of
available clips back into index.html (between /*CLIPS*/ and /*END*/).

Usage:
    MINIMAX_API_KEY=... python3 tools/gen_audio.py          # generate missing clips
    python3 tools/gen_audio.py --list                       # just print the texts
    python3 tools/gen_audio.py --redo "A." "apple"          # regenerate some clips

Run it again whenever words are added to index.html.
"""
import json, os, re, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'index.html')
AUDIO = os.path.join(ROOT, 'audio')

VOICE = 'English_Kind-heartedGirl'   # 温柔女孩，家长和老师试听后选定
MODEL = 'speech-2.6-hd'
SPEED = 0.9
API = 'https://api.minimax.cn/v1/t2a_v2'

# Fixed lines the app says besides the word list (keep in sync with index.html).
EXTRA = ['Great!', 'Well done!', 'Super!', 'Excellent!', 'Good job!', 'Perfect!',
         'Hello! Nice to meet you.', 'Great job! See you tomorrow!']


def slug(t):
    """Must match slug() in index.html."""
    return re.sub(r'^-+|-+$', '', re.sub(r'[^a-z0-9]+', '-', t.lower()))


def texts_from_html():
    s = open(HTML, encoding='utf-8').read()
    block = s[s.index('const CATS = {'):s.index('const ORDER=')]
    out = []
    for m in re.finditer(r"\n  (\w+):\{name:(.*?)\]\]\}", block, re.S):
        cat, body = m.group(1), m.group(2)
        body = body[body.index('items:'):]
        items = re.findall(r"\['((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)','", body)
        for a, b in items:
            a, b = a.replace("\\'", "'"), b.replace("\\'", "'")
            if cat == 'letters':
                out += [f'{a}.', f'{a} is for {b}.', b]
            else:
                out.append(a)
    out += EXTRA
    seen, res = set(), []
    for t in out:
        if slug(t) not in seen:
            seen.add(slug(t)); res.append(t)
    return res


def tts(text):
    body = {"model": MODEL, "text": text, "stream": False, "language_boost": "English",
            "voice_setting": {"voice_id": VOICE, "speed": SPEED, "vol": 1, "pitch": 0},
            "audio_setting": {"sample_rate": 32000, "bitrate": 64000, "format": "mp3", "channel": 1}}
    key = os.environ.get('MINIMAX_API_KEY', 'dummy')  # in Claude's cloud env the proxy injects the key
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    for attempt in range(8):
        d = json.load(urllib.request.urlopen(req, timeout=90))
        br = d.get('base_resp', {})
        if br.get('status_code') == 0:
            return bytes.fromhex(d['data']['audio'])
        if br.get('status_code') == 1002:   # rate limit (about 20 requests / minute)
            time.sleep(15); continue
        raise RuntimeError(f'{text!r}: {br}')
    raise RuntimeError(f'{text!r}: still rate limited')


def write_manifest():
    keys = sorted(f[:-4] for f in os.listdir(AUDIO) if f.endswith('.mp3'))
    s = open(HTML, encoding='utf-8').read()
    s2 = re.sub(r'/\*CLIPS\*/".*?"/\*END\*/', '/*CLIPS*/"' + ','.join(keys) + '"/*END*/', s, flags=re.S)
    if s2 == s and '/*CLIPS*/' not in s:
        raise SystemExit('index.html has no /*CLIPS*/ marker')
    open(HTML, 'w', encoding='utf-8').write(s2)
    print(f'manifest: {len(keys)} clips')


def main():
    texts = texts_from_html()
    if '--list' in sys.argv:
        for t in texts: print(slug(t), '|', t)
        print(len(texts), 'texts'); return
    redo = set(slug(t) for t in sys.argv[sys.argv.index('--redo') + 1:]) if '--redo' in sys.argv else set()
    os.makedirs(AUDIO, exist_ok=True)
    todo = [t for t in texts if slug(t) in redo or not os.path.exists(os.path.join(AUDIO, slug(t) + '.mp3'))]
    print(f'{len(texts)} texts, {len(todo)} to generate')
    for i, t in enumerate(todo, 1):
        audio = tts(t)
        open(os.path.join(AUDIO, slug(t) + '.mp3'), 'wb').write(audio)
        print(f'[{i}/{len(todo)}] {slug(t)} {len(audio)}B', flush=True)
        time.sleep(3.2)
    write_manifest()


if __name__ == '__main__':
    main()
