import io
import json
from email.message import Message
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/importers'))
import osm_download as d

URL = d.BASE + 'europe/monaco-latest.osm.pbf'
class Response(io.BytesIO):
    status = 200
    def __init__(self, body=b'fixture', size='7', etag='"one"'):
        super().__init__(body)
        self.headers = Message()
        if size is not None: self.headers['Content-Length'] = size
        self.headers['ETag'] = etag
    def geturl(self): return URL

class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.part = self.root / 'download.part'
        self.target = self.root / 'source.osm.pbf'
        self.plan = d.probe(URL, lambda *a: Response())
    def fetch(self, response):
        events = []
        result = d.download(self.plan, self.part, self.target, lambda *a: events.append(a), lambda *a: response)
        return result, events
    def test_complete_and_nonoverwrite(self):
        result, events = self.fetch(Response())
        self.assertEqual(self.target.read_bytes(), b'fixture')
        self.assertEqual(result['actual_bytes'], 7)
        self.assertEqual(events, [(0,7),(7,7)])
        self.assertEqual(json.loads(self.target.with_suffix('.json').read_text()), result)
        self.part.unlink()
        with self.assertRaises(FileExistsError): self.fetch(Response())
        self.assertEqual(self.target.read_bytes(), b'fixture')
    def test_unknown_length(self):
        self.plan = d.probe(URL, lambda *a: Response(size=None))
        _, events = self.fetch(Response(size=None))
        self.assertEqual(events[-1], (7,d.MAX_INPUT))
    def test_failure_preserves_existing_source(self):
        original = self.root/'original.pbf'; original.write_bytes(b'keep')
        for response in [Response(b'bad'), Response(etag='"changed"'), Response(size='40000000'), Response(size='-1')]:
            self.part.unlink(missing_ok=True)
            with self.assertRaises(ValueError): self.fetch(response)
            self.assertFalse(self.target.exists())
            self.assertEqual(original.read_bytes(), b'keep')
    def test_encoding_framing_and_status(self):
        for key,value in [('Content-Encoding','gzip'),('Content-Length','7'),('Transfer-Encoding','chunked')]:
            response = Response(); response.headers[key] = value
            with self.assertRaises(ValueError): d.metadata(response)
        response = Response(); response.status=206
        with self.assertRaises(ValueError): d.metadata(response)
    def test_url_and_redirect_defense(self):
        for url in ['http://download.geofabrik.de/a.osm.pbf', URL+'?x=1', URL+'#x', d.BASE+'../a.osm.pbf', 'https://download.geofabrik.de.evil/a.osm.pbf', d.BASE+'%2e/a.osm.pbf']:
            with self.assertRaises(ValueError): d.checked_url(url)
        request = urllib.request.Request(URL, method='HEAD')
        handler=d.Redirects()
        for _ in range(3): request=handler.redirect_request(request,None,302,'',{},URL)
        self.assertEqual(request.get_method(),'HEAD')
        with self.assertRaises(ValueError): handler.redirect_request(request,None,302,'',{},URL)
        with self.assertRaises(ValueError): handler.redirect_request(urllib.request.Request(URL),None,302,'',{},'https://example.com/a.osm.pbf')
    def test_expired_and_unvalidated(self):
        self.plan['checked_at']=int(time.time())-601
        with self.assertRaises(ValueError): self.fetch(Response())
        self.plan['checked_at']=int(time.time()); self.plan['etag']=''; self.plan['modified']=''
        with self.assertRaises(ValueError): self.fetch(Response())
    def test_changed_size_and_limit(self):
        with self.assertRaises(ValueError): self.fetch(Response(size='8'))
        self.plan['bytes']=None
        response=Response(b'x'*(d.MAX_INPUT+1),size=None)
        with self.assertRaises(ValueError): self.fetch(response)
        self.assertFalse(self.target.exists())
    def test_real_http_truncation_and_conditional_request(self):
        observed=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                observed.append(self.headers.get('If-Match'))
                self.send_response(200); self.send_header('Content-Length','7'); self.send_header('ETag','"one"'); self.end_headers()
                self.wfile.write(b'bad')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            def opener(url,method,headers):
                response=urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}/',headers=headers),timeout=2)
                response.geturl=lambda: URL
                return response
            with self.assertRaises(ValueError): d.download(self.plan,self.part,self.target,lambda *a: None,opener)
            self.assertEqual(observed,['"one"']);self.assertFalse(self.target.exists())
        finally: server.shutdown();server.server_close();thread.join()

if __name__=='__main__': unittest.main()
