# app.py
import streamlit as st
import json, zipfile, tempfile
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, box
from shapely.ops import unary_union, transform
from pyproj import Transformer

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
TARGET_KM2 = 5000
WGS84 = "EPSG:4326"
EA = "EPSG:6933"  # Equal Area

to_ea = Transformer.from_crs(WGS84, EA, always_xy=True).transform
to_wgs = Transformer.from_crs(EA, WGS84, always_xy=True).transform

st.set_page_config(layout="wide")
st.title("🗺️ GeoJSON Area Splitter (5000 km²)")

# -------------------------------------------------
# RECURSIVE SPLIT
# -------------------------------------------------
def split_polygon(poly, max_area):

    if poly.area <= max_area:
        return [poly]

    minx, miny, maxx, maxy = poly.bounds
    w = maxx - minx
    h = maxy - miny

    results = []

    if w >= h:
        mid = minx + w / 2
        left_box  = box(minx, miny, mid, maxy)
        right_box = box(mid, miny, maxx, maxy)
        parts = [poly.intersection(left_box),
                 poly.intersection(right_box)]
    else:
        mid = miny + h / 2
        bot_box = box(minx, miny, maxx, mid)
        top_box = box(minx, mid, maxx, maxy)
        parts = [poly.intersection(bot_box),
                 poly.intersection(top_box)]

    for p in parts:
        if p.is_empty:
            continue
        if isinstance(p, MultiPolygon):
            for g in p.geoms:
                results.extend(split_polygon(g, max_area))
        else:
            results.extend(split_polygon(p, max_area))

    return results

# -------------------------------------------------
# MAIN PROCESS
# -------------------------------------------------
def process(data):

    geoms = [shape(f["geometry"]) for f in data["features"]]

    merged = unary_union(geoms).buffer(0)

    merged_ea = transform(to_ea, merged)

    pieces_ea = split_polygon(
        merged_ea,
        TARGET_KM2 * 1_000_000
    )

    pieces = [transform(to_wgs, p) for p in pieces_ea]

    return pieces

# -------------------------------------------------
# PREVIEW MAP
# -------------------------------------------------
def leaflet(polys):

    fc = {
        "type":"FeatureCollection",
        "features":[
            {"type":"Feature","geometry":mapping(p),"properties":{}}
            for p in polys
        ]
    }

    bounds = unary_union(polys).bounds
    cx = (bounds[0] + bounds[2]) / 2
    cy = (bounds[1] + bounds[3]) / 2

    return f"""
<!DOCTYPE html>
<html>
<head>
<link rel="stylesheet"
href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
<div id="map" style="height:600px;"></div>
<script>
var map = L.map('map').setView([{cy},{cx}],6);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
var geo = {json.dumps(fc)};
L.geoJSON(geo,{{
 color:'red', weight:2, fillOpacity:0.3
}}).addTo(map);
</script>
</body>
</html>
"""

# -------------------------------------------------
# UI
# -------------------------------------------------
file = st.file_uploader("Upload GeoJSON", type=["geojson","json"])

if file:
    data = json.load(file)

    if st.button("Split 5000 km²"):
        polys = process(data)

        st.success(f"Generated {len(polys)} polygons")

        st.components.v1.html(leaflet(polys), height=620)

        tmp = tempfile.NamedTemporaryFile(delete=False)
        with zipfile.ZipFile(tmp.name,"w") as z:
            for i,p in enumerate(polys):
                fc = {
                    "type":"FeatureCollection",
                    "features":[
                        {"type":"Feature",
                         "geometry":mapping(p),
                         "properties":{}}
                    ]
                }
                z.writestr(f"area_{i+1}.geojson", json.dumps(fc))

        with open(tmp.name,"rb") as f:
            st.download_button(
                "⬇ Download ZIP",
                f.read(),
                "split_5000km2.zip"
            )
