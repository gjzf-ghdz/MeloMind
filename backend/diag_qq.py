import sys, urllib.request, json, urllib.parse

print('=== QQ Music API Diagnostic ===')

# Test 1: Server reachable?
try:
    req = urllib.request.Request('https://c.y.qq.com')
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f'[OK] Server reachable, status {resp.status}')
except Exception as e:
    print(f'[FAIL] Server unreachable: {e}')

# Test 2: Search API
params = urllib.parse.urlencode({'w': '安静 学习', 'format': 'json', 'p': 1, 'n': 5, 'cr': 1})
url = f'https://c.y.qq.com/soso/fcgi-bin/client_search_cp?{params}'
try:
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    req.add_header('Referer', 'https://y.qq.com')
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        code = data.get('code', -1)
        songs = data.get('data', {}).get('song', {}).get('list', [])
        print(f'[OK] Search: code={code}, results={len(songs)}')
        if songs:
            s = songs[0]
            print(f'  -> {s.get("songname","?")} by {s.get("singer",[{}])[0].get("name","?")}')
except Exception as e:
    print(f'[FAIL] Search: {type(e).__name__}: {e}')

# Test 3: Top list API
try:
    url3 = 'https://c.y.qq.com/v8/fcg-bin/fcg_v8_toplist_cp.fcg?format=json&topid=4'
    req = urllib.request.Request(url3)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    req.add_header('Referer', 'https://y.qq.com')
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print(f'[OK] Top list: code={data.get("code",-1)}')
except Exception as e:
    print(f'[FAIL] Top list: {type(e).__name__}: {e}')

print()
print('=== Our QQMusicSource ===')
sys.path.insert(0, '.')
from qqmusic_source import QQMusicSource
qm = QQMusicSource()
songs = qm.search('安静 学习', limit=3)
if songs:
    for s in songs:
        print(f'  {s.title} - {s.artist}')
else:
    print('  No results')
