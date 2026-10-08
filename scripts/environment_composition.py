"""District-aware facilities and landscape composition (Editor only, MIT)."""
from dataclasses import replace
import math

import shapely
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import nearest_points, polygonize_full, unary_union
from shapely.strtree import STRtree

from environment_layout import (digest, rng, xy, polygons, lines, polygon, rings,
                                geometry_record, districts, plan_paths)
from reference_maps import road


class Composition:
    def districts_stage(self):
        self.districts=districts(self)
        self.road_roles={}
        self.relationships=[]
        self.habitats=[]
        self.road_ground_grid={}
        self.frontages={}

    def road_height(self,x,y):
        factor={'red-canyon':.24,'snow-mountain':.50,'deep-forest':.68}.get(self.profile.id,1)
        return 4+(self.raw_height(x,y)-4)*factor

    def road_stage(self):
        if self.request.mode=='new':
            paths,network=plan_paths(self)
            self.planned_paths=paths
            for line in sorted(network,key=lambda g:g.wkb_hex):
                if line.length<1: continue
                middle=line.interpolate(.5,normalized=True)
                original=min(paths,key=lambda p:p['geometry'].distance(middle))
                kind=original['kind']
                # Piers are certified per short local deck span.
                parts=lines(line) if kind=='ground' else [LineString([a,b]) for a,b in zip(list(line.segmentize(32).coords),list(line.segmentize(32).coords)[1:])]
                for part in parts:
                    coordinates=list(part.segmentize(16).coords)
                    points=[]
                    for a,b in coordinates:
                        level=self.road_height(a,b)
                        if kind!='ground':
                            # Ramps at both ends keep the inherited ground levels.
                            d=original['geometry'].project(Point(a,b));length=original['geometry'].length
                            level+=min(8,d/20,(length-d)/20)
                        points.append([round(a*100),round(level*100),round(b*100)])
                    name='env-road-'+digest([xy(p) for p in coordinates])[:14]
                    road(self.doc,name,points,kind,round(original['width']*100),
                         'dirt' if self.profile.id=='deep-forest' else 'asphalt',
                         'env-node-'+digest(points[0])[:14],'env-node-'+digest(points[-1])[:14])
                    self.doc['roads'][-1]['sidewalk_cm']=120 if self.profile.urban and kind=='ground' else 0
                    self.road_roles[name]=original['role']
        else:
            for meta in getattr(self,'prior_metadata',[]): self.road_roles.update(meta.get('road_hierarchy',{}))
        for record in self.doc.get('roads',[]):
            line=LineString([(p[0]/100,p[2]/100) for p in record['points']])
            self.road_lines.append(line)
            width=max(record['widths_cm'])/100
            self.road_buffers.append(line.buffer(width/2+1.2*self.scale,cap_style=2))
            if record['kind']=='ground':
                for a,b in zip(record['points'],record['points'][1:]):
                    edge=LineString([(a[0]/100,a[2]/100),(b[0]/100,b[2]/100)])
                    for key in self.grid_keys(edge.buffer(width/2+12)):
                        self.road_ground_grid.setdefault(key,[]).append((edge,a[1]/100,b[1]/100,width/2))
        self.road_union=unary_union(self.road_lines)
        self.road_space=unary_union(self.road_buffers)
        self.road_tree=STRtree(self.road_lines)
        blocks,cuts,dangles,invalid=polygonize_full(shapely.union_all(self.road_lines,grid_size=.01))
        self.blocks=polygons(blocks)
        self.diagnostics.append(dict(stage='blocks',blocks=len(self.blocks),invalid_rings=len(lines(invalid))))

    def assembly(self,rule,identity):
        """Return physical members in a local frontage coordinate system."""
        assets=list(rule.objects)
        rows=[]
        if identity.startswith('env-parcel-') and len(assets)==1:
            bounds=self.footprint(self.asset(assets[0]),(0,0),0).bounds
            return [(assets[0],-(bounds[0]+bounds[2])/(2*self.scale),-bounds[1]/self.scale,0)]
        if rule.id=='container-yard':
            # Three actual stack rows, with 8 m truck aisles and a front apron.
            for row in range(3):
                for col in range(4): rows.append(('richer-container',(col-1.5)*8,row*12,0))
        elif rule.id=='loading':
            for row in range(2):
                for col in range(3): rows.append(('richer-container',(col-1)*8,row*15,0))
        elif rule.id=='pipes':
            rows=[('environment-pipe-run',i*12.04,0,0) for i in range(4)]
        elif rule.id=='production':
            rows=[('environment-hall-2',0,7,0),('environment-pipe-run',-9,35,0),('environment-pipe-run',3.04,35,0)]
        elif rule.id=='attractions':
            rows=([('arcade-carousel',-16,4,0),('environment-lookout',16,4,0),('environment-market-1',0,30,0)]
                  if identity.startswith('env-cluster-') else
                  [('environment-wheel',-25,12,0),('arcade-carousel',20,4,0),('environment-lookout',24,25,0)])
        elif assets:
            # Actual footprint bounds decide spacing. Stable variation cycles
            # along a frontage rather than selecting identical neighbours.
            sizes=[self.footprint(self.asset(model),(0,0),0).bounds for model in assets]
            width=sum(a[2]-a[0] for a in sizes)+5*self.scale*(len(assets)-1)
            cursor=-width/2
            for model,bounds in zip(assets,sizes):
                w=bounds[2]-bounds[0]
                rows.append((model,(cursor-bounds[0])/self.scale,-bounds[1]/self.scale,0))
                cursor+=w+5*self.scale
        return rows

    def parcel(self,rule,target,identity,region=None,required=True,side_hint=None):
        if not rule.access: return self.landscape_site(rule,target,identity,region)
        if not self.road_lines: return False
        centre=Point(target)
        eligible=[i for i,r in enumerate(self.doc['roads']) if r['kind']=='ground']
        nearest_indices=sorted(eligible,key=lambda i:self.road_lines[i].distance(centre))[:5]
        assembly=self.assembly(rule,identity)
        local=[(model,self.footprint(self.asset(model),(a*self.scale,b*self.scale),yaw),a*self.scale,b*self.scale,yaw) for model,a,b,yaw in assembly]
        bounds=unary_union([r[1] for r in local]).bounds if local else (-12*self.scale,0,12*self.scale,20*self.scale)
        lo,front,hi,back=bounds
        # Dense usable parcels; school grounds/plazas/loading aprons are tracked
        # separately and cannot impersonate occupied industrial/residential land.
        margin=4*self.scale;apron=(8 if rule.landuse=='industrial' else 5)*self.scale
        width=hi-lo+2*margin;depth=back-front+apron+5*self.scale
        if rule.landuse=='industrial' and any('hall-' in row[0] or 'shed-' in row[0] for row in local):
            occupied=unary_union([row[1] for row in local]).area
            depth=max(depth,occupied/(width*.40))
        if rule.id in ('plaza','queues'): width=max(width,52*self.scale);depth=max(depth,45*self.scale)
        if rule.id=='school': width=max(width,64*self.scale);depth=max(depth,65*self.scale)
        if rule.id=='fields': width=95*self.scale;depth=76*self.scale
        if not assembly: width=max(width,24*self.scale);depth=max(depth,24*self.scale)
        for i in nearest_indices:
            nearest=self.road_lines[i];record=self.doc['roads'][i]
            along=nearest.project(centre)
            for attempt in range(12):
                side=(side_hint if side_hint else 1)*(1 if attempt%2==0 else -1)
                offset=(0 if attempt<2 else ((attempt//2+1)//2)*(1 if attempt//2%2 else -1))*width*.65
                distance=max(width*.52,min(nearest.length-width*.52,along+offset))
                if nearest.length<width+4*self.scale: continue
                p=nearest.interpolate(distance);q=nearest.interpolate(min(nearest.length,distance+self.scale))
                angle=math.atan2(q.y-p.y,q.x-p.x)
                tangent=(math.cos(angle),math.sin(angle));normal=(-tangent[1]*side,tangent[0]*side)
                verge=max(record['widths_cm'])/200+2.0*self.scale
                near=(p.x+normal[0]*verge,p.y+normal[1]*verge)
                def at(a,b): return (near[0]+tangent[0]*a+normal[0]*b,near[1]+tangent[1]*a+normal[1]*b)
                plot=Polygon([at(a,b) for a,b in ((-width/2,0),(width/2,0),(width/2,depth),(-width/2,depth))])
                if not self.window.covers(plot) or plot.intersects(self.forbidden) or any(plot.intersects(s['geometry']) for s in self.sites): continue
                if region is not None and not region.covers(plot): continue
                anchor=at(0,depth/2)
                yaw=round((math.degrees(angle)+(180 if side<0 else 0))*1000)/1000
                # Local +Z points away from the street, irrespective of side.
                candidates=[]
                for model,area,a,b,rotation in local:
                    centred=a-(lo+hi)/2
                    pos=at(centred if side>0 else -centred,b-front+apron)
                    pos=(round(pos[0]*100)/100,round(pos[1]*100)/100)
                    footprint=self.footprint(self.asset(model),pos,yaw+rotation)
                    levels=[self.height(*p) for p in footprint.exterior.coords]
                    if not plot.covers(footprint) or footprint.intersects(self.forbidden) or any(footprint.distance(p)<.3*self.scale for p in self.nearby(footprint.buffer(.3*self.scale))) or (self.request.mode!='new' and max(levels)-min(levels)>self.footing_limit(footprint)): break
                    if any(footprint.distance(previous[3])<.025 for previous in candidates): break
                    candidates.append((model,pos,yaw+rotation,footprint))
                if len(candidates)!=len(local): continue
                # A frontage spine reaches every door and all working members;
                # dock aisles remain clear across the complete assembly.
                spine=LineString([at(-width/2+margin,apron*.40),at(width/2-margin,apron*.40)])
                access_lines=[LineString([(p.x,p.y),at(0,apron*.4)]),spine]
                for model,pos,rotation,area in candidates:
                    door=nearest_points(Point(at((pos[0]-near[0])*tangent[0]+(pos[1]-near[1])*tangent[1],0)),area)[1]
                    a=(door.x-near[0])*tangent[0]+(door.y-near[1])*tangent[1]
                    b=(door.x-near[0])*normal[0]+(door.y-near[1])*normal[1]
                    if b>apron+2*self.scale and rule.id in ('container-yard','loading','production','attractions'):
                        aisle=(1 if a>0 else -1)*(width/2-1.5*self.scale)
                        access_lines.append(LineString([at(aisle,apron*.4),at(aisle,b-2*self.scale),at(a,b-2*self.scale),door.coords[0]]))
                    else: access_lines.append(LineString([spine.interpolate(spine.project(door)).coords[0],door.coords[0]]))
                entrance=unary_union([line.buffer(1.2*self.scale,cap_style=2) for line in access_lines])
                if entrance.intersects(self.water) or entrance.intersects(self.protected) or entrance.intersects(self.fixed): continue
                if any(entrance.intersection(area.buffer(-.06*self.scale)).area>.02*self.scale**2 for _,_,_,area in candidates): continue
                if self.request.mode=='new':
                    pad=(plot,self.road_height(p.x,p.y));self.pads.append(pad)
                    for cell in self.grid_keys(plot.buffer(5)): self.pad_grid.setdefault(cell,[]).append(pad)
                placed=[]
                for n,(model,pos,rotation,area) in enumerate(candidates):
                    name=identity+'-object-'+str(n)
                    if self.place(name,model,pos,rotation,plot,clearance=0): placed.append(name)
                if len(placed)!=len(candidates):
                    # Candidates were checked transactionally; retained manual
                    # members are never filled around as a partial facility.
                    if candidates: continue
                self.surface(identity+'-entry',entrance.difference(self.road_space),'concrete' if self.profile.urban else 'gravel',anchor)
                self.surface(identity+'-yard',plot,rule.surface,anchor)
                if rule.id=='fields':
                    for ix in range(2,int(width/(8*self.scale))-1):
                        for iz in range(2,int(depth/(8*self.scale))-1):
                            pos=at(-width/2+ix*8*self.scale,iz*8*self.scale)
                            name=identity+'-crop-'+str(ix)+'-'+str(iz)
                            if self.place(name,'richer-crop-'+str(1+(ix+iz)%2),pos,yaw,plot): placed.append(name)
                district=next((d['id'] for d in self.districts if d['geometry'].covers(Point(anchor))), 'infill')
                self.sites.append(dict(id=identity,group=rule.id,landuse=rule.landuse,geometry=plot,anchor=anchor,
                    objects=placed,entrance=entrance,access=nearest.distance(Point(anchor)),required=required,
                    road_id=record['id'],frontage=[record['id'],side,round(distance,2)],district=district,
                    access_lines=[[[round(a,3),round(b,3)] for a,b in line.coords] for line in access_lines],
                    composition='working-yard' if rule.landuse=='industrial' else 'open-space' if rule.id in ('plaza','queues','school','park') else 'frontage'))
                return True
        return False

    def landscape_site(self,rule,target,identity,region=None):
        random=rng(self.request.seed,'landscape',identity)
        sizes=[self.footprint(self.asset(model),(0,0),0).bounds for model in rule.objects]
        span=sum(a[2]-a[0]+3*self.scale for a in sizes)
        for attempt in range(24):
            angle=attempt*2.4;radius=math.sqrt(attempt)*25*self.scale
            p=(target[0]+math.cos(angle)*radius,target[1]+math.sin(angle)*radius)
            area=Point(p).buffer(max(38*self.scale,span*.65),quad_segs=8)
            if not self.window.covers(area) or area.intersects(self.forbidden) or (region is not None and not region.covers(area)) or any(area.intersects(s['geometry']) for s in self.sites): continue
            placed=[]
            cursor=-span/2
            for i,(model,bounds) in enumerate(zip(rule.objects,sizes)):
                width=bounds[2]-bounds[0]
                pos=(p[0]+cursor+width/2,p[1]);cursor+=width+3*self.scale
                name=identity+'-object-'+str(i)
                if self.place(name,model,pos,0,area,natural=True): placed.append(name)
            if len(placed)!=len(rule.objects): continue
            self.surface(identity+'-ground',area,rule.surface,p)
            self.sites.append(dict(id=identity,group=rule.id,landuse=rule.landuse,geometry=area,anchor=p,objects=placed,
                entrance=Polygon(),access=0,required=True,district=next((d['id'] for d in self.districts if rule.id in d['groups']),'landscape'),access_lines=[],composition='landscape'))
            return True
        return False

    def facilities_stage(self):
        if not self.new_layout:
            return self.semantic_facilities()
        rules=self.profile.rules
        for rule in rules:
            if rule.landuse=='water' or rule.id in ('bridge','elevated-walkways'): continue
            # Transport groups are verified from actual roads, not empty plots.
            if rule.landuse=='transport' and not rule.objects: continue
            if any(s['id']=='env-facility-'+rule.id and s.get('retained') for s in self.sites): continue
            district=next((d for d in self.districts if rule.id in d['groups']),self.districts[0])
            target=district['anchor']
            local_index=list(district['groups']).index(rule.id) if rule.id in district['groups'] else 0
            # Facility-local search radiates from its functional hub, not quadrants.
            found=False
            for attempt in range(14):
                theta=(local_index+attempt)*2.39996
                radius=math.sqrt(local_index+attempt)*48*self.scale
                candidate=(target[0]+math.cos(theta)*radius,target[1]+math.sin(theta)*radius)
                region=district['geometry'] if self.profile.road_mode=='hierarchy' else None
                if self.parcel(rule,candidate,'env-facility-'+rule.id,region,required=True): found=True;break
            if not found:
                self.diagnostics.append(dict(stage='facility',id='env-facility-'+rule.id,district=district['id'],position_cm=xy(target),error='No complete accessible assembly after bounded relocation'))
        if self.profile.id=='sky-park':
            fair=next(d for d in self.districts if d['id']=='fair')
            a,b,A,B=fair['geometry'].bounds;cx,cy=fair['anchor']
            for index,(u,v) in enumerate(((-.25,-.20),(.27,-.12),(.08,.23))):
                target=(cx+(A-a)*u,cy+(B-b)*v)
                for group in ('attractions','queues'):
                    identity='env-cluster-'+str(index)+'-'+group
                    if any(s['id']==identity for s in self.sites): continue
                    rule=next(r for r in rules if r.id==group)
                    found=False
                    for attempt in range(12):
                        theta=attempt*2.4;distance=math.sqrt(attempt)*35
                        point=(target[0]+math.cos(theta)*distance,target[1]+math.sin(theta)*distance)
                        if self.parcel(rule,point,identity,fair['geometry']): found=True;break
                    if not found: self.diagnostics.append(dict(stage='facility',id=identity,district='fair',position_cm=xy(target),required_failure=True,error='No complete attraction/queue cluster'))
        # Lots fill both sides of district-local streets. Spacing follows actual
        # model width; density controls occupied slots, never streets or hubs.
        if self.profile.road_mode=='hierarchy':
            for i,line in enumerate(self.road_lines):
                record=self.doc['roads'][i]
                if record['kind']!='ground': continue
                for side in (-1,1):
                    step=36 if self.profile.id!='machine-factory' else 46
                    for slot in range(1,int(line.length/step)):
                        p=line.interpolate(slot*step);q=line.interpolate(min(line.length,slot*step+1))
                        theta=math.atan2(q.y-p.y,q.x-p.x)
                        probe=Point(p.x-math.sin(theta)*side*20,p.y+math.cos(theta)*side*20)
                        district=next((d for d in self.districts if d['geometry'].covers(probe)),None)
                        if not district or not district['core']: continue
                        use=district['landuse']
                        if use not in ('residential','commercial','industrial'): continue
                        radius=max(1,math.sqrt(district['geometry'].area/math.pi))
                        weight=max(0,1-probe.distance(Point(district['anchor']))/radius)
                        strength=district['density'][0]+(district['density'][1]-district['density'][0])*weight
                        random=rng(self.request.seed,'frontage',district['id'],record['id'],side,slot)
                        if random.random()>min(1,strength*self.request.density): continue
                        variant=(slot+int(digest([district['id'],record['id'],side])[:4],16))%3
                        family='home' if use=='residential' else 'market' if use=='commercial' else 'hall'
                        base=next(r for r in rules if r.landuse==use and r.objects)
                        selected=replace(base,objects=('environment-'+family+'-'+str(variant),))
                        identity='env-parcel-'+digest([district['id'],record['id'],side,slot])[:16]
                        self.parcel(selected,(probe.x,probe.y),identity,district['geometry'],required=False,side_hint=side)

    def semantic_facilities(self):
        for region in sorted(self.context.regions,key=lambda r:r['id']):
            if region.get('protected') or region.get('landuse') in ('water','wetland'): continue
            area=polygon(region).intersection(self.window).difference(self.forbidden)
            matching=[r for r in self.profile.rules if r.landuse==region.get('landuse') and r.objects]
            for part in polygons(area):
                if not matching:
                    self.surface('env-open-'+digest([region['id'],part.wkb_hex])[:16],part,'grass',part.centroid.coords[0]);continue
                step=64*self.scale;a,b,A,B=part.bounds
                for ix in range(math.floor(a/step),math.ceil(A/step)):
                    for iy in range(math.floor(b/step),math.ceil(B/step)):
                        key='env-infill-'+digest([region['source_id'],ix,iy])[:16]
                        if any(s['id']==key for s in self.sites): continue
                        target=((ix+.5)*step,(iy+.5)*step)
                        if not part.covers(Point(target)): continue
                        if rng(self.request.seed,'infill-density',key).random()>min(1,self.request.density): continue
                        rule=matching[int(digest(key)[:6],16)%len(matching)]
                        if rule.landuse in ('residential','commercial'):
                            family='home' if rule.landuse=='residential' else 'market'
                            rule=replace(rule,objects=('environment-'+family+'-'+str((ix+iy)%3),))
                        self.parcel(rule,target,key,part,required=False)
        if not self.context.regions:
            self.diagnostics.append(dict(stage='semantics',warning='No land-use evidence; only low-intensity ground cover'))

    def habitat_stage(self):
        land=self.window.difference(self.water)
        if self.profile.id=='deep-forest':
            shore=self.water.buffer(75).difference(self.water).intersection(land)
            clear=unary_union([s['geometry'].buffer(40) for s in self.sites if s['group'] in ('campground','ranger-station')]).intersection(land)
            dense=land.difference(unary_union([shore,clear]))
            areas=[('lakeshore',shore),('clearing',clear),('dense-woodland',dense)]
        elif self.profile.id in ('red-canyon','snow-mountain'):
            x,y,X,Y=self.window.bounds;groups=[[],[],[]]
            for ix in range(math.floor(x/64),math.ceil(X/64)):
                for iy in range(math.floor(y/64),math.ceil(Y/64)):
                    level=(self.raw_height((ix+.5)*64,(iy+.5)*64)-4)/self.profile.relief_m
                    group=0 if level<.20 else 1 if level<.55 else 2
                    groups[group].append(box(ix*64,iy*64,(ix+1)*64,(iy+1)*64))
            names=('dry-channel','scree','cliff') if self.profile.id=='red-canyon' else ('valley-forest','alpine-rock','snowfield')
            areas=[(name,unary_union(parts).intersection(land)) for name,parts in zip(names,groups)]
        else:
            core=unary_union([d['geometry'] for d in self.districts if d['core']])
            areas=[('edge',core.buffer(55).difference(core).intersection(land)),
                   ('grove',land.difference(core.buffer(55))),('meadow',core.intersection(land))]
        self.habitats=[dict(id=name,geometry=area) for name,area in areas if not area.is_empty]
        transition=unary_union([h['geometry'].boundary.buffer(14) for h in self.habitats]).intersection(land.buffer(-8))
        self.habitats.append(dict(id='transition',geometry=transition))

    def nature_stage(self):
        self.habitat_stage()
        # Visible terrain bands follow the same landscape geometry used by
        # planting. Their area never changes with the decoration density slider.
        if self.new_layout:
            materials={'lakeshore':'gravel','clearing':'grass','dry-channel':'dirt','scree':'gravel','alpine-rock':'gravel','valley-forest':'grass'}
            excluded=unary_union([self.forbidden,*[s['geometry'] for s in self.sites]])
            for habitat in self.habitats:
                material=materials.get(habitat['id'])
                if not material: continue
                area=habitat['geometry'].difference(excluded)
                a,b,A,B=area.bounds if not area.is_empty else (0,0,0,0)
                for ix in range(math.floor(a/128),math.ceil(A/128)):
                    for iy in range(math.floor(b/128),math.ceil(B/128)):
                        part=area.intersection(box(ix*128,iy*128,(ix+1)*128,(iy+1)*128))
                        self.surface('env-habitat-'+habitat['id']+'-'+str(ix)+'-'+str(iy),part,material,((ix+.5)*128,(iy+.5)*128))
        scale=self.scale;step=(13 if self.profile.id=='deep-forest' else 21 if self.profile.id=='snow-mountain' else 34)*scale
        x,y,X,Y=self.window.bounds;sites=unary_union([s['geometry'] for s in self.sites]).buffer(8*scale if self.profile.id=='deep-forest' else 0)
        for ix in range(math.floor(x/step),math.ceil(X/step)):
            for iy in range(math.floor(y/step),math.ceil(Y/step)):
                random=rng(self.request.seed,'nature',ix,iy)
                p=((ix+.2+.6*random.random())*step,(iy+.2+.6*random.random())*step)
                point=Point(p)
                if not self.window.covers(point) or sites.covers(point): continue
                if not self.new_layout:
                    regions=[r for r in self.context.regions if polygon(r).covers(point)]
                    if not any(r['landuse'] in ('forest','orchard','park','scrub','grassland') and not r.get('protected') for r in regions):
                        if random.random()<.12 and not point.buffer(2*scale).intersects(self.forbidden): self.surface('env-cover-%d-%d'%(ix,iy),point.buffer(1.5*scale,quad_segs=3),'grass',p)
                        continue
                habitat=next((h['id'] for h in self.habitats if h['geometry'].covers(point)), 'edge')
                cluster=.45+.3*math.sin(p[0]/(85*scale))*math.cos(p[1]/(100*scale))
                if self.profile.id=='deep-forest' and habitat=='dense-woodland': cluster=.72+.20*math.sin(p[0]/85)*math.cos(p[1]/100)
                if habitat in ('clearing','snowfield','dry-channel','meadow'): cluster*=.22
                if random.random()>min(.92,cluster*self.request.density): continue
                if self.profile.id=='red-canyon':
                    model=('environment-strata' if habitat=='cliff' else 'environment-boulder-'+str((ix+iy)%3))
                elif self.profile.id=='snow-mountain':
                    model=random.choice(('environment-pine','environment-sapling','environment-canopy-birch')) if habitat=='valley-forest' else 'environment-boulder-'+str((ix+iy)%3)
                else:
                    model=random.choice(('environment-canopy-oak','environment-canopy-birch','environment-pine','environment-sapling'))
                    if self.profile.id=='deep-forest' and habitat=='dense-woodland':
                        model=random.choice(('environment-canopy-mature-oak','environment-canopy-mature-oak','environment-canopy-mature-birch','environment-pine-mature','environment-sapling'))
                    if habitat=='lakeshore': model=random.choice(('environment-canopy-birch','environment-sapling','richer-grove-0','environment-boulder-0'))
                    if self.profile.id=='deep-forest' and random.random()<.2: model=random.choice(('richer-grove-0','richer-grove-1','environment-fallen-log','environment-boulder-0'))
                self.place('env-nature-%d-%d'%(ix,iy),model,p,random.randrange(360),natural=True)
        if self.profile.id=='red-canyon' and self.new_layout:
            # A continuous geological feature follows the analytic ridge crest.
            # Touching rock layers intentionally overlap; roads remain excluded.
            for ix in range(math.floor(x/27),math.ceil(X/27)):
                a=ix*27+13.5;b=(math.pi/2-a/600)*150
                for band in range(-1,4):
                    p=(a,b+band*math.tau*150)
                    self.place('env-cliff-%d-%d'%(ix,band),'environment-strata',p,-math.degrees(math.atan(.25)),natural=True,clearance=0)

    def composition_metadata(self):
        return dict(districts=[{**{k:v for k,v in d.items() if k!='geometry'},'boundaries':geometry_record(d['geometry'])} for d in self.districts],
            road_hierarchy=self.road_roles,
            habitats=[dict(id=h['id'],boundaries=geometry_record(h['geometry'])) for h in self.habitats],
            protected=[dict(id=r['id'],boundaries=geometry_record(polygon(r))) for r in self.context.protected],
            relationships=self.relationships,
            sites=[{**{k:v for k,v in s.items() if k not in ('geometry','entrance','retained')},
                    'boundaries':geometry_record(s['geometry']),'entrances':geometry_record(s['entrance'])} for s in self.sites])
