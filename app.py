# streamlit_osm_qc_dashboard.py
import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
from shapely import wkt

st.set_page_config(page_title="OSM Quality Dashboard", layout="wide")

st.title("OSM Quality Dashboard - Live QC (PostPass)")

# -----------------------------
# HOT Tasking Manager Stats
# -----------------------------
st.header("HOT Tasking Manager Project Stats")

tm_project_id = st.text_input("Enter HOT TM Project ID:", "36537")

if tm_project_id:
    try:
        tm_url = f"https://tasking-manager-tm4-production-api.hotosm.org/api/v2/projects/{tm_project_id}/statistics/"
        resp = requests.get(tm_url)
        resp.raise_for_status()
        tm_data = resp.json()

        st.metric("Total Mappers", tm_data["total_mappers"])
        st.metric("Total Tasks Mapped", tm_data["tasks_mapped"])
        st.metric("Total Validators", tm_data["tasks_validated"])

        # Active mappers table
        users = pd.DataFrame(tm_data["mappers"])
        if not users.empty:
            st.subheader("Active Mappers (Top 50)")
            st.dataframe(users[["username", "tasks_mapped"]].head(50))
    except Exception as e:
        st.error(f"Failed to fetch HOT TM stats: {e}")

# -----------------------------
# PostPass QC
# -----------------------------
st.header("PostPass Live QC")

st.markdown("""
Enter a **bounding box** in WGS84 (lon/lat) for QC. Example:
- min_lon: 103.6
- min_lat: 1.3
- max_lon: 104.0
- max_lat: 1.6
""")

col1, col2, col3, col4 = st.columns(4)
min_lon = col1.number_input("min_lon", value=103.6, format="%.6f")
min_lat = col2.number_input("min_lat", value=1.3, format="%.6f")
max_lon = col3.number_input("max_lon", value=104.0, format="%.6f")
max_lat = col4.number_input("max_lat", value=1.6)

bbox_sql = f"ST_MakeEnvelope({min_lon},{min_lat},{max_lon},{max_lat},4326)"

POSTPASS_URL = "https://postpass.geofabrik.de/api/0.2/interpreter"

def run_postpass(query):
    try:
        resp = requests.post(POSTPASS_URL, data={"data": query})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

if st.button("Run QC"):
    qc_queries = {
        "Invalid Buildings": f"""
            SELECT id, ST_AsText(geom) AS wkt_geom, ST_IsValidReason(geom) AS reason
            FROM postpass_polygon
            WHERE tags ? 'building'
              AND NOT ST_IsValid(geom)
              AND geom && {bbox_sql}
            LIMIT 50
        """,
        "Overlapping Buildings": f"""
            SELECT a.id AS b1, b.id AS b2, ST_AsText(a.geom) AS wkt_a, ST_AsText(b.geom) AS wkt_b
            FROM postpass_polygon a
            JOIN postpass_polygon b
              ON ST_Intersects(a.geom, b.geom)
            WHERE a.tags ? 'building'
              AND b.tags ? 'building'
              AND a.id < b.id
              AND a.geom && {bbox_sql}
            LIMIT 50
        """,
        "Small Buildings (<5m²)": f"""
            SELECT id, ST_AsText(geom) AS wkt_geom, ST_Area(geom::geography) AS area_m2
            FROM postpass_polygon
            WHERE tags ? 'building'
              AND ST_Area(geom::geography) < 5
              AND geom && {bbox_sql}
            LIMIT 50
        """
    }

    for title, sql in qc_queries.items():
        st.subheader(title)
        result = run_postpass(sql)
        if "error" in result:
            st.error(f"Failed to fetch data: {result['error']}")
        elif isinstance(result, list) and len(result) == 0:
            st.info("No issues found.")
        else:
            df = pd.DataFrame(result)
            st.dataframe(df)
            # Map visualization for geometries
            if 'wkt_geom' in df.columns:
                df['coordinates'] = df['wkt_geom'].apply(lambda x: list(wkt.loads(x).centroid.coords)[0])
                df[['lon','lat']] = pd.DataFrame(df['coordinates'].tolist(), index=df.index)
                st.pydeck_chart(pdk.Deck(
                    map_style='mapbox://styles/mapbox/light-v10',
                    initial_view_state=pdk.ViewState(
                        latitude=(min_lat+max_lat)/2,
                        longitude=(min_lon+max_lon)/2,
                        zoom=12
                    ),
                    layers=[pdk.Layer(
                        "ScatterplotLayer",
                        data=df,
                        get_position='[lon, lat]',
                        get_color='[200, 30, 0, 160]',
                        get_radius=10,
                    )]
                ))
