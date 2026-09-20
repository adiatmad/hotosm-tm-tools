# HOTOSM Tasking Manager Tools

A Streamlit utility for splitting uploaded GeoJSON geometry into polygons with a target maximum area of 5,000 km².

## What it does

The application:

1. accepts a GeoJSON or JSON upload;
2. merges the input feature geometries;
3. reprojects the merged geometry to an equal-area CRS (EPSG:6933);
4. recursively splits the geometry using axis-aligned cut lines until pieces are at or below the 5,000 km² target;
5. previews the resulting polygons on a Leaflet map;
6. packages the resulting GeoJSON polygons into a ZIP download.

## Requirements

Python 3 and the packages listed in `requirements.txt`.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Notes

The configured target is 5,000 km². The output is generated from the union of the uploaded geometries, so inspect the result before using it for a Tasking Manager workflow.

## License

See [LICENSE](LICENSE).
