import numpy as np
from scipy.optimize import least_squares
B=np.array([[113,0.0],[180,-2.2],[227,0.0],[254,-3.6],[285,2.3],[320,-4.7],[360,-1.0],[404,-1.2],[453,-2.9],[509,-2.5],[571,-5.6],[641,-5.1],[719,-6.4],[807,-9.8],[906,-5.8],[1017,-2.6],[1142,-1.2],[1281,-2.4],[1438,-0.3],[1615,-2.0],[1812,0.4],[2034,0.7],[2283,5.2],[2563,0.1],[2877,4.3],[3229,4.4],[3624,2.7],[4068,6.5],[4567,4.8],[5126,5.0],[5753,3.7],[6458,4.4],[7249,12.7]])
f,d=B[:,0],B[:,1]
def gain(f,corner,order,pdb,phz,pw):
    g=1/(1+(f/corner)**order)
    g=g*(1+(10**(pdb/20)-1)*np.exp(-(np.log(f/phz))**2/(2*pw**2)))
    return 20*np.log10(g)
cur=gain(f,2192.2,1.6,-5.4268,1403.6,2.246)
target=cur+d
def res(p): 
    g=gain(f,*p); return (g-g[0])-(target-target[0])
for x0 in ([8000,1.6,-8,800,0.5],[12000,2,-6,700,0.4],[20000,1.6,-10,900,0.7]):
    r=least_squares(res,x0,bounds=([800,0.5,-20,300,0.15],[40000,6,0,3000,1.5]))
    print("corner %.0f order %.2f dip %.1f dB at %.0f Hz width %.2f  rms %.2f"%(*r.x,np.sqrt(np.mean(r.fun**2))))
print("as it stands rms %.2f"%np.sqrt(np.mean(((cur-cur[0])-(target-target[0]))**2)))
