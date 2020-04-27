# NYC-Food-Access

#### Kyle Slugg

This repository maps access to fresh food across New York City, in relation to
prominent markers of socioeconomic (dis)advantage at the Census Tract level,
using data from OpenStreetMap, OpenRouteService, and U.S. Census Bureau
American Community Survey 5-Year Estimates of the 2014--2018 vintage.
Information on process can be found in Jupyter notebooks in the "Notebooks" folder.

The following packages must be installed to pull, process, and map these data:

- numpy
- pandas
- geopandas
- folium
- flask

Keys to the following APIs should be supplied in a document entitled
"secrets.py," using the included "secrets_template.py" template.

- Census API Key: Obtain at https://api.census.gov/data/key_signup.html
- OpenRouteService API Key: Sign up for an account at
  https://openrouteservice.org/dev/#/signup, and obtain key on "Dashboard"

When ready, please run "RUN_ME.py" to begin pulling and mapping data. If data
have already been obtained, you may choose at startup to refresh data or use
existing files; if no data have been obtained, either option will pull data.

_Please note that, due to rate limiting, retrieving isochrones from the
OpenRouteService API will take **at least 10 minutes** upon the initial run.
Information on your progress is printed to the terminal._
