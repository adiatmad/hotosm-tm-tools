# ============================================================
# HOT TM AREA SPLITTER - FINAL STABLE VERSION
# ============================================================
# - Equal-area recursive polygon split
# - Target block size ~5000 km²
# - Leaflet preview
# - ZIP download output
# ============================================================

import streamlit as st
import json, zipfile, traceback
from io import BytesIO

from shapely.geometry import shape, mapping, Polygon, MultiPolygon, box
from shapely.ops import unary_union, transform
from pyproj import Transformer, CRS

import folium
from streamlit_folium import st_folium

# ============================================================
# CONFIG
# ============================================================

st.set_page_config(page_title="HOT TM Area Splitter", layout="wide")

DEFAULT_TARGET = 5000.0

EA_CRS = CRS.from_epsg(6933)   # Equal Area
WGS84 = CRS.from_epsg(4326)

to_ea = Transformer.from_crs(WGS84, EA_CRS, always_xy=True).transform
to_wgs = Transformer.from_crs(EA_CRS, WGS84, always_xy=True).transform

# ============================================================
# UI
# ============================================================

st.title("🗺️ HOT TM Area Splitter (5000 km² Blocks)")

uploaded = st.file_uploader("Upload GeoJSON", type=["geojson","json"])
target_km2 = st.number_input(
    "Target area per polygon (km²)",
    value=DEFAULT_TARGET,
    min_value=100.0
)

run = st.button("Process")

# ============================================================
# HELPERS
# ============================================================

def split_recursive(poly, max_area_m2, depth=0, max_depth=12):

    # stop if close enough
    if poly.area <= max_area_m2 * 1.05:
        return [poly]

    # safety stop
    if depth >= max_depth:
        return [poly]

    minx, miny, maxx, maxy = poly.bounds
    w = maxx - minx
    h = maxy - miny

    if w >= h:
        mid = (minx + maxx) / 2
        b1 = box(minx, miny, mid, maxy)
        b2 = box(mid, miny, maxx, maxy)
    else:
        mid = (miny + maxy) / 2
        b1 = box(minx, miny, maxx, mid)
        b2 = box(minx, mid, maxx, maxy)

    parts = []
    for p in [poly.intersection(b1), poly.intersection(b2)]:
        if not p.is_empty and p.area > 1:
            parts.extend(
                split_recursive(p, max_area_m2, depth+1, max_depth)
            )

    return parts

def extract_coords(geom):
    coords=[]
    if geom["type"]=="Polygon":
        coords.extend(geom["coordinates"][0])
    elif geom["type"]=="MultiPolygon":
        for p in geom["coordinates"]:
            coords.extend(p[0])
    return coords

# ============================================================
# MAIN PROCESS
# ============================================================

def process(data, target_km2):

    shapes = [shape(f["geometry"]) for f in data["features"]]
    merged = unary_union(shapes)

    if isinstance(merged, Polygon):
        merged = [merged]
    else:
        merged = list(merged.geoms)

    target_m2 = target_km2 * 1_000_000
    final_parts = []

    for g in merged:
        g_ea = transform(to_ea, g)
        pieces = split_recursive(g_ea, target_m2)
        final_parts.extend(pieces)

    return {
        "type":"FeatureCollection",
        "features":[
            {"type":"Feature","properties":{},
             "geometry":mapping(transform(to_wgs,p))}
            for p in final_parts
        ]
    }

# ============================================================
# MAP PREVIEW
# ============================================================

def show_map(fc):

    coords=[]
    for f in fc["features"]:
        coords.extend(extract_coords(f["geometry"]))

    if coords:
        lats=[c[1] for c in coords]
        lons=[c[0] for c in coords]
        center=[sum(lats)/len(lats), sum(lons)/len(lons)]
    else:
        center=[0,0]

    m=folium.Map(location=center, zoom_start=9)

    folium.GeoJson(
        fc,
        style_function=lambda x:{
            "fillColor":"#3388ff",
            "color":"black",
            "weight":1,
            "fillOpacity":0.4
        }
    ).add_to(m)

    return m

# ============================================================
# RUN
# ============================================================

if run and uploaded:

    try:
        data=json.load(uploaded)

        with st.spinner("Processing polygons..."):
            result=process(data, target_km2)

        st.success(f"Generated {len(result['features'])} polygons")

        st.subheader("Preview")
        m=show_map(result)
        st_folium(m, width=900, height=500)

        buf=BytesIO()
        with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr(
                "area_blocks.geojson",
                json.dumps(result)
            )

        st.download_button(
            "⬇️ Download ZIP",
            buf.getvalue(),
            "hot_tm_blocks.zip",
            "application/zip"
        )

    except Exception as e:
        st.error(str(e))
        st.text(traceback.format_exc())
