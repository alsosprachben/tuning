# THE PHONE LAYOUT'S SHOTS (NUI_LAYOUT=phone, a 16 Pro Max's 3x pixels and safe area): each card with
# the patch that fills it, its other pages; at the top, or (1) scrolled to its foot.
# usage: nui_phone_shots.py SCRATCH OUT 0|1 [shot,shot...]  (SCRATCH holds wt_panel/nvlive)
import os, subprocess, sys
sys.path.insert(0, os.path.join(sys.argv[1], 'wt_panel', 'examples'))
import nui_tour as T
S, out, foot = sys.argv[1], sys.argv[2], sys.argv[3] == '1'
only = sys.argv[4].split(',') if len(sys.argv) > 4 else None
os.makedirs(out, exist_ok=True)
nvx = os.path.expanduser('~/nvx/live.nvx')
ps = T.picks(nvx)
sess = os.path.join(out, 'session.json'); open(sess, 'w').write('{}\n')
cw = (804 - 32) / 5
CARDS = ['parts', 'scenes', 'library', 'synth', 'stops', 'piano', 'drums', 'amp', 'effects', 'matrix', 'tuning', 'control', 'files', 'setup']
def card(c): i = CARDS.index(c); return 'tap %.0f %.0f' % (14 + (i % 5) * (cw + 8) + cw / 2, 114 + (i // 5) * 64 + 28)
P2, P3 = [(580, 134), (740, 134)], [(495, 134), (625, 134), (755, 134)]
STATES = [  # (shot, patch, card, taps after opening)
    ('synth_lead', dict(program=84, variation=0), 'synth', []), ('synth_lead_p2', dict(program=84, variation=0), 'synth', [(720, 134)]),
    ('synth_bass', dict(program=38, variation=0), 'synth', []),
    ('stops_drawbar', dict(program=16, variation=0), 'stops', []), ('stops_church', dict(program=19, variation=0), 'stops', []),
    ('stops_harmonium', dict(program=20, variation=0), 'stops', []),
    ('amp_drawbar', dict(program=16, variation=0), 'amp', []), ('amp_guitar', dict(program=27, variation=0), 'amp', []),
    ('piano_piano', dict(program=0, variation=0), 'piano', []), ('drums_kit', dict(program=0, drums=True), 'drums', []),
    ('effects_p2', dict(program=0, variation=0), 'effects', [P3[1]]), ('effects_p3', dict(program=0, variation=0), 'effects', [P3[2]]),
    ('control_p2', dict(program=0, variation=0), 'control', [P3[1]]), ('control_p3', dict(program=0, variation=0), 'control', [P3[2]]),
    ('tuning', dict(program=0, variation=0), 'tuning', [P2[0]]), ('tuning_p2', dict(program=0, variation=0), 'tuning', [P2[1]]),
    ('files_p2', dict(program=0, variation=0), 'files', [P2[1]]), ('setup_p2', dict(program=0, variation=0), 'setup', [P2[1]]),
    ('scenes', dict(program=0, variation=0), 'scenes', []), ('matrix', dict(program=0, variation=0), 'matrix', []),
]
steps, shots = ['wait 3000'], []
for name, want, c, taps in STATES:
    if only and name not in only:
        continue
    n = name + ('_foot' if foot else '')
    shots.append(n)
    steps += ['call {"call":"part_pick","row":0,"pick":%d}' % T.pick_for(ps, want), 'wait 600', 'tap 81 78', 'wait 300', card(c), 'wait 500']
    for t in taps:
        steps += ['tap %d %d' % t, 'wait 400']
    steps += ['wait 300', 'shot ' + os.path.join(out, n + '.ppm')]
steps += ['quit']
sc = os.path.join(out, 'script%d.txt' % foot); open(sc, 'w').write('\n'.join(steps) + '\n')
env = dict(os.environ, NUI_LAYOUT='phone', SDL_VIDEODRIVER='offscreen', NUI_SIZE='2868x1320', NUI_SAFE='186,0,2496,1257',
           NUI_SCRIPT=sc, NUI_TEXT_AUDIT=os.path.join(out, 'audit%d.txt' % foot))
if foot: env['NUI_CARD_SCROLL'] = '1'
subprocess.run([os.path.join(S, 'wt_panel', 'nvlive'), nvx, '--session=' + sess, '--app-windowed', '--midi=/dev/null',
                '--device=null'], env=env, stdout=open(os.path.join(out, 'run%d.log' % foot), 'w'), stderr=subprocess.STDOUT, timeout=1200)
from PIL import Image
for n in shots:
    p = os.path.join(out, n + '.ppm')
    if os.path.exists(p):
        Image.open(p).resize((956, 440), Image.LANCZOS).save(os.path.join(out, n + '.png')); os.remove(p)
# pairs: top over foot, two across
