# osm_qc_dashboard.py
import streamlit as st
import requests
import pandas as pd
import json

st.set_page_config(page_title="OSM Quality Dashboard", layout="wide")

st.title("OSM Quality Dashboard (Streamlit + PostPass)")
st.markdown("""
This dashboard fetches **live QC data from PostPass** for a specified bounding box.
""")

# --- User Input ---
st.sidebar.header("Bounding Box Input")
min_lon = st.sidebar.number_input("Min Longitude (x_min)", value=100.0)
min_lat = st.sidebar.number_input("Min Latitude (y_min)", value=0.0)
max_lon = st.sidebar.number_input("Max Longitude (x_max)", value=101.0)
max_lat = st.sidebar.number_input("Max Latitude (y_max)", value=1.0)

bbox = f"ST_MakeEnvelope({min_lon},{min_lat},{max_lon},{max_lat},4326)"

# --- Helper Function ---
POSTPASS_URL = "https://postpass.geofabrik.de/api/0.2/interpreter"

def run_postpass(sql: str):
    try:
        response = requests.post(POSTPASS_URL, data={"data": sql}, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        return {"error": f"HTTP Error {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        return {"error": str(e)}

# --- Queries ---
queries = {
    "Invalid Buildings": f"""
        SELECT id, ST_IsValidReason(geom) 
        FROM postpass_polygon 
        WHERE tags ? 'building' AND NOT ST_IsValid(geom)
          AND geom && {bbox}
    """,
    "Overlapping Buildings": f"""
        SELECT a.id AS b1, b.id AS b2 
        FROM postpass_polygon a 
        JOIN postpass_polygon b 
        ON ST_Intersects(a.geom, b.geom)
        WHERE a.tags ? 'building' AND b.tags ? 'building' AND a.id < b.id
          AND a.geom && {bbox} AND b.geom && {bbox}
    """,
    "Small Buildings (<5m²)": f"""
        SELECT id, ST_Area(geom::geography) AS area_m2 
        FROM postpass_polygon 
        WHERE tags ? 'building' AND ST_Area(geom::geography)<5
          AND geom && {bbox}
    """
}

# --- Execute Queries ---
st.header("Live QC Results")
for title, sql in queries.items():
    st.subheader(title)
    with st.spinner(f"Fetching {title}..."):
        result = run_postpass(sql)
        if "error" in result:
            st.error(f"Failed to fetch data: {result['error']}")
        else:
            df = pd.json_normalize(result.get("features", []))
            if df.empty:
                st.info("No issues found in this area.")
            else:
                st.dataframe(df)
                # Optional download
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=f"Download {title} as CSV",
                    data=csv,
                    file_name=f"{title.replace(' ','_')}.csv",
                    mime='text/csv'
                )
