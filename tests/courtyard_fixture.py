"""Synthetic complete OSM courtyard snapshot; public test data only."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from osm_fixture import pbf

def xml():
    points=[(9,55),(9.002,55),(9.002,55.002),(9,55.002),(9.0005,55.0005),(9.0015,55.0005),(9.0015,55.0015),(9.0005,55.0015)]
    nodes=''.join(f'<node id="{i+1}" lon="{x}" lat="{y}"/>' for i,(x,y) in enumerate(points))
    ways=''
    for identity,refs in [(1,[1,2,3]),(2,[1,4,3]),(3,[5,6,7,8,5])]:
        ways+=f'<way id="{identity}">'+''.join(f'<nd ref="{i}"/>' for i in refs)+'</way>'
    return '<osm version="0.6">'+nodes+ways+'<relation id="1"><member type="way" ref="2" role="outer"/><member type="way" ref="1" role="outer"/><member type="way" ref="3" role="inner"/><tag k="type" v="multipolygon"/><tag k="building" v="public"/><tag k="height" v="12"/></relation></osm>'
if __name__=='__main__':pbf(sys.argv[1],xml())
