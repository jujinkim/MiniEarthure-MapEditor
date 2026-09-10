"""Public synthetic >32 MiB PBF, no external data or private dependency."""
import sys
import struct
import tempfile
from pathlib import Path
from osm_fixture import XML, multipolygon_xml


def large_pbf(path):
    import osmium
    # Keep each uncompressed blob below the PBF 32 MiB limit as well as making
    # the *whole source* exceed the old importer cap. No giant invalid blob.
    def blob_size(header):
        offset=0
        def integer():
            nonlocal offset
            result,shift=0,0
            while True:
                byte=header[offset]; offset+=1
                result|=(byte&127)<<shift
                if byte<128: return result
                shift+=7
        while offset<len(header):
            key=integer()
            value=integer()
            if key==24: return value
            if key&7==2: offset+=value
        raise ValueError("synthetic writer omitted blob size")
    with tempfile.TemporaryDirectory() as temp, Path(path).open("xb") as output:
        for batch in range(13):
            part=Path(temp)/f"{batch}.pbf"
            with osmium.SimpleWriter(osmium.io.File(str(part), "pbf,pbf_compression=none")) as writer:
                for identity in range(1000+batch*100,1000+(batch+1)*100) if batch<12 else []:
                    writer.add_node(osmium.osm.mutable.Node(id=identity, location=(20,60),
                        tags={f"synthetic_{k}": f"{identity}:{k}:" + "x"*480 for k in range(64)}))
                if batch==12:
                    for entity in osmium.FileProcessor(osmium.io.FileBuffer(multipolygon_xml().encode(), "osm")):
                        writer.add(entity)
            raw=part.read_bytes()
            length=struct.unpack(">I",raw[:4])[0]
            header_end=4+length+blob_size(raw[4:4+length])
            output.write(raw if batch==0 else raw[header_end:])
    return Path(path).stat().st_size


if __name__ == "__main__":
    print(large_pbf(sys.argv[1]))
