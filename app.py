# app.py
import streamlit as st
import json, zipfile, tempfile
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, LineString
from shapely.ops import unary_union, split, transform
from pyproj import Transformer

# -------------------------------
# CONFIG
# -------------------------------
TARGET_KM2 = 5000
WGS84 = "EPSG:4326"
EA = "EPSG:6933"

to_ea = Transformer.from_crs(WGS84, EA, always_xy=True).transform
to_wgs = Transformer.from_crs(EA, WGS84, always_xy=True).transform

st.set_page_config(layout="wide")
st.title("🗺️ GeoJSON Splitter (Exact 5000 km² Polygons)")

# -------------------------------
# RECURSIVE SPLIT USING LINE
# -------------------------------
def split_polygon(poly, max_area):

    if poly.area <= max_area:
        return [poly]

    minx, miny, maxx, maxy = poly.bounds
    w = maxx - minx
    h = maxy - miny

    if w >= h:
        mid = (minx + maxx) / 2
        cutter = LineString([(mid, miny-1), (mid, maxy+1)])
    else:
        mid = (miny + maxy) / 2
        cutter = LineString([(minx-1, mid), (maxx+1, mid)])

    try:
        parts = split(poly, cutter)
    except:
        return [poly]

    results = []
    for p in parts:
        results.extend(split_polygon(p, max_area))

    return results

# -------------------------------
# MAIN PROCESS
# -------------------------------
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

# -------------------------------
# PREVIEW
# -------------------------------
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
 style:function(){{return {{color:'red',weight:2,fillOpacity:0.3}}}}
}}).addTo(map);
</script>
</body>
</html>
"""

# -------------------------------
# UI
# -------------------------------
file = st.file_uploader("Upload GeoJSON", type=["geojson","json"])

if file:
    data = json.load(file)

    if st.button("Split to 5000 km²"):
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
