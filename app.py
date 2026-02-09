# hot_tm_pro_plus.py
import streamlit as st
import json, math, random, datetime, zipfile, os, traceback
from io import BytesIO
from concurrent.futures import ProcessPoolExecutor, as_completed

from shapely.geometry import shape, mapping, Polygon, MultiPolygon, box
from shapely.ops import unary_union, transform
import shapely.ops

from pyproj import CRS, Transformer

# ============================================================
# CONFIG
# ============================================================
st.set_page_config(layout="wide", page_title="HOT TM Optimizer PRO+")
MAX_WORKERS = max(1, (os.cpu_count() or 2) - 1)

# ============================================================
# UI
# ============================================================
st.title("🚀 HOT Tasking Manager GeoJSON Optimizer — PRO+")

col_left, col_right = st.columns([2,1])
with col_left:
    uploaded_file = st.file_uploader("Upload GeoJSON", type=["geojson","json"])
    show_preview = st.checkbox("Show Leaflet preview", True)
    explain_mode = st.checkbox("Explain mode", False)

with col_right:
    target_size_mb = st.number_input("Target max file size (MB)", 0.1, value=1.0)
    max_area_km2 = st.number_input("Max area per FILE (km²)", 1.0, value=5000.0)
    split_threshold_km2 = st.number_input("Split polygon if larger than (km²)", 1.0, value=5000.0)
    approx_points = st.number_input("Approx points per polygon", 50, value=200)
    pro_zoom = st.slider("Tile export zoom", 6, 16, 10)
    run_button = st.button("Process")

# ============================================================
# EQUAL AREA
# ============================================================
EA_CRS = CRS.from_epsg(6933)
WGS84 = CRS.from_epsg(4326)
TRANSFORMER = Transformer.from_crs(WGS84, EA_CRS, always_xy=True)

def area_m2(geom):
    g = geom if not isinstance(geom, dict) else shape(geom)
    g2 = transform(TRANSFORMER.transform, g)
    return g2.area

# ============================================================
# SPLIT POLYGON BY AREA
# ============================================================
def split_polygon(poly, max_area_m2):
    if area_m2(poly) <= max_area_m2:
        return [poly]

    minx,miny,maxx,maxy = poly.bounds
    size = math.sqrt(max_area_m2)
    step = size / 111000.0

    pieces=[]
    x=minx
    while x<maxx:
        y=miny
        while y<maxy:
            cell = box(x,y,x+step,y+step)
            inter = poly.intersection(cell)
            if not inter.is_empty:
                if isinstance(inter, Polygon):
                    pieces.append(inter)
                else:
                    pieces.extend(list(inter.geoms))
            y+=step
        x+=step
    return pieces

# ============================================================
# GROUP BY AREA PER FILE
# ============================================================
def group_by_quota(features, max_km2):
    limit = max_km2 * 1_000_000
    groups=[]
    curr=[]
    total=0

    for f in features:
        a = area_m2(f)
        if a>limit:
            if curr:
                groups.append(curr)
                curr=[]; total=0
            groups.append([f])
            continue
        if total+a<=limit:
            curr.append(f)
            total+=a
        else:
            groups.append(curr)
            curr=[f]; total=a
    if curr:
        groups.append(curr)
    return groups

# ============================================================
# MAIN PROCESS
# ============================================================
def main_process(data):
    feats=[shape(f["geometry"]) for f in data["features"]]

    st.info("Unioning...")
    merged = unary_union(feats)
    polys=list(merged.geoms) if isinstance(merged,MultiPolygon) else [merged]

    st.info("Splitting large polygons...")
    split_polys=[]
    for p in polys:
        split_polys.extend(split_polygon(p, split_threshold_km2*1_000_000))

    st.info("Grouping by 5000 km² per file...")
    groups = group_by_quota(split_polys, max_area_km2)

    timestamp=datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    base=f"hot_tm_{timestamp}"
    buf=BytesIO()

    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
        for i,g in enumerate(groups,1):
            fc={
                "type":"FeatureCollection",
                "features":[{"type":"Feature","properties":{}, "geometry":mapping(p)} for p in g]
            }
            zf.writestr(f"{base}_area_group_{i}.geojson",
                        json.dumps(fc,separators=(",",":")))

    buf.seek(0)
    return buf, f"{base}.zip", len(groups)

# ============================================================
# UI TRIGGER
# ============================================================
if run_button:
    if not uploaded_file:
        st.error("Upload GeoJSON first.")
    else:
        data=json.load(uploaded_file)
        with st.spinner("Processing..."):
            buf,name,count = main_process(data)
        st.success(f"Done. Created {count} area-based files.")
        st.download_button("Download ZIP", buf.getvalue(), name)
