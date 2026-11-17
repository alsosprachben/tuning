# THE INTERFACES' COST (the native UI plan's B5): nvlive -- and the web UI's
# Chromium, its clavitone-ui profile -- CPU (% of one core) and memory (PSS),
# idle 20 s, then playing a MIDI file 20 s (silent: ALSA's null device). A
# real window opens: run it when the screen may be used.
#   ui_measure.py native|web|engine EXPORT.nvx FILE.mid SESSION.json
#   (engine: nvlive with its web server and no browser, the baseline;
#    native: the --app window, the file played by its own taps -- the
#    Files card at 1920x1080, as the test scripts)
import os, sys, time, json, subprocess, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WT = HERE
kind, NVX, MARS, SESSION = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
S = tempfile.mkdtemp(prefix='ui_measure_')
HZ = os.sysconf('SC_CLK_TCK')

def ws_call(port, q):
    """one call over the engine's UI socket (a bare WebSocket client: no module needed)"""
    import socket, base64, struct
    s = socket.create_connection(('127.0.0.1', port))
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET /ws HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Origin: http://127.0.0.1:{port}\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    buf = b''
    while b'\r\n\r\n' not in buf:
        buf += s.recv(4096)
    q = dict(q, id=1)
    d, m = json.dumps(q).encode(), os.urandom(4)
    n = len(d)
    h = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack('>H', n))
    s.sendall(h + m + bytes(b ^ m[i % 4] for i, b in enumerate(d)))
    time.sleep(0.5)
    s.close()


def procs():
    out = {}
    for p in os.listdir('/proc'):
        if not p.isdigit():
            continue
        try:
            comm = open(f'/proc/{p}/comm').read().strip()
            cmd = open(f'/proc/{p}/cmdline', 'rb').read().replace(b'\0', b' ').decode(errors='replace')
        except OSError:
            continue
        if comm == 'nvlive':
            out[int(p)] = 'nvlive'
        elif 'clavitone-ui' in cmd and ('chrom' in comm or 'chrom' in cmd):
            out[int(p)] = 'chromium'
    return out

def cpu(pid):
    try:
        f = open(f'/proc/{pid}/stat').read().rsplit(')', 1)[1].split()
        return int(f[11]) + int(f[12])
    except OSError:
        return None

def pss(pid):
    try:
        for l in open(f'/proc/{pid}/smaps_rollup'):
            if l.startswith('Pss:'):
                return int(l.split()[1])
    except OSError:
        pass
    return 0

def window(secs):
    ps = procs()
    a = {p: cpu(p) for p in ps}
    t0 = time.time()
    time.sleep(secs)
    dt = time.time() - t0
    res = {}
    for p, who in procs().items():
        b, c = a.get(p), cpu(p)
        if b is None or c is None:
            continue
        r = res.setdefault(who, {'cpu': 0.0, 'pss_mb': 0.0, 'n': 0})
        r['cpu'] += 100.0 * (c - b) / HZ / dt
        r['pss_mb'] += pss(p) / 1024
        r['n'] += 1
    return {k: {kk: round(vv, 1) for kk, vv in v.items()} for k, v in res.items()}

subprocess.run(['cp', SESSION, os.path.join(S, 'session.json')])     # (a copy: the run's changes stay out of yours)
env = dict(os.environ)
args = [os.path.join(WT, 'nvlive'), NVX, '--session=' + os.path.join(S, 'session.json'), '--rubato', '--gpu-span=2048',
        '--gpu-min=1', '--program=0', '--midi=/dev/null', '--device=null']
if kind == 'native':
    script = os.path.join(S, 'm_native.txt')
    open(script, 'w').write('wait 32000\ntap 1632 299\nwait 800\ntap 300 489\nwait 1500\ntap 1441 451\nwait 1500\ntap 78 299\nwait 30000\nquit\n')
    env['NUI_SCRIPT'] = script
    env['NUI_DIR'] = os.path.dirname(MARS)
    args.append('--app')
elif kind == 'engine':                  # (the engine alone: its web server, no browser)
    args += ['--ui', '--ui-no-browser']
else:
    args.append('--ui')
log = open(os.path.join(S, f'm_{kind}.log'), 'w')
nv = subprocess.Popen(args, env=env, stdout=log, stderr=log, cwd=WT)
time.sleep(10)
idle = window(20)
if kind in ('web', 'engine'):
    time.sleep(2)
    ws_call(8710, {'call': 'file_play', 'path': MARS, 'mode': 'auto'})   # (asked as the page asks)
    time.sleep(6)
else:
    time.sleep(8)
playing = window(20)
print(json.dumps({'kind': kind, 'idle': idle, 'playing': playing}))
if kind in ('web', 'engine'):
    nv.send_signal(2)
try:
    nv.wait(timeout=30)
except subprocess.TimeoutExpired:
    nv.send_signal(2)
    nv.wait(timeout=10)
time.sleep(2)
left = procs()
print('left running:', left)
