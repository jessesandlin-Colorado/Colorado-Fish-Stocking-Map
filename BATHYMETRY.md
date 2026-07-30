# Bathymetry data

COFish currently includes an optional pilot layer for **Blue Mesa Reservoir**.
It is derived from the U.S. Bureau of Reclamation's 2019 reservoir survey
raster and displayed as 25-foot depth contours.

Depths are measured below Reclamation's published 7,519-foot full-pool
elevation. They are historical planning information, not current water depth
and not a substitute for navigation charts or on-the-water observations.

## Sources

- [Reclamation reservoir survey catalog](https://www.usbr.gov/tsc/techreferences/reservoir.html)
- [Blue Mesa 2019 GIS surface](https://www.usbr.gov/tsc/techreferences/reservoir/BlueMesaReservoir2019GISSurface.tif.zip)
- [Blue Mesa Reservoir location and full-pool elevation](https://data.usbr.gov/location/1533)

## Rebuilding the web layer

The generated GeoJSON is committed so visitors do not download the roughly
81 MB source archive. Rebuilding it requires Python plus `rasterio`,
`contourpy`, `shapely`, and `pyproj`:

```sh
python scripts/build_bathymetry.py \
  /path/to/bm2_rpvd_2019.tif \
  data/bathymetry/blue-mesa-2019.geojson
```
