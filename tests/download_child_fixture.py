"""Replace only transport for native UI/IPC tests; run the production downloader."""
import io
from email.message import Message
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0, str(Path(sys.argv[1]).parent))
import osm_download as d
from osm_fixture import pbf
with tempfile.TemporaryDirectory() as directory:
    raw = pbf(Path(directory)/'synthetic.pbf')
class Response(io.BytesIO):
    status=200
    def __init__(self,url):
        super().__init__(raw)
        self.url=url
        self.headers=Message()
        self.headers['Content-Length']=str(len(raw))
        self.headers['ETag']='"fixture"'
    def geturl(self): return self.url
    def read(self, size=-1):
        if "slow" in self.url:
            time.sleep(0.03)
            size=min(size,64)
        return super().read(size)

def opener(url,method,headers=None): return Response(url)
d.probe.__defaults__=(opener,)
d.download.__defaults__=(opener,)
sys.argv=sys.argv[1:]
d.main()
