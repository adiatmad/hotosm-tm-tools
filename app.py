# ============================================================
# HOT TM AREA SPLITTER (EQUAL-AREA, RECURSIVE, + LEAFLET PREVIEW)
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

EA_CRS = CRS.from_epsg(6933)      # World Cylindrical Equal Area
WGS84 = CRS.from_epsg(4326)

to_ea = Transformer.from_crs(WGS84, EA_CRS, always_xy=True).transform
to_wgs = Transformer.from_crs(EA_CRS, WGS84, always_xy=True).transform

# ============================================================
# UI
# ============================================================

st.title("🗺️ HOT TM Area Splitter (5000 km² Blocks)")

uploaded = st.file_uploader("Upload GeoJSON", type=["geojson","json"])
target_km2 = st.number_input("Target area per polygon (km²)", value=DEFAULT_TARGET)

run = st.button("Process")

# ============================================================
# HELPERS
# ============================================================

def split_recursive(poly, max_area_m2):

    if poly.area <= max_area_m2:
        return [poly]

    minx, miny, maxx, maxy = poly.bounds
    w = maxx - minx
    h = maxy - miny

    if w >= h:
        mid = (minx + maxx) / 2
        box1 = box(minx, miny, mid, maxy)
        box2 = box(mid, miny, maxx, maxy)
    else:
        mid = (miny + maxy) / 2
        box1 = box(minx, miny, maxx, mid)
        box2 = box(minx, mid, maxx, maxy)

    result = []
    for part in [poly.intersection(box1), poly.intersection(box2)]:
        if not part.is_empty:
            if isinstance(part, Polygon):
                result.extend(split_recursive(part, max_area_m2))
            elif isinstance(part, MultiPolygon):
                for g in part.geoms:
                    result.extend(split_recursive(g, max_area_m2))
    return result

# ============================================================
# MAIN LOGIC
# ============================================================

def process(data, target_km2):

    geoms = [shape(f["geometry"]) for f in data["features"]]
    merged = unary_union(geoms)

    if isinstance(merged, Polygon):
        merged = [merged]
    else:
        merged = list(merged.geoms)

    target_m2 = target_km2 * 1_000_000
    pieces = []

    for g in merged:
        ea = transform(to_ea, g)
        parts = split_recursive(ea, target_m2)
        pieces.extend(parts)

    final_polys = [transform(to_wgs, p) for p in pieces]

    return {
        "type": "FeatureCollection",
        "features": [
            {"type":"Feature","properties":{}, "geometry":mapping(p)}
            for p in final_polys
        ]
    }

# ============================================================
# LEAFLET MAP
# ============================================================

def show_map(fc):

    coords = []
    for f in fc["features"]:
        coords.extend(f["geometry"]["coordinates"][0])

    if coords:
        lats = [c[1] for c in coords]
        lons = [c[0] for c in coords]
        center = [sum(lats)/len(lats), sum(lons)/len(lons)]
    else:
        center = [0,0]

    m = folium.Map(location=center, zoom_start=9, tiles="OpenStreetMap")

    folium.GeoJson(
        fc,
        style_function=lambda x: {
            "fillColor": "#3388ff",
            "color": "black",
            "weight": 1,
            "fillOpacity": 0.4
        }
    ).add_to(m)

    return m

# ============================================================
# RUN
# ============================================================

if run and uploaded:

    try:
        data = json.load(uploaded)

        with st.spinner("Splitting polygons..."):
            result = process(data, target_km2)

        st.success(f"Generated {len(result['features'])} polygons")

        st.subheader("Preview")

        m = show_map(result)
        st_folium(m, width=900, height=500)

        buf = BytesIO()
        with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("area_blocks.geojson",
                       json.dumps(result))

        st.download_button(
            "Download GeoJSON",
            buf.getvalue(),
            "hot_tm_5000km2_blocks.zip",
            "application/zip"
        )

    except Exception as e:
        st.error(str(e))
        st.text(traceback.format_exc())
