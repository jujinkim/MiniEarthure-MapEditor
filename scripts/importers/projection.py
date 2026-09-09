"""Explicit, offline WGS84/UTM to local-cm adapter, outside generation contracts."""
import math
from import_layer import number


class Coordinates:
    def __init__(self, options=None):
        options = {"mode": "local-metres"} if options is None else options
        if not isinstance(options, dict): raise ValueError("coordinate options must be an object")
        self.mode = options.get("mode")
        if self.mode == "local-metres":
            if set(options) != {"mode"}: raise ValueError("local coordinates have no projection options")
            self.metadata = {"mode": self.mode, "quantization_cm": 1}
            return
        if self.mode != "wgs84-utm" or set(options) != {"mode", "origin", "local_origin_m"}:
            raise ValueError("select local-metres or explicit WGS84 origin/local origin")
        origin, local = options["origin"], options["local_origin_m"]
        if not isinstance(origin,list) or len(origin)!=2 or not isinstance(local,list) or len(local)!=2:
            raise ValueError("origin and local origin require two coordinates")
        self.lon = number(origin[0], "origin longitude", -180, 180)
        self.lat = number(origin[1], "origin latitude", -80, 84)
        self.local = [number(n,"local origin") for n in local]
        self.zone = min(60, math.floor((self.lon + 180) / 6) + 1)
        self.south = self.lat < 0
        self.epsg = (32700 if self.south else 32600) + self.zone
        try:
            import pyproj
        except ImportError as exc:
            raise ValueError("WGS84 requires pyproj 3.7.2 in the selected Python; install requirements-import.txt or choose local metres") from exc
        if pyproj.__version__ != "3.7.2":
            raise ValueError("WGS84 adapter requires pyproj 3.7.2; install requirements-import.txt")
        # No remote grids, datum approximation, axis inference or arbitrary CRS code.
        pyproj.network.set_network_enabled(False)
        self.transformer = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{self.epsg}", always_xy=True, allow_ballpark=False, only_best=True)
        self.origin_xy = self.transformer.transform(self.lon, self.lat, errcheck=True)
        self.metadata = {"mode": self.mode, "source_crs": "EPSG:4326", "target_crs": f"EPSG:{self.epsg}",
            "axis_order": "longitude-latitude", "origin": [self.lon,self.lat], "local_origin_m": self.local,
            "quantization_cm": 1, "max_radius_m": 20000, "pyproj": pyproj.__version__, "proj": pyproj.proj_version_str}

    def point(self, raw):
        if not isinstance(raw,list) or len(raw)!=2:
            raise ValueError("expected exactly two coordinates; Z is not silently discarded")
        if self.mode == "local-metres":
            return [round(number(raw[0],"x")*100), round(number(raw[1],"y")*100)]
        lon, lat = number(raw[0],"longitude",-180,180), number(raw[1],"latitude",-80,84)
        west = -180 + (self.zone-1)*6
        if not west <= lon <= west+6 or (lat < 0) != self.south:
            raise ValueError("source crosses selected UTM strip/hemisphere; split the area explicitly")
        x,y = self.transformer.transform(lon,lat,errcheck=True)
        dx,dy = x-self.origin_xy[0], y-self.origin_xy[1]
        if math.hypot(dx,dy)>20000:
            raise ValueError("source exceeds 20 km from projection origin; split area explicitly")
        return [round(number(dx+self.local[0],"projected x")*100), round(number(dy+self.local[1],"projected y")*100)]
