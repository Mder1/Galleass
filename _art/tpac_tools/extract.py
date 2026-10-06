import tpac, pickle, struct, io, numpy as np
from PIL import Image
found=pickle.load(open('found.pkl','rb'))
FCC={'DXT1':b'DXT1','DXT3':b'DXT3','DXT5':b'DXT5','BC5':b'ATI2','BC4':b'ATI1'}
def dds(w,h,fmt,data):
    return struct.pack('<4sIIIIIII44xII4s20xI16x', b'DDS ',124,0x1007|0x80000,h,w,len(data),0,1,32,4,FCC[fmt],0x1000)+data
for n,ms in sorted(found.items()):
    m=ms[0]; data=tpac.pixels(m); chain=tpac.mip_chain(m,data)
    cap=4096 if m['w']>=8192 else 2048
    w,h,d=next(c for c in chain if c[0]<=cap)
    im=Image.open(io.BytesIO(dds(w,h,m['fmt'],d))); im.load()
    a=np.asarray(im.convert('RGBA')).astype(np.float32)
    stats=' '.join('%s[%.0f..%.0f m%.0f]'%(c,a[...,i].min(),a[...,i].max(),a[...,i].mean()) for i,c in enumerate('RGBA'))
    print(n,m['fmt'],im.mode,w,h,stats)
    np.save(n+'.npy',a.astype(np.uint8))
