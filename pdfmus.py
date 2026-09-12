#!/usr/bin/env python3
"""Read a PDF content stream: text glyphs with exact coordinates, and paths.

Engraving programs (Sibelius, Finale) emit music as font glyphs at exact
positions, not as a raster.  So a PDF score is symbolic data wearing a
picture's clothes: noteheads, accidentals, clefs and rests are characters with
coordinates, staff lines and stems are stroked paths, slurs are beziers.  That
makes a score readable by arithmetic rather than by recognition -- and, unlike
OMR, wrong answers show up as systematic offsets rather than plausible noise.

This module is the generic half: it interprets the content stream and hands
back glyphs and line segments.  scorepdf.py is the music half.
"""

import re, zlib, collections

TOK = re.compile(rb'''
    (?P<num>-?\d*\.?\d+)
  | /(?P<name>[A-Za-z0-9+.\-]+)
  | \((?P<str>(?:\\.|[^)\\])*)\)
  | (?P<arr>\[)|(?P<arre>\])
  | (?P<op>[A-Za-z'"*]+)
''', re.X | re.S)

def unescape(b):
    out=bytearray(); i=0
    while i<len(b):
        c=b[i]
        if c==0x5c and i+1<len(b):
            n=b[i+1]
            m={ord('n'):10,ord('r'):13,ord('t'):9,ord('b'):8,ord('f'):12,
               ord('('):40,ord(')'):41,ord('\\'):92}
            if n in m: out.append(m[n]); i+=2; continue
            if 0x30<=n<=0x37:
                j=i+1; o=''
                while j<len(b) and len(o)<3 and 0x30<=b[j]<=0x37: o+=chr(b[j]); j+=1
                out.append(int(o,8)&0xFF); i=j; continue
            out.append(n); i+=2; continue
        out.append(c); i+=1
    return bytes(out)

def mul(a,b):
    return [a[0]*b[0]+a[1]*b[2], a[0]*b[1]+a[1]*b[3],
            a[2]*b[0]+a[3]*b[2], a[2]*b[1]+a[3]*b[3],
            a[4]*b[0]+a[5]*b[2]+b[4], a[4]*b[1]+a[5]*b[3]+b[5]]

def run(content):
    """-> list of (font, size, x, y, code); also returns drawn line segments."""
    glyphs=[]; lines=[]
    ctm=[1,0,0,1,0,0]; stack=[]
    tm=tlm=[1,0,0,1,0,0]
    font=None; fsize=0; tl=0
    operands=[]; path=[]
    for m in TOK.finditer(content):
        if m.group('num') is not None: operands.append(float(m.group('num'))); continue
        if m.group('name') is not None: operands.append(m.group('name').decode('latin1')); continue
        if m.group('str') is not None: operands.append(unescape(m.group('str'))); continue
        if m.group('arr'): operands.append('['); continue
        if m.group('arre'): operands.append(']'); continue
        op=m.group('op').decode('latin1')
        try:
            if op=='q': stack.append(list(ctm))
            elif op=='Q': ctm=stack.pop() if stack else ctm
            elif op=='cm' and len(operands)>=6: ctm=mul(operands[-6:],ctm)
            elif op=='BT': tm=tlm=[1,0,0,1,0,0]
            elif op=='Tf' and len(operands)>=2: font=operands[-2]; fsize=operands[-1]
            elif op=='TL' and operands: tl=operands[-1]
            elif op=='Tm' and len(operands)>=6: tm=tlm=list(operands[-6:])
            elif op=='Td' and len(operands)>=2: tlm=mul([1,0,0,1,operands[-2],operands[-1]],tlm); tm=list(tlm)
            elif op=='TD' and len(operands)>=2:
                tl=-operands[-1]; tlm=mul([1,0,0,1,operands[-2],operands[-1]],tlm); tm=list(tlm)
            elif op=='T*': tlm=mul([1,0,0,1,0,-tl],tlm); tm=list(tlm)
            elif op in ('Tj','TJ',"'",'"'):
                if op=="'": tlm=mul([1,0,0,1,0,-tl],tlm); tm=list(tlm)
                items=[]
                if op=='TJ':
                    j=len(operands)-1
                    while j>=0 and operands[j]!='[': j-=1
                    items=operands[j+1:]
                else:
                    items=[operands[-1]] if operands and isinstance(operands[-1],bytes) else []
                for it in items:
                    if isinstance(it,float):
                        tm=mul([1,0,0,1,-it/1000.0*fsize,0],tm); continue
                    for ch in it:
                        trm=mul(mul([fsize,0,0,fsize,0,0],tm),ctm)
                        glyphs.append((font,fsize,trm[4],trm[5],ch))
                        tm=mul([1,0,0,1,fsize*0.55,0],tm)   # nominal advance
            elif op=='m' and len(operands)>=2: path=[(operands[-2],operands[-1])]
            elif op=='l' and len(operands)>=2: path.append((operands[-2],operands[-1]))
            elif op=='c' and len(operands)>=6:
                for t in (0.25,0.5,0.75,1.0):
                    if not path: break
                    p0=path[0] if len(path)==1 else path[-1]
                path.extend([(operands[0],operands[1]),(operands[2],operands[3]),(operands[4],operands[5])])
            elif op in ('v','y') and len(operands)>=4:
                path.extend([(operands[0],operands[1]),(operands[2],operands[3])])
            elif op in ('S','s','f','F') and len(path)>=2:
                for a,b in zip(path,path[1:]):
                    ax=a[0]*ctm[0]+a[1]*ctm[2]+ctm[4]; ay=a[0]*ctm[1]+a[1]*ctm[3]+ctm[5]
                    bx=b[0]*ctm[0]+b[1]*ctm[2]+ctm[4]; by=b[0]*ctm[1]+b[1]*ctm[3]+ctm[5]
                    lines.append((ax,ay,bx,by))
                path=[]
        finally:
            if op not in (None,): operands=[]
    return glyphs, lines

def pages(path):
    d=open(path,'rb').read()
    out=[]
    for m in re.finditer(rb'stream\r?\n', d):
        s=m.end(); e=d.find(b'endstream', s)
        try: c=zlib.decompress(d[s:e])
        except Exception: continue
        if b'Tm' in c and b'Tf' in c: out.append(c)
    return out

if __name__=='__main__':
    import sys
    P=pages('score.pdf')
    print("pages:",len(P))
    g,l=run(P[0])
    mus=[x for x in g if x[0]=='R20']
    print("page1: %d glyphs (%d music), %d line segs"%(len(g),len(mus),len(l)))
    c=collections.Counter(x[4] for x in mus)
    print("music codes:", c.most_common(10))
    ys=sorted(set(round(x[3],1) for x in mus))
    print("distinct music y: %d  range %.0f..%.0f"%(len(ys),ys[0],ys[-1]))
