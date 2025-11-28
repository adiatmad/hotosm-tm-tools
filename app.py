import streamlit as st
import requests
import pandas as pd
from streamlit_autorefresh import st_autorefresh

# --- CONFIG ---
TM_PROJECT_DEFAULT = 16441  # default HOT TM project
POSTPASS_URL = "https://postpass.geofabrik.de/api/0.2/interpreter"

# Auto-refresh every 5 minutes (300000 ms)
count = st_autorefresh(interval=300000, limit=None, key="refresh")

# --- PAGE HEADER ---
st.set_page_config(page_title="OSM Quality Dashboard", layout="wide")
st.title("🌍 OSM Quality Dashboard (Live QC)")
st.markdown(
    """
This dashboard shows **HOT Tasking Manager statistics** and **PostPass QC results**.
Enter a HOT TM Project ID or campaign hashtag to see live quality checks.
"""
)

# --- HOT TM STATS ---
tm_project = st.text_input("HOT TM Project ID (default project shown if empty):", value=str(TM_PROJECT_DEFAULT))
tm_project_id = tm_project.strip() or str(TM_PROJECT_DEFAULT)

st.subheader("📊 HOT Tasking Manager Stats")

try:
    tm_url = f"https://tasking-manager-tm4-production-api.hotosm.org/api/v2/projects/{tm_project_id}/statistics/"
    tm_resp = requests.get(tm_url)
    tm_resp.raise_for_status()
    tm_data = tm_resp.json()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Mappers", tm_data.get("total_mappers", 0))
    col2.metric("Tasks Mapped", tm_data.get("tasks_mapped", 0))
    col3.metric("Validators", tm_data.get("tasks_validated", 0))

    # Active mappers table
    mappers_df = pd.DataFrame(tm_data.get("mappers", []))
    if not mappers_df.empty:
        st.subheader("Active Mappers (Top 50)")
        st.dataframe(mappers_df[["username", "tasks_mapped"]].head(50))
    else:
        st.info("No mapper data available.")

except Exception as e:
    st.error(f"Failed to fetch HOT TM stats: {e}")

# --- POSTPASS LIVE QC ---
st.subheader("🏗️ Live QC via PostPass")

if st.button("Run Live QC"):
    campaign = tm_project_id  # use same input for campaign filtering
    st.info(f"Fetching QC for campaign/project: {campaign}")

    queries = {
        "Invalid Buildings": f"""
            SELECT id, ST_IsValidReason(geom) AS reason
            FROM postpass_polygon
            WHERE tags ? 'building'
              AND NOT ST_IsValid(geom)
              AND changeset IN (
                SELECT id FROM postpass_changeset
                WHERE tags->>'comment' ILIKE '%{campaign}%'
              )
            LIMIT 50
        """,
        "Overlapping Buildings": f"""
            SELECT a.id AS b1, b.id AS b2
            FROM postpass_polygon a
            JOIN postpass_polygon b
            ON ST_Intersects(a.geom, b.geom)
            WHERE a.tags ? 'building'
              AND b.tags ? 'building'
              AND a.id < b.id
              AND a.changeset IN (
                SELECT id FROM postpass_changeset
                WHERE tags->>'comment' ILIKE '%{campaign}%'
              )
            LIMIT 50
        """,
        "Small Buildings (<5m²)": f"""
            SELECT id, ST_Area(geom::geography) AS area_m2
            FROM postpass_polygon
            WHERE tags ? 'building'
              AND ST_Area(geom::geography) < 5
              AND changeset IN (
                SELECT id FROM postpass_changeset
                WHERE tags->>'comment' ILIKE '%{campaign}%'
              )
            LIMIT 50
        """
    }

    for title, sql in queries.items():
        try:
            resp = requests.post(POSTPASS_URL, data={"data": sql})
            if resp.status_code != 200:
                st.error(f"{title}: Failed to fetch data ({resp.status_code})")
                continue
            data = resp.json()
            st.subheader(title)
            if data:
                st.json(data)
            else:
                st.info("No results found.")
        except Exception as e:
            st.error(f"{title}: Error fetching PostPass data: {e}")

st.markdown("---")
st.markdown("Dashboard auto-refreshes every 5 minutes. 💡 Volunteers, keep mapping safely!")
