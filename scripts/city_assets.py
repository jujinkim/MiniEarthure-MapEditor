"""Original MIT static streetscape library, authored in actual metres.

Batch faces by material, sharing each GLB across instances. Collision describes
solid masses; windows and signs are surface details, never extra physics bodies.
"""
from collections import defaultdict
from driving_school_map import box, glb, cm, oriented_faces

BRICK = [(0.64,0.37,0.27,1),(0.81,0.74,0.62,1),(0.48,0.54,0.59,1),(0.86,0.83,0.75,1)]
GLASS = [(0.25,0.42,0.52,1),(0.35,0.52,0.62,1),(0.49,0.63,0.69,1)]
DARK=(0.15,0.19,0.22,1)
WHITE=(0.86,0.87,0.83,1)
GREEN=(0.30,0.46,0.23,1)
TREE_CANOPY_WIDTH_M = 1.15

class Model:
    def __init__(self): self.groups=defaultdict(lambda:[[],[]]); self.collision=[]
    def faces(self, vertices, faces, color):
        vs,fs=self.groups[tuple(color)]; offset=len(vs)
        vs.extend(vertices);fs.extend(tuple(i+offset for i in face) for face in faces)
    def solid(self, center, size, color, physical=False):
        vertices=box(center,size)
        self.faces(vertices,oriented_faces(vertices),color)
        if physical: self.collision.append(dict(center=cm(center),size_cm=cm(size)))
    def panel(self, vertices, normal, color):
        a,b,c=vertices[:3];u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        faces=[(0,1,2),(0,2,3)] if sum(n[i]*normal[i] for i in range(3))>0 else [(0,2,1),(0,3,2)]
        self.faces(vertices,faces,color)
    def facade(self,cx,cy,width,depth,bottom,height,tone,spacing=1.0):
        for side in range(4):
            span=width if side<2 else depth
            columns=max(2,int(span/spacing));floors=max(1,int(height/0.85))
            for row in range(floors):
                h1=bottom+row*height/floors+0.19; h2=bottom+(row+1)*height/floors-0.13
                for col in range(columns):
                    u1=-span/2+col*span/columns+0.15;u2=-span/2+(col+1)*span/columns-0.15
                    color=GLASS[(row+col+tone)%len(GLASS)]
                    if side<2:
                        y=cy+(-1 if side==0 else 1)*(depth/2+0.009)
                        self.panel([(cx+u1,h1,y),(cx+u2,h1,y),(cx+u2,h2,y),(cx+u1,h2,y)],(0,0,-1 if side==0 else 1),color)
                    else:
                        x=cx+(-1 if side==2 else 1)*(width/2+0.009)
                        self.panel([(x,h1,cy+u1),(x,h1,cy+u2),(x,h2,cy+u2),(x,h2,cy+u1)],(-1 if side==2 else 1,0,0),color)
    def publish(self,t,name):
        path='assets/'+name+'.glb'
        t.payloads[path]=glb([(vs,color,fs) for color,(vs,fs) in self.groups.items()], indexed=True)
        t.doc['assets'].append(dict(id=name,path=path,attribution=t.doc['attributions'][0],collision=self.collision))

def building(t,index,tower=False,compact=False):
    name=('sky-building-' if tower else 'korea-building-')+str(index)+('-compact' if compact else '')
    m=Model(); w=14 if tower else (10.5 if compact else 11)
    height=(7.5+index%5*2) if tower else (2.5+index%4)
    if tower:
        m.solid((0,1,0),(w,2,w),BRICK[index%4],True)
        m.facade(0,0,w,w,0,2,index,1.5)
        styles=[(10,10,0,0),(8,13,-1,0),(12,8,0,1),(9,9,0,0),(7,12,-2,0),(12,7,0,-2)]
        tw,td,tx,ty=styles[index%6]
        m.solid((tx,(height+2)/2,ty),(tw,height-2,td),GLASS[index%3],True)
        m.facade(tx,ty,tw,td,2,height-2,index,0.9)
        if index%3==0:
            m.solid((tx,height+0.6,ty),(tw*0.65,1.2,td*0.65),WHITE,True)
        m.solid((tx,height+0.1,ty),(tw+0.08,0.18,td+0.08),WHITE)
    else:
        # Apartments with balconies, civic blocks,
        # shop offices and stepped residential roofs use different solid masses.
        m.solid((0,height/2,0),(w,height,w),BRICK[index%4],True)
        m.facade(0,0,w,w,0,height,index,1.4 if index%3 else 1.8)
        if index%3==0:
            for floor in range(1,int(height)):
                m.solid((0,floor,-w/2-0.12),(w,0.1,0.22),WHITE)
        if index%3==1:
            m.solid((0,height+0.25,0),(6,0.5,7),BRICK[(index+1)%4],True)
        if index%3==2:
            m.solid((0,height+0.05,0),(w+0.1,0.1,w+0.1),DARK)
    # Street doors, shop sign panels and rooftop services are all original geometry.
    m.solid((0,0.65,-w/2-0.012),(1.15,1.3,0.018),DARK)
    sign=[(0.74,0.19,0.15,1),(0.18,0.39,0.53,1),(0.20,0.43,0.30,1)][index%3]
    m.solid((0,1.65,-w/2-0.08),(w*0.65,0.36,0.15),sign)
    for i in range(5): m.solid((-1.8+i*0.85,1.65,-w/2-0.163),(0.37,0.16,0.01),WHITE)
    m.solid((w/3,height+0.25,w/3),(1,0.5,1.5),DARK)
    m.publish(t,name)
    return name

def tree(t):
    """One shared tree model for the practice grounds and city districts."""
    if any(a['id'] == 'city-tree' for a in t.doc['assets']):
        return 'city-tree'
    m=Model();m.solid((0,0.12,0),(0.65,0.24,0.65),(0.55,0.56,0.51,1),True)
    m.solid((0,0.25,0),(0.59,0.02,0.59),GREEN)
    m.solid((0,1.15,0),(0.16,1.8,0.16),(0.38,0.28,0.18,1),True)
    for h,w in [(2.0,TREE_CANOPY_WIDTH_M),(2.5,0.95),(2.9,0.6)]: m.solid((0,h,0),(w,0.7,w),GREEN)
    m.publish(t,'city-tree')
    return 'city-tree'

def props(t):
    tree(t)
    m=Model();m.solid((0,0.4,0),(1.3,0.12,0.44),(0.58,0.37,0.20,1),True)
    m.solid((0,0.64,0.18),(1.3,0.45,0.08),(0.58,0.37,0.20,1),True)
    for x in [-0.5,0.5]:m.solid((x,0.2,0),(0.1,0.4,0.4),DARK,True)
    m.publish(t,'city-bench')
    m=Model()
    for x in [-1.15,1.15]:m.solid((x,1.05,0.4),(0.08,2.1,0.08),DARK,True)
    m.solid((0,2.14,0),(2.7,0.12,1.2),(0.2,0.38,0.49,1),True)
    m.solid((0,1.05,0.43),(2.3,1.7,0.03),(0.46,0.61,0.66,1),True)
    m.solid((0,0.44,0.15),(1.9,0.14,0.42),WHITE,True)
    m.solid((-0.96,1.25,-0.03),(0.30,0.55,0.035),WHITE)
    m.publish(t,'city-bus-stop')
    m=Model();m.solid((0,1.7,0),(0.09,3.4,0.09),DARK,True)
    m.solid((0,3.4,-0.4),(0.14,0.12,0.85),DARK)
    m.solid((0,3.34,-0.72),(0.28,0.04,0.45),(0.95,0.91,0.70,1))
    m.publish(t,'city-lamp')
    m=Model();m.solid((0,0.32,0),(0.16,0.64,0.16),DARK,True);m.solid((0,0.51,0),(0.17,0.06,0.17),WHITE);m.publish(t,'city-bollard')
    m=Model();m.solid((0,0.35,0),(0.35,0.7,0.35),(0.25,0.36,0.36,1),True);m.solid((0,0.62,-0.181),(0.24,0.12,0.012),DARK);m.publish(t,'city-bin')
