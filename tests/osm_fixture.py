"""Synthetic OSM snapshots only; no downloaded or private data."""
from pathlib import Path
import sys

XML = '''<osm version="0.6" generator="mapeditor-synthetic">
<node id="1" lon="9" lat="55"/><node id="2" lon="9.0002" lat="55"/>
<node id="3" lon="9.0002" lat="55.0002"/><node id="4" lon="9" lat="55.0002"/>
<node id="5" lon="9.0005" lat="55"/><node id="6" lon="9.001" lat="55"/>
<node id="7" lon="9.002" lat="55"/><node id="8" lon="9.0022" lat="55"/>
<node id="9" lon="9.0022" lat="55.0002"/><node id="10" lon="9.002" lat="55.0002"/>
<node id="11" lon="9.003" lat="55"><tag k="amenity" v="bench"/></node>
<way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
<tag k="building" v="yes"/><tag k="height" v="12 m"/></way>
<way id="2"><nd ref="5"/><nd ref="6"/><tag k="highway" v="residential"/><tag k="width" v="4.5"/></way>
<way id="3"><nd ref="7"/><nd ref="8"/><nd ref="9"/><nd ref="10"/><nd ref="7"/><tag k="landuse" v="forest"/></way>
<way id="4"><nd ref="10"/><nd ref="11"/><tag k="barrier" v="fence"/></way>
</osm>'''


def pbf(path, xml=XML):
    import osmium
    # Tests own their temporary destination; never overwrite an existing file.
    with osmium.SimpleWriter(str(path)) as writer:
        for entity in osmium.FileProcessor(osmium.io.FileBuffer(xml.encode(), "osm")):
            writer.add(entity)
    return Path(path).read_bytes()


if __name__ == "__main__":
    pbf(sys.argv[1], XML.replace("12 m", sys.argv[2] + " m") if len(sys.argv) > 2 else XML)
