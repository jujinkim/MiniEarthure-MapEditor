"""Public synthetic place names/geometry only."""
import sys
from osm_fixture import XML, pbf

XML = XML.replace("</osm>", '''<relation id="10">
<member type="way" ref="1" role="outer"/>
<member type="relation" ref="11" role="subarea"/>
<tag k="type" v="boundary"/><tag k="boundary" v="administrative"/>
<tag k="admin_level" v="6"/><tag k="name" v="가상시"/><tag k="name:en" v="Synthetic City"/>
</relation></osm>''')

if __name__ == "__main__": pbf(sys.argv[1], XML)
