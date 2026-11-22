import sys,os,numpy as np
sys.path.insert(0,'.');sys.path.insert(0,'examples')
os.environ.setdefault("TUNING_REFLECT","0")
import tonelib as T, blockrender as B, mido
C=T.ElectricGrandProperties
for kv in os.environ['SETV'].split(','):
    n_,v_=kv.split(':'); setattr(C,n_,eval(v_))
exec(open('../parity_piece.py').read().split("src=mido.MidiFile")[0].split("import blockrender as B")[1] if False else "")
sys.argv=['x','../nocturne_upright.mid',sys.argv[1],'2','12']
exec(open('../parity_piece.py').read().replace("import blockrender as B",""))
