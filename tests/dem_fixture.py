"""Original synthetic COG-shaped raster. No provider data or private dependency."""
from pathlib import Path
import sys
import numpy as np
import rasterio
from rasterio.transform import Affine


def create(path, resolution=30, nodata=False, crs="EPSG:4326", shift=0, bias=0, tile=(9,55)):
    size = 3600 if resolution == 30 else 1200
    rows = np.arange(size, dtype=np.float32)[:,None]
    cols = np.arange(size, dtype=np.float32)[None,:]
    heights = 100 + cols/size*100 + (1-rows/size)*200 + bias + (tile[0]-9)*100 + (tile[1]-55)*200
    if nodata: heights[:] = -9999
    with rasterio.open(path,"w",driver="GTiff",width=size,height=size,count=1,dtype="float32",crs=crs,
                       transform=Affine(1/size,0,tile[0]-0.5/size+shift,0,-1/size,tile[1]+1+0.5/size),
                       tiled=True,blockxsize=1024,blockysize=1024,compress="deflate",predictor=3,nodata=-9999) as output:
        output.write(heights,1)


if __name__ == "__main__":
    if len(sys.argv)>2 and sys.argv[2]=="mosaic":
        folder=Path(sys.argv[1]);folder.mkdir(exist_ok=True)
        for tile in [(9,55),(10,55),(9,54),(10,54)]: create(folder/f"Copernicus_DSM_COG_10_N{tile[1]:02d}_00_E{tile[0]:03d}_00_DEM.tif",tile=tile)
    else: create(Path(sys.argv[1]),bias=float(sys.argv[2]) if len(sys.argv)>2 else 0)
