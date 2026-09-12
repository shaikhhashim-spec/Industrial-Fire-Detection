# Third-party notices

## OSIRIS

The layer panel, status bar, keyboard-shortcut overlay and the day/night,
fire-satellite and hazard-context layers were designed after
[OSIRIS](https://github.com/simplifaisoul/osiris) (Open Source Intelligence &
Reconnaissance Integrated System). Its MIT licence is reproduced below.

```
MIT License

Copyright (c) 2026 simplifaisoul

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The globe itself follows OSIRIS's approach: [MapLibre GL JS](https://maplibre.org)
(BSD-3-Clause) in globe projection over CARTO's Dark Matter vector basemap.

## Map data and data sources

| Layer | Source | Terms |
|---|---|---|
| Hotspots | [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) VIIRS NRT (S-NPP, NOAA-20, NOAA-21), clipped to Indian state/UT boundaries | NASA open data |
| Industrial sites (why a hotspot is there) | [OpenStreetMap](https://www.openstreetmap.org/copyright) via Overpass — power plants, works, industrial sites, coal mines, kilns, flares | ODbL; attribution shown in the app |
| Thermal power stations | [WRI Global Power Plant Database v1.3](https://datasets.wri.org/dataset/globalpowerplantdatabase) | CC BY 4.0 |
| Nearest town / district | [GeoNames](https://www.geonames.org/) cities5000 + admin codes | CC BY 4.0 |
| Globe basemap | [CARTO Basemaps](https://carto.com/basemaps) (Dark Matter GL style) on [OpenStreetMap](https://www.openstreetmap.org/copyright) data | Attribution required (shown on the map); free tier covers non-commercial and low-volume use |
| Satellite imagery | [Esri World Imagery](https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9) | Attribution required (shown when the layer is on); review Esri's terms before any commercial deployment |
| Fire satellites | [CelesTrak](https://celestrak.org) GP element sets, propagated with [satellite.js](https://github.com/shashwatak/satellite-js) (MIT) | Public; please keep the 6 h browser cache — CelesTrak asks clients not to re-download the same data more than once every 2 h |
| Earthquakes | [USGS Earthquake Hazards Program](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php) M2.5+ past-week GeoJSON feed | U.S. public domain |
| Natural events | [NASA EONET v3](https://eonet.gsfc.nasa.gov/docs/v3) open events | NASA open data |
| Dashboard basemap | [Esri World Dark Gray / Light Gray Canvas](https://www.arcgis.com/home/group.html?id=702026e41f6641fb85da88efe79dc166) | Attribution required (shown on the map); used in place of CARTO's raster tiles, which now watermark keyless requests |
