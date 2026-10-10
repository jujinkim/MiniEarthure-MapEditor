import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
from facility_csv import convert

class Facilities(unittest.TestCase):
    def options(self):
        return dict(encoding="utf-8-sig", name_column="이름", latitude_column="위도", longitude_column="경도",
                    category="작은도서관", source_url="https://example.org/synthetic", bounds_cm=[0,0,102400,102400], source_denominator=8)

    def convert(self, raw, options=None):
        return convert(raw,"synthetic.csv","CC0-1.0","unknown","a"*32,
            dict(mode="wgs84-utm",origin=[9,55],local_origin_m=[4096,4096]), options or self.options())

    def test_korean_encodings_mapping_scale_and_invalid_rows(self):
        value='이름,위도,경도\n"작은, 도서관",55,9\n없음,,\n잘못됨,91,9\n밖,55.09,9\n'
        for encoding in ["utf-8-sig","cp949","euc-kr"]:
            raw=value.encode(encoding); before=bytes(raw); options=self.options(); options['encoding']=encoding
            layer=self.convert(raw,options)
            self.assertEqual(raw,before)
            self.assertEqual(layer.patches[0]['after']['name'],'작은, 도서관')
            self.assertEqual(layer.patches[0]['after']['position'],[51200,51200])
            self.assertEqual(layer.feature_count,1)
            self.assertEqual(len(layer.coordinates['csv']['rejected']),2)
            self.assertEqual(layer.coordinates['csv']['outside'],[5])
            self.assertIn('"height": "unspecified"',layer.patches[0]['after']['source']['notice'])
            layer.encode()

    def test_malformed_headers_encoding_and_mapping_fail_closed(self):
        for raw in [b'', b'name,name\nx,y\n', '이름,위도,경도\n"unterminated'.encode()]:
            with self.assertRaises(ValueError): self.convert(raw)
        with self.assertRaisesRegex(ValueError,'encoding'): self.convert('이름,위도,경도\n책,55,9'.encode('cp949'))
        options=self.options(); options['latitude_column']='이름'
        with self.assertRaisesRegex(ValueError,'distinct'): self.convert('이름,위도,경도\n책,55,9'.encode(),options)

    def test_no_guessed_missing_or_nonfinite_coordinates(self):
        for value in ['', 'nan', 'inf', 'not a coordinate']:
            with self.assertRaisesRegex(ValueError,'no valid facilities'):
                self.convert(f'이름,위도,경도\n책,{value},9'.encode())

    def test_same_source_new_namespace_and_no_double_scale(self):
        raw='이름,위도,경도\n책,55,9'.encode()
        layer=self.convert(raw)
        source=copy.deepcopy(layer.patches)
        self.assertEqual(self.convert(raw).encode(),layer.encode())
        self.assertEqual(layer.patches,source)
        options=self.options(); options['source_denominator']=1; options['bounds_cm']=[0,0,500000,500000]
        self.assertEqual(self.convert(raw,options).patches[0]['after']['position'],[409600,409600])

    def test_geographic_crop_filters_before_projecting_distant_rows(self):
        options=self.options(); options['geographic_bbox']=[8.999,54.999,9.001,55.001]
        layer=self.convert('이름,위도,경도\n안,55,9\n밖,55.002,9\n먼,37,127'.encode(),options)
        self.assertEqual(layer.feature_count,1)
        self.assertEqual(layer.coordinates['csv']['outside'],[3,4])
        self.assertEqual(layer.coordinates['csv']['rejected'],[])

if __name__ == '__main__': unittest.main()
