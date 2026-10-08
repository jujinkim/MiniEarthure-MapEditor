"""Original metre-scale MIT modules. Source geometry is retained in this file.

Material batching shares geometry and colors; no texture copies or baked lights.
Every load-bearing/roadside solid has an explicit collision proxy.
"""
from city_assets import Model
from driving_school_map import glb


def library():
    steel=(.34,.39,.40,1); concrete=(.63,.65,.61,1); wood=(.49,.33,.20,1)
    models={}
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
        result[identity]=(record,data)
    return result
