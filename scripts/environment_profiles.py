"""Current Editor-only environment composition profiles, actual metres (MIT)."""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class DistrictRule:
    id: str
    landuse: str
    anchor: tuple
    radii: tuple
    groups: tuple
    density: tuple = (.65, 1.0)
    core: bool = True


@dataclass(frozen=True)
class FacilityRule:
    id: str
    landuse: str
    objects: tuple
    area_m2: tuple = (900, 6400)
    entrance: str = "road-facing"
    access: bool = True
    adjacent: tuple = ()
    forbidden: tuple = ("water", "protected", "carriageway")
    density: tuple = (1, 4)
    dimensions_m: tuple = (8, 30)
    surface: str = "grass"


@dataclass(frozen=True)
class ThemeProfile:
    id: str
    name: str
    english: str
    minimum_size_m: tuple
    rules: tuple
    natural_assets: tuple
    road_spacing_m: int
    relief_m: float
    ground_color: tuple
    urban: bool = False
    districts: tuple = ()
    road_mode: str = "hierarchy"
    core_land_fraction: tuple = (.20, .35)
    natural_minimum: float = 0.0
    habitats: tuple = ("grove", "meadow", "edge")
    access_count: int = 3
    # Silhouette/roof/height combinations cycle by frontage, independently of
    # density. Required assemblies and open-space reservations never scale away.
    assemblies: tuple = ()


def rule(key, use, assets=(), **kwargs):
    return FacilityRule(key, use, tuple(assets), **kwargs)


PROFILES = {p.id: p for p in [
    ThemeProfile("village", "마을 드라이빙 파크", "Village Driving Park", (1120,960), (
        rule("centre","commercial",["richer-shop-0","richer-bench"],adjacent=("shops","community"),surface="concrete"),
        rule("housing","residential",["richer-house-0","richer-house-1","richer-house-2"],adjacent=("school",)),
        rule("school","public",["arcade-school","richer-bench"],area_m2=(2400,10000)),
        rule("shops","commercial",["richer-shop-1","richer-shop-2"],surface="concrete"),
        rule("community","public",["richer-courtyard-1","richer-bench"]),
        rule("farmstead","farmland",["richer-farm-0","richer-shed-0"],adjacent=("fields","farm-lane")),
        rule("fields","farmland",["richer-crop-1","richer-crop-2"],area_m2=(3600,14400),surface="dirt"),
        rule("farm-lane","farmland",["richer-farm-2"],surface="dirt"),
        rule("irrigation","water",[],access=False),
        rule("park","park",["richer-canopy-0","richer-bench"])),
        ("environment-canopy-oak","environment-canopy-birch"),160,7,(117,148,86)),
    ThemeProfile("neon-harbor", "네온 항만", "Neon Harbor", (1920,1280), (
        rule("docks","industrial",["richer-dock-crane","richer-container"],surface="concrete",adjacent=("loading","warehouse")),
        rule("loading","industrial",["richer-container","richer-lamp"],surface="concrete"),
        rule("warehouse","industrial",["richer-shed-2","richer-shed-3"],surface="concrete",adjacent=("loading","logistics")),
        rule("container-yard","industrial",["richer-container"]*4,surface="concrete"),
        rule("logistics","industrial",["richer-shed-1"],surface="asphalt"),
        rule("housing","residential",["richer-house-3","richer-tower-0"]),
        rule("commercial","commercial",["richer-shop-2","richer-tower-1"],surface="concrete"),
        rule("waterfront","park",["richer-bench","richer-lamp"],surface="concrete"),
        rule("bridge","transport",[],surface="concrete")),
        ("richer-canopy-1",),220,5,(78,94,103),True),
    ThemeProfile("deep-forest", "깊은 숲", "Deep Forest", (1760,1760), (
        rule("canopy","forest",["environment-canopy-oak","environment-canopy-birch","arcade-pine"],access=False),
        rule("shrubs","scrub",["richer-grove-0"],access=False),
        rule("understory","grassland",["richer-grove-1"],access=False),
        rule("forest-floor","forest",[],surface="dirt",access=False),
        rule("rocks","bare_rock",["richer-rock-0","richer-rock-2"],access=False,surface="gravel"),
        rule("streams-lake","water",[],access=False),
        rule("forest-road","transport",[],surface="dirt"),
        rule("campground","recreation_ground",["richer-bench","richer-nord-0"],surface="dirt"),
        rule("ranger-station","public",["richer-nord-1","richer-shed-0"])),
        ("environment-canopy-oak","environment-canopy-birch","environment-canopy-oak","arcade-pine"),240,38,(65,101,62)),
    ThemeProfile("red-canyon", "붉은 협곡", "Red Canyon", (2400,1200), (
        rule("ridges","bare_rock",["environment-butte"],access=False,surface="gravel"),
        rule("cliffs","bare_rock",["environment-strata","environment-butte"],access=False,surface="gravel"),
        rule("strata","bare_rock",["environment-strata"],access=False,surface="dirt"),
        rule("scree","bare_rock",["richer-rock-0","richer-rock-1"],access=False,surface="gravel"),
        rule("dry-river","bare_rock",[],surface="dirt",access=False),
        rule("quarry","industrial",["richer-shed-2","richer-container"],surface="gravel",area_m2=(3600,14400)),
        rule("access-road","transport",[],surface="gravel"),
        rule("overlook","recreation_ground",["richer-bench","richer-shop-0"],surface="gravel")),
        ("richer-rock-0","richer-rock-1","environment-strata","environment-butte"),260,85,(170,76,42)),
    ThemeProfile("snow-mountain", "설산", "Snow Mountain", (1600,2080), (
        rule("ridge","bare_rock",["richer-rock-2"],access=False,surface="gravel"),
        rule("valley","grassland",[],access=False),
        rule("altitude-vegetation","forest",["arcade-pine"],access=False),
        rule("bedrock","bare_rock",["richer-rock-1"],access=False,surface="gravel"),
        rule("snowfield","bare_rock",[],access=False),
        rule("lodge-village","residential",["richer-nord-0","richer-nord-2"],adjacent=("parking",)),
        rule("parking","transport",["richer-lamp"],surface="asphalt"),
        rule("mountain-road","transport",[],surface="asphalt"),
        rule("guard-facilities","public",["richer-shed-0","richer-lamp"],surface="gravel")),
        ("arcade-pine","richer-rock-1"),240,160,(217,228,232)),
    ThemeProfile("machine-factory", "기계 공장", "Machine Factory", (1440,1440), (
        rule("production","industrial",["richer-shed-3","arcade-pipe-gantry"],surface="concrete",adjacent=("warehouse","loading")),
        rule("warehouse","industrial",["richer-shed-2"],surface="concrete",adjacent=("loading",)),
        rule("loading","industrial",["richer-container"]*3,surface="concrete"),
        rule("pipes","industrial",["arcade-pipe-gantry"]*2,surface="concrete"),
        rule("tanks","industrial",["arcade-tank"]*2,surface="concrete"),
        rule("power","industrial",["environment-transformer","richer-shed-1"],surface="concrete"),
        rule("administration","commercial",["richer-shop-3"],surface="concrete"),
        rule("parking","transport",["richer-lamp"],surface="asphalt"),
        rule("work-road","transport",[],surface="asphalt"),
        rule("fence","industrial",["environment-fence"],surface="gravel")),
        ("richer-canopy-0",),180,4,(115,120,116),True),
    ThemeProfile("sky-park", "공중 놀이공원", "Sky Amusement Park", (1920,1600), (
        rule("entrance","commercial",["richer-shop-0","richer-lamp"],surface="concrete",adjacent=("plaza",)),
        rule("plaza","recreation_ground",["richer-bench"],surface="concrete",area_m2=(2400,10000)),
        rule("attractions","recreation_ground",["environment-wheel","arcade-carousel"],area_m2=(6400,14400),surface="concrete",adjacent=("queues",)),
        rule("queues","recreation_ground",["richer-bench","richer-lamp"],surface="concrete"),
        rule("food-services","commercial",["richer-shop-1","richer-shop-2"],surface="concrete"),
        rule("conveniences","public",["richer-courtyard-0"],surface="concrete"),
        rule("management","industrial",["richer-shed-0"],surface="concrete"),
        rule("elevated-walkways","transport",[],surface="concrete"),
        rule("supports","industrial",["environment-pier"],surface="concrete")),
        ("richer-canopy-0","richer-canopy-2"),220,12,(109,145,82),True),
]}


def district(key, use, anchor, radii, groups, density=(.65, 1.0), core=True):
    return DistrictRule(key, use, anchor, radii, tuple(groups.split()), density, core)


LAYOUTS = {
    "village": (
        district("centre", "commercial", (.43,.43), (.20,.19), "centre shops school community park"),
        district("west-homes", "residential", (.23,.60), (.13,.15), "housing"),
        district("east-homes", "residential", (.64,.60), (.13,.15), "housing"),
        district("farms", "farmland", (.33,.20), (.30,.12), "farmstead fields farm-lane", (.2,.45), False)),
    "neon-harbor": (
        district("port", "industrial", (.66,.42), (.15,.35), "docks loading warehouse container-yard logistics"),
        district("town", "residential", (.29,.37), (.14,.21), "housing"),
        district("market", "commercial", (.29,.64), (.14,.13), "commercial"),
        district("waterfront", "park", (.74,.80), (.05,.09), "waterfront", (.25,.4), False)),
    "deep-forest": (
        district("camp", "recreation_ground", (.61,.57), (.055,.055), "campground"),
        district("ranger", "public", (.30,.67), (.055,.055), "ranger-station"),
        district("grove", "forest", (.34,.30), (.18,.18), "canopy forest-floor shrubs understory rocks", (.4,1), False)),
    "red-canyon": (
        district("quarry", "industrial", (.30,.28), (.07,.09), "quarry"),
        district("overlook", "recreation_ground", (.70,.65), (.05,.06), "overlook"),
        district("strata", "bare_rock", (.66,.30), (.20,.14), "ridges cliffs strata scree dry-river", (.3,.7), False)),
    "snow-mountain": (
        district("lodges", "residential", (.38,.70), (.09,.05), "lodge-village parking"),
        district("pass", "public", (.66,.35), (.05,.06), "guard-facilities"),
        district("alpine", "bare_rock", (.38,.22), (.24,.15), "ridge valley altitude-vegetation bedrock snowfield", (.3,.7), False)),
    "machine-factory": (
        district("works", "industrial", (.56,.39), (.27,.23), "production warehouse loading pipes tanks power fence"),
        district("gate", "commercial", (.32,.64), (.16,.13), "administration parking work-road")),
    "sky-park": (
        district("gate", "commercial", (.36,.66), (.17,.12), "entrance food-services conveniences"),
        district("fair", "recreation_ground", (.53,.37), (.28,.22), "attractions queues plaza"),
        district("service", "industrial", (.75,.58), (.09,.10), "management supports", (.3,.55))),
}

for key, profile in list(PROFILES.items()):
    replacements = {
        "housing": ("environment-home-0", "environment-home-1", "environment-home-2"),
        "centre": ("environment-market-0", "richer-bench"),
        "shops": ("environment-market-1", "environment-market-2"),
        "commercial": ("environment-market-0", "environment-market-1", "environment-market-2"),
        "warehouse": ("environment-hall-0", "environment-hall-1"),
        "production": ("environment-hall-2", "environment-pipe-run"),
        "lodge-village": ("environment-lodge-0", "environment-lodge-1", "environment-lodge-2"),
        "administration": ("environment-market-2",),
        "entrance": ("environment-market-0", "richer-lamp"),
        "attractions": ("environment-wheel", "arcade-carousel", "environment-lookout"),
    }
    rules = tuple(replace(r, objects=replacements.get(r.id, r.objects)) for r in profile.rules)
    remote = key in ("deep-forest", "red-canyon", "snow-mountain")
    habitats = (("dense-woodland", "understory", "lakeshore", "clearing") if key=="deep-forest" else
                ("cliff", "scree", "dry-channel", "mesa") if key=="red-canyon" else
                ("valley-forest", "alpine-rock", "snowfield", "treeline") if key=="snow-mountain" else
                ("grove", "meadow", "edge"))
    PROFILES[key] = replace(profile, rules=rules, districts=LAYOUTS[key],
        road_mode="loop" if remote else "hierarchy", natural_minimum=.85 if remote else .65 if key=="village" else 0,
        habitats=habitats, assemblies=("road-front", "entrance", "yard", "working-access"))

# Distribution models keep roof/window/door meshes and collision declarations.
# Source assets are deliberately untouched. These factors restore useful real
# metre proportions from the earlier miniature art library.
def model_scale(asset):
    if asset.startswith("environment-"): return 1.0
    if any(word in asset for word in ("house", "shop", "farm", "nord", "courtyard", "stilt")): return 2.5
    if "shed" in asset: return 3.0
    if "tower" in asset: return 2.5
    if "school" in asset: return 3.0
    if "container" in asset: return 2.5
    if "crane" in asset: return 3.0
    if "canopy" in asset or "pine" in asset: return 2.0
    if "grove-2" in asset: return 2.0
    if "grove" in asset: return 0.45
    if "rock" in asset: return 3.0
    if "wheel" in asset: return 2.5
    return 1.0
