# hot_tm_pro_plus.py
import streamlit as st
import json
import math
import random
import datetime
import zipfile
from io import BytesIO
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, box, Point, LineString
from shapely.ops import unary_union
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
import traceback

# ----------------------------
# CONFIG
# ----------------------------
st.set_page_config(layout="wide", page_title="HOT TM Optimizer PRO+")
MAX_WORKERS = max(1, (os.cpu_count() or 2) - 1)

# ----------------------------
# UI
# ----------------------------
st.title("🚀 HOT Tasking Manager GeoJSON Optimizer — PRO+")
st.write("Includes min-area merging (compactness-aware), adaptive <target MB>, tile export, preview, explain mode.")

col_left, col_right = st.columns([2, 1])

with col_left:
    uploaded_file = st.file_uploader("Upload GeoJSON", type=["geojson", "json"])
    show_preview = st.checkbox("Show Leaflet preview", value=True)
    explain_mode = st.checkbox("Explain mode (diagnostics + logs)", value=False)

with col_right:
    target_size_mb = st.number_input("Target max file size (MB)", min_value=0.1, value=1.0, step=0.1)
    max_area_km2 = st.number_input("Max polygon area per feature (km²) (split threshold)", min_value=1.0, value=5000.0, step=1.0)
    min_area_km2 = st.number_input("Min polygon area to keep (km²) (merge smaller)", min_value=0.01, value=0.5, step=0.01)
    compactness_threshold = st.number_input("Compactness threshold (0-1) (lower -> more sliver merge)", min_value=0.0, max_value=1.0, value=0.2, step=0.01)
    merge_islands = st.checkbox("Allow merging isolated islands by nearest neighbor fallback", value=False)
    nearest_neighbor_max_km = st.number_input("Nearest neighbor fallback max distance (km)", min_value=0.1, value=5.0, step=0.1)
    approx_points = st.number_input("Approx points per polygon (resample)", min_value=10, value=200, step=10)
    pro_zoom = st.slider("Tile export zoom (Z)", min_value=6, max_value=16, value=10)
    run_button = st.button("Process (PRO+)")

# Fun messages
fun_messages = [
    "🛰️ Tracing roads for rapid response...",
    "🚑 Mapping emergency access routes...",
    "🌧️ Outlining flood impact zones...",
    "🏥 Supporting humanitarian teams...",
    "🗺️ Splitting large areas into manageable tasks...",
    "💾 Compressing data without losing crucial detail..."
]

# ----------------------------
# GEODESIC helpers (no pyproj)
# ----------------------------
def rad(d): return d * math.pi / 180.0

def haversine_m(lon1, lat1, lon2, lat2):
    # careful arithmetic: compute step by step
    R = 6371000.0  # meters
    lat1r = rad(lat1); lat2r = rad(lat2)
    dlat = lat2r - lat1r
    dlon = rad(lon2 - lon1)
    a = math.sin(dlat/2.0)**2 + math.cos(lat1r)*math.cos(lat2r)*math.sin(dlon/2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def geodesic_area_m2(poly: Polygon) -> float:
    """
    Approximate geodesic area in m^2 using spherical approximation (OK for decisions up to ~5000 km²).
    Implementation follows the spherical excess style derived approximation used earlier; careful arithmetic applied.
    """
    coords = list(poly.exterior.coords)
    if len(coords) < 3:
        return 0.0
    R = 6371000.0
    total = 0.0
    for i in range(len(coords)-1):
        lon1, lat1 = coords[i]
        lon2, lat2 = coords[i+1]
        total += rad(lon2 - lon1) * (2 + math.sin(rad(lat1)) + math.sin(rad(lat2)))
    return abs(total * (R**2) / 2.0)

def perimeter_m(poly: Polygon) -> float:
    coords = list(poly.exterior.coords)
    per = 0.0
    for i in range(len(coords)-1):
        lon1, lat1 = coords[i]
        lon2, lat2 = coords[i+1]
        per += haversine_m(lon1, lat1, lon2, lat2)
    return per

def compactness(poly: Polygon) -> float:
    """4π·area / perimeter² in metric units. Returns 0..1-ish (1 is perfect circle)."""
    a = geodesic_area_m2(poly)
    p = perimeter_m(poly)
    if p <= 0:
        return 0.0
    return (4.0 * math.pi * a) / (p * p)

# ----------------------------
# meters <-> degrees approx helpers (local)
# ----------------------------
def meters_per_degree(lat_deg):
    lat_rad = rad(lat_deg)
    # refined approx
    m_per_deg_lat = 111132.954 - 559.822 * math.cos(2*lat_rad) + 1.175 * math.cos(4*lat_rad)
    m_per_deg_lon = (111132.954 * math.cos(lat_rad))
    return m_per_deg_lat, m_per_deg_lon

# ----------------------------
# Split by area (no pyproj) - similar to PRO
# ----------------------------
def split_by_area_no_pyproj(poly_geojson, max_area_m2):
    poly = shape(poly_geojson)
    if isinstance(poly, MultiPolygon):
        results = []
        for p in poly.geoms:
            results.extend(split_by_area_no_pyproj(mapping(p), max_area_m2))
        return results
    area_m2 = geodesic_area_m2(poly)
    if area_m2 <= max_area_m2:
        return [mapping(poly)]
    cell_m = (max_area_m2 ** 0.5)
    minx, miny, maxx, maxy = poly.bounds
    mid_lat = (miny + maxy) / 2.0
    mdeg_lat, mdeg_lon = meters_per_degree(mid_lat)
    cell_deg_lat = cell_m / mdeg_lat
    cell_deg_lon = cell_m / mdeg_lon
    pieces = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            cell = box(x, y, x + cell_deg_lon, y + cell_deg_lat)
            inter = poly.intersection(cell)
            if not inter.is_empty:
                if isinstance(inter, (Polygon, MultiPolygon)):
                    if isinstance(inter, Polygon):
                        pieces.append(mapping(inter))
                    else:
                        for g in inter.geoms:
                            pieces.append(mapping(g))
            y += cell_deg_lat
        x += cell_deg_lon
    if not pieces:
        return [mapping(poly)]
    return pieces

# ----------------------------
# Resample polygon (decimation + small simplify)
# ----------------------------
def resample_polygon_geojson(poly_geojson, approx_points):
    poly = shape(poly_geojson)
    coords = list(poly.exterior.coords)
    if len(coords) <= approx_points:
        return mapping(poly)
    step = max(1, len(coords) // approx_points)
    new_coords = coords[::step]
    if new_coords[0] != new_coords[-1]:
        new_coords.append(new_coords[0])
    new_poly = Polygon(new_coords)
    new_poly = new_poly.simplify(0.00001, preserve_topology=True)
    return mapping(new_poly)

# ----------------------------
# Tile math (slippy)
# ----------------------------
def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    xtile = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    return xtile, ytile

def tile_bounds_deg(x, y, z):
    n = 2 ** z
    lon_deg_min = x / n * 360.0 - 180.0
    lon_deg_max = (x+1) / n * 360.0 - 180.0
    def tile2lat(ty):
        n = 2.0 ** z
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ty / n)))
        return math.degrees(lat_rad)
    lat_deg_max = tile2lat(y)
    lat_deg_min = tile2lat(y+1)
    return (lon_deg_min, lat_deg_min, lon_deg_max, lat_deg_max)

# ----------------------------
# Worker for splitting + resampling (used in parallel)
# ----------------------------
def process_polygon_worker(args):
    poly_geojson, max_area_m2, approx_points, pro_zoom = args
    out = {"features": [], "diag": {}}
    try:
        pieces = split_by_area_no_pyproj(poly_geojson, max_area_m2)
        out["diag"]["pieces"] = len(pieces)
        out_features = []
        for p in pieces:
            res = resample_polygon_geojson(p, approx_points)
            out_features.append(res)
        out["features"] = out_features
    except Exception as e:
        out["error"] = str(e) + "\n" + traceback.format_exc()
    return out

# ----------------------------
# Adaptive reduction (same idea as PRO)
# ----------------------------
def geojson_bytes(obj):
    return len(json.dumps(obj, separators=(",", ":")).encode("utf-8"))

def adaptive_reduce_features(features, target_bytes, max_area_km2, approx_points, pro_zoom, explain_mode=False):
    attempt = 0
    max_attempts = 8
    curr = features
    while True:
        attempt += 1
        fc = {"type": "FeatureCollection", "features": [{"type":"Feature","properties":{},"geometry":f} for f in curr]}
        size = geojson_bytes(fc)
        if explain_mode:
            st.info(f"[Adaptive] Attempt {attempt}, size={(size/1e6):.3f} MB, features={len(curr)}")
        if size <= target_bytes or attempt >= max_attempts:
            return curr
        new_features = []
        dynamic_max_area = (max_area_km2 * 1_000_000) / (1.5 ** attempt)
        with ProcessPoolExecutor(max_workers=max(1, min(MAX_WORKERS, 6))) as ex:
            futures = []
            for f in curr:
                futures.append(ex.submit(process_polygon_worker, (f, dynamic_max_area, max(20, approx_points//(1+attempt)), pro_zoom)))
            for fut in as_completed(futures):
                res = fut.result()
                if "features" in res:
                    new_features.extend(res["features"])
                else:
                    # ignore fallback
                    pass
        curr = new_features

# ----------------------------
# Export tiles grouping
# ----------------------------
def export_tiles(features, z):
    tiles_map = {}
    for f in features:
        geom = shape(f)
        minx, miny, maxx, maxy = geom.bounds
        tx1, ty1 = lonlat_to_tile(minx, maxy, z)
        tx2, ty2 = lonlat_to_tile(maxx, miny, z)
        for tx in range(min(tx1, tx2), max(tx1, tx2)+1):
            for ty in range(min(ty1, ty2), max(ty1, ty2)+1):
                tb = tile_bounds_deg(tx, ty, z)
                tile_poly = box(tb[0], tb[1], tb[2], tb[3])
                if geom.intersects(tile_poly):
                    tiles_map.setdefault((tx,ty), []).append(mapping(geom.intersection(tile_poly)))
    tile_geojsons = {}
    for (tx,ty), feats in tiles_map.items():
        fc = {"type":"FeatureCollection", "features":[{"type":"Feature","properties":{}, "geometry":g} for g in feats]}
        tile_geojsons[(tx,ty)] = fc
    return tile_geojsons

# ----------------------------
# Preview HTML (Leaflet)
# ----------------------------
def leaflet_preview_html(features, center=None, zoom=5):
    fc = {"type":"FeatureCollection", "features":[{"type":"Feature","properties":{}, "geometry":f} for f in features]}
    fc_json = json.dumps(fc)
    if not center:
        if features:
            geom = shape(features[0])
            minx, miny, maxx, maxy = geom.bounds
            center = [(miny+maxy)/2.0, (minx+maxx)/2.0]
        else:
            center = [0,0]
    html = f"""
    <!doctype html><html><head>
    <meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    </head><body>
    <div id="map" style="width:100%;height:600px;"></div>
    <script>
      var map = L.map('map').setView([{center[0]}, {center[1]}], {zoom});
      L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{maxZoom:19}}).addTo(map);
      var geojson = {fc_json};
      L.geoJSON(geojson, {{
        style: function (feature) {{ return {{color: '#ff7800', weight:1}}; }},
      }}).addTo(map);
    </script></body></html>
    """
    return html

# ----------------------------
# NEW: Merge small polygons into neighbors (iterative)
# ----------------------------
def merge_small_polygons(polygons, min_area_m2, compactness_thresh, merge_islands_flag, nearest_neighbor_max_m, explain_mode=False):
    """
    polygons: list of shapely Polygon (not geojson)
    returns list of polygons after merging all < min_area_m2 iteratively
    Strategy:
      1) compute area & compactness
      2) sort small polygons by ascending compactness (i.e. slivers first)
      3) attempt to merge with touching neighbor (intersection/boundary touches)
      4) if none and merge_islands_flag True -> find nearest neighbor with centroid dist <= threshold
      5) merge by unary_union(small, neighbor) and replace neighbor with union
      6) repeat until no small left or iteration limit
    """
    # Convert to mutable list
    polys = list(polygons)
    iteration = 0
    max_iter = 2000
    while True:
        iteration += 1
        if iteration > max_iter:
            if explain_mode:
                st.warning("Merge loop reached iteration limit.")
            break
        # compute areas & compactness
        stats = []
        for idx, p in enumerate(polys):
            a = geodesic_area_m2(p)
            c = compactness(p)
            stats.append({"idx": idx, "area": a, "compactness": c, "poly": p})
        # find any small
        smalls = [s for s in stats if s["area"] < min_area_m2]
        if not smalls:
            break
        # sort by compactness asc (most slivery first) then by area asc
        smalls.sort(key=lambda x: (x["compactness"], x["area"]))
        merged_one = False
        for s in smalls:
            sidx = s["idx"]
            small_poly = polys[sidx]
            # find touching neighbors
            neighbors = []
            for jdx, cand in enumerate(polys):
                if jdx == sidx:
                    continue
                # use touches() or intersects (touches is stricter)
                try:
                    if small_poly.touches(cand) or small_poly.intersects(cand):
                        neighbors.append((jdx, cand))
                except Exception:
                    continue
            if neighbors:
                # choose neighbor that yields smallest perimeter increase or highest overlap
                best_jdx, best_cand = None, None
                best_score = None
                for jdx, cand in neighbors:
                    try:
                        u = unary_union([small_poly, cand])
                        # prefer union whose compactness improves or area minimal distortion
                        score = compactness(u) - compactness(cand)  # prefer higher improvement
                        if best_score is None or score > best_score:
                            best_score = score; best_jdx = jdx; best_cand = cand
                    except Exception:
                        continue
                if best_jdx is not None:
                    # perform merge
                    new_poly = unary_union([small_poly, best_cand])
                    # replace neighbor polygon with union, remove small_poly by index
                    # careful with indices: ensure sidx and best_jdx refer to current list ordering
                    # we will remove higher index first to keep indices valid
                    hi = max(sidx, best_jdx); lo = min(sidx, best_jdx)
                    # replace lo with new_poly, pop hi
                    polys[lo] = new_poly
                    polys.pop(hi)
                    merged_one = True
                    if explain_mode:
                        st.info(f"Merged small polygon (area {s['area']:.1f} m², compactness {s['compactness']:.3f}) into touching neighbor. New area {geodesic_area_m2(new_poly):.1f} m²")
                    break  # re-evaluate smalls
            else:
                # no touching neighbor; fallback to nearest neighbor if allowed
                if merge_islands_flag:
                    centroid = small_poly.representative_point()
                    cx, cy = centroid.x, centroid.y
                    best_dist = None; best_idx = None
                    for jdx, cand in enumerate(polys):
                        if jdx == sidx: continue
                        # compute centroid distance in meters
                        c2 = cand.representative_point()
                        d = haversine_m(cx, cy, c2.x, c2.y)
                        if best_dist is None or d < best_dist:
                            best_dist = d; best_idx = jdx
                    if best_dist is not None and best_dist <= nearest_neighbor_max_m:
                        # merge into best_idx
                        new_poly = unary_union([small_poly, polys[best_idx]])
                        hi = max(sidx, best_idx); lo = min(sidx, best_idx)
                        polys[lo] = new_poly
                        polys.pop(hi)
                        merged_one = True
                        if explain_mode:
                            st.info(f"Merged small isolated polygon (area {s['area']:.1f} m²) with nearest neighbor at distance {best_dist/1000:.2f} km")
                        break
                # if not allowed or no neighbor within threshold, we skip this small for now
                continue
        if not merged_one:
            # couldn't merge any small polygon (maybe islands too far and merge_islands False)
            if explain_mode:
                st.info("No further merges possible under current rules.")
            break
    return polys

# ----------------------------
# MAIN PROCESS (orchestrates everything)
# ----------------------------
def main_process(data, target_size_mb, max_area_km2, min_area_km2, compactness_thresh,
                 merge_islands_flag, nearest_neighbor_max_km, approx_points, pro_zoom, explain_mode, show_preview):
    logs = []
    try:
        features = data.get("features", [])
        if not features:
            raise ValueError("No features found in uploaded GeoJSON.")

        logs.append(random.choice(fun_messages))
        geoms = [shape(f["geometry"]) for f in features]
        polygons = [g for g in geoms if isinstance(g, (Polygon, MultiPolygon))]
        if not polygons:
            raise ValueError("No polygon geometries found.")

        logs.append("Unioning polygons...")
        unioned = unary_union(polygons)
        if isinstance(unioned, Polygon):
            unioned = MultiPolygon([unioned])

        # break union into top-level polygons list
        initial_polys = []
        for g in unioned.geoms:
            if isinstance(g, Polygon):
                initial_polys.append(g)
            elif isinstance(g, MultiPolygon):
                for sub in g.geoms:
                    initial_polys.append(sub)

        logs.append(f"Initial top-level polygons count: {len(initial_polys)}")

        # --------------------------------------
        # Step A: Merge small polygons per user rule (iterative)
        # --------------------------------------
        if min_area_km2 > 0:
            logs.append(f"Running merge_small_polygons (min_area={min_area_km2} km²)")
            min_area_m2 = min_area_km2 * 1_000_000
            nearest_neighbor_max_m = nearest_neighbor_max_km * 1000.0
            merged_polys = merge_small_polygons(initial_polys, min_area_m2, compactness_thresh, merge_islands_flag, nearest_neighbor_max_m, explain_mode=explain_mode)
            logs.append(f"After merging pass, polygons count: {len(merged_polys)}")
        else:
            merged_polys = initial_polys

        # --------------------------------------
        # Step B: Split by max area (parallel)
        # --------------------------------------
        logs.append("Splitting polygons > max area (parallel workers)...")
        input_polys_mappings = [mapping(p) for p in merged_polys]
        results_features = []
        diagnostics = []
        max_area_m2 = max_area_km2 * 1_000_000
        with ProcessPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(input_polys_mappings)))) as ex:
            futures = {ex.submit(process_polygon_worker, (p, max_area_m2, approx_points, pro_zoom)): idx for idx, p in enumerate(input_polys_mappings)}
            for fut in as_completed(futures):
                res = fut.result()
                if "error" in res:
                    logs.append(f"Worker error: {res['error']}")
                else:
                    results_features.extend(res.get("features", []))
                    diagnostics.append(res.get("diag", {}))

        logs.append(f"Pieces after splitting: {len(results_features)}")

        # --------------------------------------
        # Step C: Adaptive reduction to meet target size
        # --------------------------------------
        logs.append("Adaptive reduction to target file size...")
        target_bytes = int(target_size_mb * 1_000_000)
        final_features = adaptive_reduce_features(results_features, target_bytes, max_area_km2, approx_points, pro_zoom, explain_mode=explain_mode)
        logs.append(f"Final features count: {len(final_features)}")

        # --------------------------------------
        # Step D: Export tiles and prepare ZIP
        # --------------------------------------
        logs.append("Exporting tiles...")
        tile_geojsons = export_tiles(final_features, pro_zoom)
        logs.append(f"Tiles generated: {len(tile_geojsons)}")

        timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        base_name = f"hot_tm_pro_plus_{timestamp}"
        buffer = BytesIO()
        manifest = {"generated": timestamp, "tile_zoom": pro_zoom, "tiles_count": len(tile_geojsons), "features_count": len(final_features)}
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for (tx,ty), fc in tile_geojsons.items():
                fname = f"{base_name}_z{pro_zoom}_x{tx}_y{ty}.geojson"
                zf.writestr(fname, json.dumps(fc, separators=(",",":")))
            merged_fc = {"type":"FeatureCollection", "features":[{"type":"Feature","properties":{},"geometry":f} for f in final_features]}
            zf.writestr(f"{base_name}_merged.geojson", json.dumps(merged_fc, separators=(",",":")))
            zf.writestr("manifest.json", json.dumps(manifest, separators=(",",":")))
        buffer.seek(0)

        # preview html
        preview_html = None
        if show_preview:
            center = None
            if final_features:
                g = shape(final_features[0])
                minx, miny, maxx, maxy = g.bounds
                center = [(miny+maxy)/2.0, (minx+maxx)/2.0]
            preview_html = leaflet_preview_html(final_features, center=center, zoom=max(3, pro_zoom-2))

        return {"ok": True, "zip": buffer, "zip_name": f"{base_name}.zip", "logs": logs, "diagnostics": diagnostics, "preview_html": preview_html, "manifest": manifest}
    except Exception as e:
        return {"ok": False, "error": str(e) + "\n" + traceback.format_exc(), "logs": logs}

# ----------------------------
# UI trigger and response
# ----------------------------
if run_button:
    if not uploaded_file:
        st.error("Please upload a GeoJSON file first.")
    else:
        try:
            data = json.load(uploaded_file)
        except Exception as e:
            st.error(f"Failed to load JSON: {e}")
            data = None
        if data:
            with st.spinner("Processing (PRO+)..."):
                result = main_process(data, target_size_mb, max_area_km2, min_area_km2, compactness_threshold,
                                      merge_islands, nearest_neighbor_max_km, approx_points, pro_zoom, explain_mode, show_preview)
            if not result.get("ok"):
                st.error("Processing failed.")
                st.text(result.get("error"))
                if result.get("logs"):
                    st.write("Logs:")
                    for L in result["logs"]:
                        st.write("-", L)
            else:
                st.success("Processing completed (PRO+).")
                st.write("### Logs")
                for L in result["logs"]:
                    st.write("-", L)
                if explain_mode:
                    st.write("### Diagnostics (sample)")
                    st.json(result.get("diagnostics")[:10])
                st.download_button("Download ZIP (tiles + merged)", data=result["zip"].getvalue(), file_name=result["zip_name"], mime="application/zip")
                st.write("Manifest:")
                st.json(result["manifest"])
                if show_preview and result["preview_html"]:
                    st.write("### Preview map")
                    from streamlit.components.v1 import html
                    html(result["preview_html"], height=650)
