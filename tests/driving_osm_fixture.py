"""Small synthetic connected roads; no external or user data."""
import sys
from osm_fixture import pbf
pbf(sys.argv[1], '''<osm version="0.6">
<node id="1" lon="9" lat="55"/><node id="2" lon="9.005" lat="55"/>
<node id="3" lon="9.005" lat="55.003"/><node id="4" lon="9.01" lat="55"/>
<way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/><tag k="width" v="32"/></way>
<way id="2"><nd ref="2"/><nd ref="3"/><tag k="highway" v="service"/><tag k="width" v="32"/></way>
<way id="3"><nd ref="2"/><nd ref="4"/><tag k="highway" v="secondary"/><tag k="width" v="32"/></way>
</osm>''')
