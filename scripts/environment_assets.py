"""Original metre-scale MIT modules. Source geometry is retained in this file.

Material batching shares geometry and colors; no texture copies or baked lights.
Every load-bearing/roadside solid has an explicit collision proxy.
"""
from city_assets import Model
from driving_school_map import box, cm, glb, oriented_faces
import math


def beam(model, start, end, width, depth, color, physical=False):
    """A continuous rectangular member in a vertical plane, with matching proxy."""
    dx,dy=end[0]-start[0],end[1]-start[1]
    length=math.hypot(dx,dy)
    nx,ny=-dy/length*width/2,dx/length*width/2
    vertices=[(p[0]+s*nx,p[1]+s*ny,p[2]+z*depth/2)
              for p,s in ((start,-1),(end,-1),(end,1),(start,1)) for z in (-1,1)]
    # Restore the ordinary box vertex ordering before calculating outward faces.
    vertices=[vertices[i] for i in (0,2,3,1,6,4,5,7)]
    model.faces(vertices,oriented_faces(vertices),color)
    if physical:
        if not hasattr(model,'convex_collision'): model.convex_collision=[]
        model.convex_collision.append(dict(vertices=[cm(p) for p in vertices],faces=oriented_faces(vertices)))


def crown(model, center, size, color):
    """Rounded, faceted foliage with a broad silhouette, not a flat umbrella."""
    n=10;rings=5;vertices=[(center[0],center[1]-size[1]/2,center[2])]
    for row in range(1,rings):
        latitude=-math.pi/2+math.pi*row/rings
        for i in range(n):
            angle=math.tau*i/n
            vertices.append((center[0]+size[0]/2*math.cos(latitude)*math.cos(angle),
                center[1]+size[1]/2*math.sin(latitude),center[2]+size[2]/2*math.cos(latitude)*math.sin(angle)))
    vertices.append((center[0],center[1]+size[1]/2,center[2]));faces=[]
    for i in range(n):
        faces.append((0,1+(i+1)%n,1+i))
        for row in range(rings-2):
            a=1+row*n+i;b=1+row*n+(i+1)%n;c=b+n;d=a+n
            faces.extend(((a,b,c),(a,c,d)))
        faces.append((len(vertices)-1,1+(rings-2)*n+i,1+(rings-2)*n+(i+1)%n))
    outward=[]
    for a,b,c in faces:
        u=[vertices[b][i]-vertices[a][i] for i in range(3)];v=[vertices[c][i]-vertices[a][i] for i in range(3)]
        normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        outward.append((a,b,c) if sum(normal[i]*(vertices[a][i]-center[i]) for i in range(3))>0 else (a,c,b))
    model.faces(vertices,outward,color)


def wheel():
    m=Model();steel=(.25,.34,.37,1);rim=(.84,.77,.57,1);white=(.87,.88,.79,1)
    m.solid((0,.2,0),(38,.4,16),(.55,.57,.54,1),True)
    for z in (-3.5,3.5):
        for x in (-7,7):
            m.solid((x,.6,z),(2,1.2,2),(.61,.63,.60,1),True)
            beam(m,(x,.8,z),(0,18,z),.65,.7,steel,True)
        for i in range(24):
            a,b=math.tau*i/24,math.tau*(i+1)/24
            first=(15*math.cos(a),18+15*math.sin(a),z)
            second=(15*math.cos(b),18+15*math.sin(b),z)
            beam(m,first,second,.36,.36,rim)
            if z<0:
                beam(m,(first[0],first[1],0),(second[0],second[1],0),.36,7.4,rim,True)
            if i%2==0: beam(m,(0,18,z),first,.16,.16,white)
    m.solid((0,18,0),(1.7,1.7,8),steel,True)
    for i in range(12):
        angle=math.tau*i/12;x,y=15*math.cos(angle),18+15*math.sin(angle)
        color=[(.76,.30,.23,1),(.22,.52,.60,1),(.85,.66,.23,1)][i%3]
        m.solid((x,y-1.2,0),(2.4,1.2,3),color,True)
        m.solid((x,y-.1,0),(2.5,.18,3.1),rim,True)
        for side in (-1,1):
            for z in (-1.35,1.35): m.solid((x+side*1.05,y-.6,z),(.13,1.1,.13),steel)
    return m


def broadleaf(birch=False):
    m=Model();bark=(.76,.77,.66,1) if birch else (.34,.26,.17,1)
    m.solid((0,3.6,0),(.38 if birch else .65,7.2,.45 if birch else .7),bark,True)
    crowns=[(-2.1,8,-.7,5.3,6.0),(2.1,8.6,.4,5.1,6.4),(0,10.1,0,6,6.2),(0,7,2,5,5)]
    for i,(x,y,z,w,h) in enumerate(crowns):
        beam(m,(0,4,0),(x,y-.7,0),.15,.18,bark)
        color=(.32+i*.025,.48+i*.02,.19+i*.014,1) if birch else (.18+i*.02,.35+i*.025,.16+i*.018,1)
        crown(m,(x,y,z),(w*.85 if birch else w,h,w*.85),color)
    return m


def strata(butte=False):
    m=Model();m.convex_collision=[]
    for i in range(5):
        bottom=i*(3.2 if butte else 2.2)-.6;top=bottom+(3.2 if butte else 2.2)
        width=(21 if butte else 27)-i*1.8;depth=(16 if butte else 9)-i*.7
        vertices=box((0,(bottom+top)/2,0),(width,top-bottom,depth))
        # Each layer is a complete convex slab; slight taper and stagger expose strata.
        vertices=[(x+(.35 if i%2 else -.35)+(0.4 if j>=4 else 0),y,z) for j,(x,y,z) in enumerate(vertices)]
        color=[(.59,.27,.13,1),(.71,.35,.18,1),(.82,.47,.26,1),(.62,.29,.15,1),(.77,.41,.20,1)][i]
        m.faces(vertices,oriented_faces(vertices),color)
        m.convex_collision.append(dict(vertices=[cm(p) for p in vertices],faces=oriented_faces(vertices)))
    return m


def roof(m, width, depth, height, rise, color, hip=False):
    vertices=[(-width/2,height,-depth/2),(width/2,height,-depth/2),
              (width/2,height,depth/2),(-width/2,height,depth/2),
              (0,height+rise,-depth/2+(depth*.24 if hip else 0)),
              (0,height+rise,depth/2-(depth*.24 if hip else 0))]
    faces=[(0,2,1),(0,3,2),(0,1,4),(3,5,2),(0,4,5),(0,5,3),(1,2,5),(1,5,4)]
    faces=[(a,c,b) for a,b,c in faces]
    m.faces(vertices,faces,color)
    if not hasattr(m,'convex_collision'): m.convex_collision=[]
    m.convex_collision.append(dict(vertices=[cm(p) for p in vertices],faces=faces))


def building(kind, variant):
    """Three architectural silhouettes, with shared facade/roof/porch parts.

    Local -Z is the front. Dimensions include porches/canopies so placement and
    access planning reserve the complete assembly, not just its main mass.
    """
    m=Model();wall=[(.80,.70,.53,1),(.71,.79,.80,1),(.68,.47,.36,1)][variant]
    dark=(.22,.27,.28,1);trim=(.88,.87,.78,1);glass=(.28,.46,.55,1)
    if kind=='hall':
        w,d,h=[(28,32,10),(34,28,12),(32,36,14)][variant]
        m.solid((0,h/2,0),(w,h,d),wall,True)
        if variant==0: roof(m,w+1,d+1,h,3,dark)
        elif variant==1: roof(m,w+1,d+1,h,2,trim,True)
        else:
            # A connected production annex changes the upper silhouette.
            m.solid((-w*.18,h+2,0),(w*.48,4,d*.82),trim,True)
            roof(m,w+1,d+1,h,1,dark)
        for x in (-w*.28,0,w*.28):
            m.solid((x,2,-d/2-.03),(5,4,.08),dark)
            m.solid((x,.45,-d/2-1.8),(6,.9,3.6),trim,True)
        m.solid((0,5.3,-d/2-2.4),(w,.35,5),dark,True)
        for x in (-w/2+.5,w/2-.5): m.solid((x,2.65,-d/2-4.5),(.4,5.3,.4),dark,True)
        for z in (-d*.3,0,d*.3): m.solid((w/2+.04,h*.7,z),(.08,2,4),glass)
        return m
    w,d,h = ([(16,14,5),(18,13,8),(14,18,6)][variant] if kind=='home' else
             [(20,16,6),(18,19,10),(24,15,8)][variant] if kind=='market' else
             [(18,16,6),(14,18,9),(22,15,7)][variant])
    m.solid((0,h/2,0),(w,h,d),wall,True)
    if variant<2 or kind=='lodge': roof(m,w+1,d+1,h,3+variant*.6,trim if kind=='lodge' else dark,variant==1)
    else:
        m.solid((-w*.16,h+1,0),(w*.65,2,d*.7),trim,True)
        m.solid((0,h+.1,0),(w+.6,.2,d+.6),dark,True)
    for level in range(max(1,int(h/3))):
        for x in (-w*.32,0,w*.32):
            m.solid((x,2+level*3,-d/2-.04),(2,1.6,.08),glass)
        for z in (-d*.28,d*.28):
            for x in (-w/2-.04,w/2+.04): m.solid((x,2+level*3,z),(.08,1.6,2),glass)
    m.solid((0,1.2,-d/2-.06),(1.5,2.4,.10),dark)
    if kind=='market':
        m.solid((0,3.6,-d/2-1.2),(w,.25,2.6),[(.68,.21,.18,1),(.23,.46,.43,1),(.35,.39,.60,1)][variant],True)
        for x in (-w*.3,w*.3): m.solid((x,1.4,-d/2-.08),(w*.26,2.6,.1),glass)
        m.solid((0,4.4,-d/2-.10),(w*.7,.8,.15),trim)
    else:
        m.solid((0,.18,-d/2-1.2),(w*.55,.36,2.4),trim,True)
        m.solid((0,3.1,-d/2-1.2),(w*.58,.20,2.7),dark,True)
        for x in (-w*.25,w*.25): m.solid((x,1.6,-d/2-2),(.24,3.2,.24),trim,True)
    return m


def pine(young=False):
    m=Model();height=7 if young else 14
    m.solid((0,height*.32,0),(.35,height*.64,.35),(.38,.29,.20,1),True)
    for i in range(4):
        radius=(2.6 if young else 4.2)*(1-i*.18)
        center=height*(.35+i*.15)
        vertices=[(radius*math.cos(a*math.tau/8),center,radius*math.sin(a*math.tau/8)) for a in range(8)]
        vertices.append((0,center+height*.32,0))
        faces=[(a,(a+1)%8,8) for a in range(8)]+[(0,a+1,a) for a in range(1,7)]
        m.faces(vertices,faces,(.16+i*.015,.29+i*.018,.21+i*.012,1))
    return m


def boulder(variant):
    m=Model();m.convex_collision=[]
    for i in range(variant+1):
        w,d,h=(6+variant*2,4+variant,3+variant*1.5)
        vertices=box((i*2,h*.38,i*.7),(w,h,d))
        vertices=[(x*(.64 if n>=4 else 1)+(.6 if n>=4 else 0),y,z*(.72 if n>=4 else 1)) for n,(x,y,z) in enumerate(vertices)]
        faces=oriented_faces(vertices)
        m.faces(vertices,faces,(.48+variant*.05,.43+variant*.04,.35+variant*.03,1))
        m.convex_collision.append(dict(vertices=[cm(p) for p in vertices],faces=faces))
    return m


def support_module(height_cm):
    height=height_cm/100;m=Model();color=(.63,.65,.61,1)
    for x in (-2,2): m.solid((x,height/2,0),(.65,height,.65),color,True)
    m.solid((0,height-.3,0),(5,.6,.8),color,True)
    identity='environment-pier-h'+str(height_cm)
    return (dict(id=identity,path=identity+'.glb',collision=m.collision,
        attribution=dict(source='mapeditor-environment-modules',license='MIT',notice='Terrain-fitted support; original source in environment_assets.py.')),
        glb([(vs,color,fs) for color,(vs,fs) in m.groups.items()],indexed=True))


def grown(model, horizontal, vertical):
    """A retained growth variant; the original model and its proxies stay intact."""
    for vertices,_ in model.groups.values():
        vertices[:]=[(x*horizontal,y*vertical,z*horizontal) for x,y,z in vertices]
    for proxy in model.collision:
        for key in ('center','size_cm'):
            proxy[key]=[round(v*factor) for v,factor in zip(proxy[key],(horizontal,vertical,horizontal))]
    return model


def library():
    steel=(.34,.39,.40,1); concrete=(.63,.65,.61,1); wood=(.49,.33,.20,1)
    models={'wheel':wheel(),'canopy-oak':broadleaf(),'canopy-birch':broadleaf(True),
            'strata':strata(),'butte':strata(True)}
    for kind in ('home','market','hall','lodge'):
        for variant in range(3): models[kind+'-'+str(variant)]=building(kind,variant)
    for variant in range(3): models['boulder-'+str(variant)]=boulder(variant)
    models['pine']=pine();models['sapling']=pine(True)
    models['canopy-mature-oak']=grown(broadleaf(),1.65,1.25)
    models['canopy-mature-birch']=grown(broadleaf(True),1.55,1.30)
    models['pine-mature']=grown(pine(),1.45,1.25)
    m=Model()
    m.solid((0,.45,0),(7,.9,1),wood,True)
    beam(m,(-1,.5,0),(1,1.5,0),.30,.35,wood,True)
    models['fallen-log']=m
    m=Model()
    # Joined pipe rack: same endpoints on repeated modules, actual support legs.
    for x in (-5,5):
        for z in (-1.8,1.8): m.solid((x,2.5,z),(.35,5,.35),steel,True)
        m.solid((x,4.8,0),(.4,.4,4.2),steel,True)
    for z in (-1,0,1): m.solid((0,5.2,z),(12,.5,.5),(.65,.55,.32,1),True)
    models['pipe-run']=m
    m=Model()
    for x in (-3,3):
        for z in (-3,3): m.solid((x,8,z),(.6,16,.6),wood,True)
    for y in (4,8,12,16): m.solid((0,y,0),(7,.3,7),wood,True)
    roof(m,9,9,18,3,steel)
    for z in (-3,3):
        beam(m,(-3,0,z),(3,16,z),.35,.35,wood,True)
        beam(m,(3,0,z),(-3,16,z),.35,.35,wood,True)
    models['lookout']=m
    m=Model()
    for x in [-2,2]: m.solid((x,1.1,0),(.12,2.2,.12),steel,True)
    for y in [.35,1.1,2.0]: m.solid((0,y,0),(4.1,.10,.10),steel,True)
    for x in [-1.5,-1,-.5,0,.5,1,1.5]: m.solid((x,1.1,0),(.04,1.8,.04),steel)
    models['fence']=m
    m=Model()
    for x in [-1.5,1.5]: m.solid((x,.5,0),(.15,1,.18),steel,True)
    m.solid((0,.85,0),(4,.35,.16),(.74,.76,.73,1),True)
    models['guardrail']=m
    m=Model()
    m.solid((0,.12,0),(4,.24,3),concrete,True)
    for x in [-.9,.9]:
        m.solid((x,1.4,0),(1.2,2.6,1.8),steel,True)
        for y in [.5,.8,1.1,1.4,1.7,2.0]: m.solid((x,y,-.92),(1.1,.10,.08),(.20,.24,.25,1))
        for z in [-.55,0,.55]: m.solid((x,2.95,z),(.22,.5,.22),wood,True)
    models['transformer']=m
    m=Model()
    for x in [-2,2]: m.solid((x,4,0),(.6,8,.6),concrete,True)
    m.solid((0,7.7,0),(5,.6,.8),concrete,True)
    models['pier']=m
    result={}
    for name,m in models.items():
        identity='environment-'+name
        data=glb([(vs,color,fs) for color,(vs,fs) in m.groups.items()],indexed=True)
        record=dict(id=identity,path=identity+'.glb',collision=m.collision,
            attribution=dict(source='mapeditor-environment-modules',license='MIT',notice='Original metre-scale procedural geometry; source retained in environment_assets.py.'))
        if hasattr(m,'convex_collision'): record['convex_collision']=m.convex_collision
        result[identity]=(record,data)
    return result
