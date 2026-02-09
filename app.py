# app.py
import streamlit as st
import json, zipfile, math, tempfile, os
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, box
from shapely.ops import unary_union, transform
from pyproj import Transformer

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
TARGET_KM2 = 5000
EA_CRS = "EPSG:6933"   # World Cylindrical Equal Area
WGS84 = "EPSG:4326"

to_ea = Transformer.from_crs(WGS84, EA_CRS, always_xy=True).transform
to_wgs = Transformer.from_crs(EA_CRS, WGS84, always_xy=True).transform

st.set_page_config(page_title="GeoJSON Area Splitter 5000 km²", layout="wide")
st.title("🗺️ GeoJSON Splitter → 5000 km² Polygons")

# --------------------------------------------------
# SPLIT RECURSIVE
# --------------------------------------------------
def split_recursive(poly, max_area):

    if poly.area <= max_area:
        return [poly]

    minx, miny, maxx, maxy = poly.bounds
    width = maxx - minx
    height = maxy - miny

    if width >= height:
        mid = minx + width/2
        cutter = box(mid, miny, mid, maxy)
    else:
        mid = miny + height/2
        cutter = box(minx, mid, maxx, mid)

    left = poly.intersection(cutter)
    right = poly.difference(cutter)

    results = []
    for part in [left, right]:
        if not part.is_empty:
            if isinstance(part, MultiPolygon):
                for g in part.geoms:
                    results.extend(split_recursive(g, max_area))
            else:
                results.extend(split_recursive(part, max_area))

    return results

# --------------------------------------------------
# MAIN PROCESS
# --------------------------------------------------
def process_geojson(data):

    geoms = [shape(f["geometry"]) for f in data["features"]]

    # 1. dissolve all
    merged = unary_union(geoms)
    merged = merged.buffer(0)

    if isinstance(merged, MultiPolygon):
        merged = unary_union(list(merged.geoms))

    # 2. project to equal-area
    merged_ea = transform(to_ea, merged)

    target_m2 = TARGET_KM2 * 1_000_000

    # 3. split
    pieces_ea = split_recursive(merged_ea, target_m2)

    # 4. back to WGS84
    pieces = [transform(to_wgs, p) for p in pieces_ea]

    return pieces

# --------------------------------------------------
# LEAFLET PREVIEW
# --------------------------------------------------
def leaflet_html(polys):

    fc = {
        "type":"FeatureCollection",
        "features":[
            {"type":"Feature","properties":{},
             "geometry":mapping(p)}
            for p in polys
        ]
    }

    center = polys[0].centroid
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
<div id="map" style="height:600px;"></div>
<script>
var map = L.map('map').setView([{center.y},{center.x}],6);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
var data = {json.dumps(fc)};
L.geoJSON(data,{style:{{color:"red",weight:2,fillOpacity:0.2}}}).addTo(map);
</script>
</body>
</html>
"""

# --------------------------------------------------
# UI
# --------------------------------------------------
file = st.file_uploader("Upload GeoJSON", type=["geojson","json"])

if file:
    data = json.load(file)

    if st.button("Split to 5000 km²"):
        polys = process_geojson(data)

        st.success(f"Generated {len(polygons:=polys)} polygons")

        # preview
        st.components.v1.html(leaflet_html(polys), height=620)

        # ZIP export
        buffer = tempfile.NamedTemporaryFile(delete=False)
        with zipfile.ZipFile(buffer.name,"w") as z:
            for i,p in enumerate(polys):
                fc = {
                    "type":"FeatureCollection",
                    "features":[
                        {"type":"Feature","properties":{},
                         "geometry":mapping(p)}
                    ]
                }
                z.writestr(f"area_{i+1}.geojson", json.dumps(fc))

        with open(buffer.name,"rb") as f:
            st.download_button(
                "⬇️ Download ZIP",
                f.read(),
                file_name="split_5000km2.zip"
            )
