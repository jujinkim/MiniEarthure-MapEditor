"""Configure live recipe-driven vegetation for the compact practice map.

MapKit owns candidate generation, density, thinning, terrain anchoring and
clearance. This authoring step declares inputs; it never keeps a target count,
replays an old tree snapshot, or relocates rejected candidates.
"""
import math
from city_assets import tree, TREE_CANOPY_WIDTH_M


def configure_vegetation(t):
    name = tree(t)
    t.doc['recipe_version'] = 7
    for zone in t.doc['zones']:
        # The map defines polygons, exclusions and 700/800 per-mille density.
        # Spacing uses metres appropriate to the shared 3.25 m city model.
        zone['spacing_cm'] = max(300, zone['spacing_cm'])
        zone['tree'] = dict(asset_id=name,
                            radius_cm=math.ceil(TREE_CANOPY_WIDTH_M*100/2),
                            clearance_cm=5)
