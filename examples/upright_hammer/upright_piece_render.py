import sys,os,numpy as np,mido
sys.path.insert(0,'.');sys.path.insert(0,'examples')
import tonelib as T, blockrender as B
from roomtail import write_wav
C=T.UprightPianoProperties
if sys.argv[2]=='new':
    C.max_partial_hz=10000.0; C.hammer_model=True
    for kv in os.environ['SETV'].split(','):
        n_,v_=kv.split(':'); setattr(C,n_,float(v_))
    if os.environ.get('VELPTS'): C.hammer_vel_power_points=eval(open(os.environ['VELPTS']).read())
    if os.environ.get('LEVELPTS'): C.hammer_level_points=eval(open(os.environ['LEVELPTS']).read())
    if os.environ.get('RING'): C.ring_db=eval(open(os.environ['RING']).read()); C.ring_tuned=False
    if os.environ.get('KTAB'): C.strike_noise_register_db=eval(open(os.environ['KTAB']).read())
    if os.environ.get('KVP'): C.strike_noise_vel_power_register=eval(open(os.environ['KVP']).read())
src=mido.MidiFile(os.environ.get('MID','/home/ben/Downloads/midi/ondine.mid'))
out=mido.MidiFile(type=1,ticks_per_beat=src.ticks_per_beat)
LIM=float(sys.argv[3])
tempo_map=mido.merge_tracks(src.tracks)
for tr in src.tracks:
    nt=mido.MidiTrack(); t=0.0; acc=0
    # cut at LIM seconds of the merged tempo map
    out.tracks.append(nt)
# simplest: write the merged track cut by elapsed seconds
merged=mido.MidiTrack(); el=0.0; tempo=500000; sounding=set()
for msg in mido.merge_tracks(src.tracks):
    el+=mido.tick2second(msg.time,src.ticks_per_beat,tempo)
    if msg.type=='set_tempo': tempo=msg.tempo
    if el>LIM:
        break
    merged.append(msg)
    if msg.type=='note_on' and msg.velocity>0: sounding.add((msg.channel,msg.note))
    elif msg.type in('note_off','note_on'): sounding.discard((msg.channel,msg.note))
for i,(ch,n) in enumerate(sorted(sounding)):
    merged.append(mido.Message('note_off',channel=ch,note=n,velocity=0,time=src.ticks_per_beat if i==0 else 0))
for ch in range(16): merged.append(mido.Message('control_change',channel=ch,control=64,value=0,time=0))
out.tracks=[merged]; p='/tmp/claude-1000/-home-ben-repos-midgrid/995da13a-46bc-415f-93c3-09ac5f2168de/scratchpad/upright_piece_cut.mid'; out.save(p)
L,R=B.render(p,os.environ.get('TUNER','hybrid440'))[:2]
x=np.stack([np.asarray(L,float),np.asarray(R,float)],1); x/=max(np.abs(x).max(),1e-9)/0.7
write_wav(sys.argv[1],x,B.SR)
