import sys
from osm_fixture import XML, pbf

if __name__ == "__main__":
    pbf(sys.argv[1], XML.replace('<tag k="highway" v="residential"/>', '<tag k="highway" v="residential"/><tag k="bridge" v="yes"/>'))
