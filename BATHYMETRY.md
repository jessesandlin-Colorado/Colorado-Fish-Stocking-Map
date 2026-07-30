# Bathymetry data

COFish includes one optional bathymetry layer containing historical depth
contours for selected Colorado reservoirs. The source catalog in
`bathymetry-layer.js` connects eligible Fishing Atlas records to their compact
web layers.

| Water | Survey | Interval |
| --- | ---: | ---: |
| Blue Mesa Reservoir | 2019 | 25 ft |
| Navajo Reservoir | 2019 | 25 ft |
| Flatiron Reservoir | 2012 | 10 ft |
| Lake Estes | 2001 | 10 ft |
| Lake Isabel | 2012 | 10 ft |
| Pinewood Reservoir | 2012 | 10 ft |

Depths are measured below each survey's documented reference elevation. They
are historical planning information, not current water depth and not a
substitute for navigation charts or on-the-water observations.

## Sources

- [Reclamation reservoir survey catalog](https://www.usbr.gov/tsc/techreferences/reservoir.html)
- [Blue Mesa 2019 GIS surface](https://www.usbr.gov/tsc/techreferences/reservoir/BlueMesaReservoir2019GISSurface.tif.zip)
- [Blue Mesa Reservoir location and full-pool elevation](https://data.usbr.gov/location/1533)
- [Navajo Reservoir 2019 survey report](https://www.usbr.gov/tsc/techreferences/reservoir/NavajoReservoir2019SedimentationSurvey_final508VI.pdf)
- [Flatiron 2012 survey report](https://www.usbr.gov/tsc/techreferences/reservoir/Flatiron%20Reservoir%20Report%202012.pdf)
- [Lake Estes 2001 survey report](https://www.usbr.gov/tsc/techreferences/reservoir/Lake%20Estes%202001%20Survey.pdf)
- [Lake Isabel 2012 survey report](https://www.usbr.gov/tsc/techreferences/reservoir/Lake%20Isabel%20_Report_Final_online.pdf)
- [Pinewood 2012 survey report](https://www.usbr.gov/tsc/techreferences/reservoir/Pinewood%20Reservoir%20Rattlesnake%20Dam%202012%20Bathymetric%20Survey.pdf)

## Rebuilding the web layer

The generated GeoJSON is committed so visitors do not download the large
Blue Mesa and Navajo source rasters or the source File Geodatabases.
Rebuilding a raster survey requires Python plus `rasterio`, `contourpy`,
`shapely`, and `pyproj`:

```sh
python scripts/build_bathymetry.py \
  /path/to/bm2_rpvd_2019.tif \
  data/bathymetry/blue-mesa-2019.geojson
```

The File Geodatabase surveys use `scripts/build_vector_bathymetry.py`, which
requires `pyogrio`, `geopandas`, and `shapely`. Run the script with `--help`
for the source-specific datum, reference elevation, layer, and interval
arguments.
