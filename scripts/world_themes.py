#!/usr/bin/env python3
"""Author seven independent miniature world scenes in a NEW directory.

Uses the public MapKit static library and baked sign images. The sample axes are
independent overrides; neither region chooses language nor climate chooses physics.
No downloads or private repositories are needed. Existing town v3–v6 is untouched.
"""
import argparse
import copy
import json
from pathlib import Path
from reference_maps import canonical, empty, road, sha, rectangle
from driving_school_map import cm

PROFILES={
 'polar':dict(architecture='utility',climate='polar',settlement='outpost',reference='Fictional Svalbard coastal research outpost',sign='latin'),
 'metropolis':dict(architecture='contemporary',climate='temperate',settlement='dense',reference='Fictional Seoul contemporary station frontage',sign='korean'),
 'countryside':dict(architecture='farm',climate='temperate',settlement='farmstead',reference='Fictional northern French farm lane',sign='latin'),
 'middle-eastern':dict(architecture='courtyard',climate='temperate',settlement='village',reference='Fictional Levantine stone courtyard market; not a desert preset',sign='arabic'),
 'desert':dict(architecture='utility',climate='arid',settlement='sparse',reference='Fictional Wadi Rum inspired sandstone service track',sign='latin'),
 'jungle':dict(architecture='veranda',climate='humid',settlement='sparse',reference='Fictional Borneo forest clearing with shelter and layered vegetation',sign='latin'),
 'southeast-asian':dict(architecture='veranda',climate='tropical',settlement='village',reference='Fictional central Thai canal-side shop verandas',sign='thai'),
}
ARCHITECTURE={'utility':'utility-cabin','contemporary':'podium-tower','farm':'gable-barn','courtyard':'courtyard-house','veranda':'deep-veranda'}
CLIMATES=['polar','temperate','arid','humid','tropical']
SETTLEMENTS=['outpost','dense','farmstead','village','sparse']
ATTRIBUTION=dict(source='mapeditor-world-themes-v1',license='MIT',notice='Original fictional miniature scenes; region references describe design cues, not a surveyed location or a universal regional style. No extracted assets or user datasets.')

def compose(profile,architecture=None,climate=None,settlement=None,sign=None):
    result=copy.deepcopy(PROFILES[profile])
    for key,value,choices in [('architecture',architecture,ARCHITECTURE),('climate',climate,CLIMATES),('settlement',settlement,SETTLEMENTS)]:
        if value is not None:
            if value not in choices:raise ValueError('Unknown '+key+': '+value)
            result[key]=value
    if sign is not None: result['sign']=sign
    return result

def scene(profile,library,signs,**overrides):
    config=compose(profile,**overrides)
    doc=empty('world-'+profile+'-v1',9600,1600)
    doc.update(recipe_version=6,bounds={'min':[0,0],'max':[9600,6400]},surface_areas=[])
    doc['provenance'].update(tool_id='mapeditor-world-themes',build_id='world-themes-v1',first_created='2026-09-11T00:00:00Z',last_edited='2026-09-11T00:00:00Z')
    # Axis metadata is inert attribution, content independent of UI language.
    doc['attributions']=[ATTRIBUTION,dict(source='world-authoring-profile',license='MIT',notice=json.dumps(config,sort_keys=True))]
    payloads={};used={};placements=doc['placements']
    catalog=json.loads((library/'library.json').read_text())
    assets={a['id']:a for a in catalog['assets']}
    def place(name,x,z,turn=0,h=0,ident=None):
        asset='world-'+name
        if asset not in used:
            record=copy.deepcopy(assets[asset]);data=(library/record['path']).read_bytes()
            if sha(data)!=catalog['sha256'][record['path']]:raise ValueError('Common library hash mismatch: '+asset)
            payloads[record['path']]=data;used[asset]=record
        placements.append(dict(id=ident or name+'-'+str(len(placements)),asset_id=asset,position=cm((x,h,z)),quarter_turns=turn))
    dense=config['settlement']=='dense'
    width=10 if dense else (4 if config['settlement']=='sparse' else 6)
    surface='gravel' if config['climate']=='arid' else ('dirt' if config['climate']=='humid' else 'asphalt')
    road(doc,'traverse',[[400,0,3200],[9200,0,3200]],width=width*100,surface=surface)
    doc['roads'][0]['sidewalk_cm']=120 if dense else 0
    # Off-road paving leaves room for doors, shaded passages and planting.
    if config['settlement'] in ['dense','village']:
        doc['surface_areas'].append(dict(id='frontage',polygon=rectangle(500,1700,8600,3000),surface='concrete'))
    plot={'polar':'polar','arid':'arid','humid':'humid','tropical':'tropical','temperate':'farm' if config['settlement']=='farmstead' else 'garden'}[config['climate']]
    for z in [8,56]:
        for x in range(8,96,16):place('plot-'+plot,x,z)
    body=ARCHITECTURE[config['architecture']]
    if body=='utility-cabin' and config['climate']=='polar':body='polar-cabin'
    xs={'dense':[14,28,42,56,70,84],'village':[18,36,54,74],'farmstead':[24,65],'outpost':[25, 62],'sparse':[58]}[config['settlement']]
    for i,x in enumerate(xs):
        place(body,x,20,2,ident='front-'+str(i))
        if dense or (config['settlement']=='village' and i%2==0):place(body,x+2,44,0,ident='rear-'+str(i))
    # Separate signboard and image; common body/collision hashes are unchanged
    # for all languages. It sits beside the road, never across the drive lane.
    sign_x=xs[0]
    sign_z=26 if dense else 27
    place('blank-signboard',sign_x,sign_z,2,h=.8,ident='signboard')
    sign_path=signs/(config['sign']+'.glb');meta=json.loads((signs/(config['sign']+'.json')).read_text())
    data=sign_path.read_bytes()
    if sha(data)!=meta['glb_sha256']:raise ValueError('Sign image hash mismatch')
    target='signs/'+sha(data)+'.glb';payloads[target]=data
    doc['assets'].append(dict(id='map-writing',path=target,attribution=dict(source=meta['font_source'],license=meta['font_license'],notice=json.dumps(meta,ensure_ascii=False)),
        collision=[dict(center=[0,55,0],size_cm=[300,110,2])]))
    placements.append(dict(id='map-writing-instance',asset_id='map-writing',position=cm((sign_x,.9,sign_z+.09)),quarter_turns=2))
    climate=config['climate']
    if climate=='polar':place('shade-shelter',78,24)
    elif climate=='arid':
        for x,z in [(12,22),(31,20),(46,44),(77,23),(86,44)]:place('arid-shrub',x,z)
        place('rock-outcrop',28,43)
    elif climate in ['humid','tropical']:
        for x in [20,40,75]:place('drain-channel',x,38,1)
        if climate=='humid':place('shade-shelter',28,44)
    elif config['settlement']=='farmstead':
        for x in range(12,90,4):place('farm-fence',x,40)
    else:
        for x in [15,46,78]:place('bench',x,38 if dense else 39)
    for x in ([9,51,93] if dense else [10,49,86]):
        if config['settlement'] not in ['sparse','farmstead']:place('street-lamp',x,38.4 if dense else 37+width/2,h=.12 if dense else 0)
    if config['architecture']=='courtyard':
        for x in [30,65]:place('shade-shelter',x,43)
    doc['assets']+=list(used.values())
    # Representative wall ray looks at the road-facing solid wing, not the open
    # middle of a courtyard. Height avoids raised floor / roof-only contacts.
    wall_x=xs[0]+(3.3 if body=='courtyard-house' else 0)
    depth={'utility-cabin':6,'polar-cabin':6,'podium-tower':9,'gable-barn':8,'courtyard-house':8,'deep-veranda':5}[body]
    report=dict(profile=profile,axes=config,common_assets={a['id']:catalog['sha256'][a['path']] for a in used.values()},
        source_bytes=sum(map(len,payloads.values())),image_decoded_bytes=1024*256*4,
        spawn=dict(x=4600 if config["settlement"]=="sparse" else 1200,y=3200,surface='traverse',yaw=-1.5707963267948966),
        view_center_m=[32,26],wall=dict(x=wall_x,y=20+depth/2,height=2.1,asset='world-'+body),
        limits='Existing runtime caps. Road traction is unchanged; visual snow/ice/wetness does not define new physics.',
        sign=meta,source_hashes={p:sha(v) for p,v in payloads.items()})
    return doc,payloads,report

def create(destination,library,signs,profiles=None,**overrides):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    summaries={}
    for profile in profiles or PROFILES:
        doc,payloads,report=scene(profile,Path(library),Path(signs),**overrides)
        folder=destination/profile;folder.mkdir()
        for path,data in {'document.json':canonical(doc),**payloads}.items():
            target=folder/path;target.parent.mkdir(exist_ok=True,parents=True);target.write_bytes(data)
        (folder/'world.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
        summaries[profile]=report
    return summaries

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination',type=Path)
    p.add_argument('--library',type=Path,default=Path(__file__).resolve().parents[1]/'addons/mapkit/examples/world-library')
    p.add_argument('--signs',type=Path,required=True);p.add_argument('--profile',choices=PROFILES)
    p.add_argument('--architecture',choices=ARCHITECTURE);p.add_argument('--climate',choices=CLIMATES);p.add_argument('--settlement',choices=SETTLEMENTS);p.add_argument('--sign')
    a=p.parse_args();create(a.destination,a.library,a.signs,[a.profile] if a.profile else None,architecture=a.architecture,climate=a.climate,settlement=a.settlement,sign=a.sign)
