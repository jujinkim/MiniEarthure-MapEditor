"""Original synthetic COG-shaped raster. No provider data or private dependency."""
from pathlib import Path
import sys
import numpy as np
import rasterio
from rasterio.transform import Affine


def create(path, resolution=30, nodata=False, crs="EPSG:4326", shift=0, bias=0):
    size = 3600 if resolution == 30 else 1200
    rows = np.arange(size, dtype=np.float32)[:,None]
    cols = np.arange(size, dtype=np.float32)[None,:]
    heights = 100 + cols/size*100 + (1-rows/size)*200 + bias
    if nodata: heights[:] = -9999
    with rasterio.open(path,"w",driver="GTiff",width=size,height=size,count=1,dtype="float32",crs=crs,
                       transform=Affine(1/size,0,9-0.5/size+shift,0,-1/size,56+0.5/size),
                       tiled=True,blockxsize=1024,blockysize=1024,compress="deflate",predictor=3,nodata=-9999) as output:
        output.write(heights,1)


if __name__ == "__main__": create(Path(sys.argv[1]),bias=float(sys.argv[2]) if len(sys.argv)>2 else 0)
