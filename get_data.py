#Imports
import secrets

import pandas as pd
import geopandas as gpd
import numpy as np
import folium
from folium.plugins import MarkerCluster
from openrouteservice import client
import shapely

import requests
import json
import time
import sqlite3
from datetime import date
import math


#NOTE: Requires libspatialindex_c and rtree for geoanalysis. brew install
#spatialindex, pip3 install rtree

#Global Vars
CENSUS_KEY = secrets.CENSUS_API_KEY


ORS_KEY = secrets.ORS_API_KEY
ORS_URL = 'https://api.openrouteservice.org/v2/isochrones/foot-walking'

CACHE_PATH = './Cache/Cache.json'
CACHE_VAR = {}

overpass_url = "http://overpass-api.de/api/interpreter?"
overpass_query_markets = '''[out:json]
[timeout:25]
;
area(3600175905)->.searchArea;
(
  node
    ["shop"="supermarket"]
    (area.searchArea);
  way
    ["shop"="supermarket"]
    (area.searchArea);
  relation
    ["shop"="supermarket"]
    (area.searchArea);
  node
    ["shop"="grocery"]
    (area.searchArea);
  way
    ["shop"="grocery"]
    (area.searchArea);
  relation
    ["shop"="grocery"]
    (area.searchArea);
  node
    ["shop"="greengrocer"]
    (area.searchArea);
  way
    ["shop"="greengrocer"]
    (area.searchArea);
  relation
    ["shop"="greengrocer"]
    (area.searchArea);
);
out center;
>;
out skel qt;
'''

def open_cache(cache_path):
    '''
        Opens the cache with the file path provided as a dictionary; if no cache is present,
        creates a cache dictionary.

        Returns the resultant cache dictionary.

        Parameters
        ----------
        cache_path: str
            The path to a cache file, if such a file exists.

        Returns
        -------
        dict
            A dictionary containing cached information stored in the form of a json.
        '''
    try:
        with open(cache_path, 'r') as cache_file:
                cache = json.load(cache_file)
    except:
        cache = {}

    return cache


def save_cache(cache_data, cache_name):
    '''
        Saves a cache dictionary to the filepath provided.

        Parameters
        ----------
        cache_name: dict
            A dictionary containing cached webpage information.

        cache_path: str
            The file path where the cache is to be saved.


        Returns
        -------
        None
        '''
    if cache_name is not None and CACHE_VAR is not None:
        updated_cache = CACHE_VAR.copy()
        updated_cache[cache_name] = cache_data
    else:
        updated_cache = cache_data

    with open(CACHE_PATH, 'w') as cache_file:
        json.dump(updated_cache, cache_file, indent=2)


def construct_unique_key(params, api_url):
    '''
        Constructs a unique key for a webpage (to be used in this program's
        cache) from supplied parameters and an API URL.

        Parameters
        ----------
        params: dict
            A dictionary containing search parameters.

        api_url: string
            The location of an API. Defaults to global API_URL.


        Returns
        -------
        str
            A unique key.
        '''
    param_strings = []
    connector = '_'
    for k in params.keys():
        param_strings.append(f'{k}_{params[k]}')
    unique_key = api_url + connector + connector.join(param_strings)
    return unique_key


def call_API_with_cache(url, params, cache_name, reset_cache=False):
    '''
        Manages API calls using the provided cache of API-derived data.

        Parameters
        ----------
        url: string
            The location of a resource to be requested.

        params: dict
            A dictionary containing search parameters; defaults to None.

        cache: dict
            A dictionary containing previously obtained data.


        Returns
        -------
        dict
            The JSON returned by the API call, formatted as a dictionary.
        '''

    if reset_cache == False:
        temp_cache = CACHE_VAR.setdefault(cache_name, {})
    else:
        temp_cache = {}

    if params is not None:
        key = construct_unique_key(params, url)
    else:
        key = url

    if key in temp_cache.keys():
        print(f"Using Cache: {url}")
        content = temp_cache[key]
        return content
    else:
        print(f"Fetching: {url}")
        if params is not None:
            content = requests.get(url=url, params=params).json()
        else:
            content = requests.get(url=url).json()

        temp_cache[key] = content
        save_cache(temp_cache, cache_name)

    return content



def get_market_data(refresh=False):
    '''TODO: Docstring

    Fetches market data, saves and returns as GeoJSON'''

    geographic_elements = {'type':'FeatureCollection',
                      'name':'markets',
                      'features':[]}


    results = call_API_with_cache(url=overpass_url,
                                  params={'data':overpass_query_markets},
                                  cache_name='markets', reset_cache=refresh)

    for element in results['elements']:
        if 'tags' in element:
            geodict = {'type':'Point'}
            propdict = {'id':element['id']}

            if element['type'] == 'node' and 'tags' in element:
                lon = element['lon']
                lat = element['lat']
                geodict['coordinates'] = [lon, lat]

            elif 'center' in element:
                lon = element['center']['lon']
                lat = element['center']['lat']
                geodict['coordinates'] = [lon, lat]

            for key, value in element['tags'].items():
                propdict[key] = value

            geographic_elements['features'].append({'type':'Feature',
                                       'geometry':geodict,
                                       'properties':propdict})

    markets_data = gpd.read_file(json.dumps(geographic_elements))
    markets_data['wkb_geometry'] = markets_data['geometry'].apply(lambda item: item.wkb)
    markets_data['addr'] = markets_data.apply(lambda row: f"{row['addr:housenumber']} {row['addr:street']}, {row['addr:city']}", axis=1)
    markets_data['addr'] = markets_data['addr'].apply(lambda x: None if (str(x).find('None') != -1) else x)

    census_tracts = gpd.read_file('Geospatial_Data/NYC_Tracts.geojson').to_crs('epsg:4326')
    fields_to_keep = ['id', 'name', 'alt_name', 'addr', 'shop', 'opening_hours', 'phone', 'GEOID','wkb_geometry']

    markets_data_with_tract = gpd.sjoin(markets_data, census_tracts, how='left', op='intersects')
    markets_data_trimmed = markets_data_with_tract[fields_to_keep]

    make_markets_table(markets_data_trimmed)

    return geographic_elements




def make_markets_table(geodataframe):
    '''TODO: Docstring
    geom_column must be in wkb form'''

    conn = sqlite3.connect('Geospatial_Data/map_data.sqlite')
    conn.enable_load_extension(True)
    conn.load_extension("mod_spatialite")

    cur = conn.cursor()

    try:
        conn.execute("SELECT InitSpatialMetaData(1);")
    except:
        pass

    create_statement = '''CREATE TABLE IF NOT EXISTS "markets"(
    "feat_id" INTEGER PRIMARY KEY,
    "name" TEXT,
    "alt_name" TEXT,
    "addr" TEXT,
    "shop" TEXT,
    "opening_hours" TEXT,
    "phone" TEXT,
    "GEOID" TEXT)'''


    drop_statement = f'''DROP TABLE IF EXISTS "markets"'''

    conn.execute(drop_statement)
    conn.execute(create_statement)

    def add_row(row):
        add_statement = '''INSERT INTO markets
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''
        values = row.values.tolist()[:8]
        conn.execute(add_statement, values)

    geodataframe.apply(lambda row: add_row(row), axis=1)

    try:
        conn.execute(f"""
            SELECT AddGeometryColumn("markets", 'wkb_geometry', 4326, 'POINT', 2);
            """)
    except:
        pass

    geometry_tuples = []
    geodataframe.apply(lambda row: geometry_tuples.append((row['wkb_geometry'], row['id'])), axis=1)

    conn.executemany(
    f"""
    UPDATE markets
    SET wkb_geometry=GeomFromWKB(?, 4326)
    WHERE markets.feat_id = ?
    """, (tuple(geometry_tuples)))
    conn.commit()
    conn.close()




def divide_features(feature_df, n, geometry_col, id_col):
    '''TODO: Write Docstring'''
    ids_with_locations = {}

    feature_df['geom_reformat'] = feature_df[geometry_col].apply(lambda location: [location.x, location.y])

    df_chunks = np.array_split(feature_df[[id_col, 'geom_reformat']], math.trunc(feature_df.shape[0]/5)+1)

    for chunk in df_chunks:
        id_string = ''

        for item in chunk[id_col].tolist():
            id_string += f'{item}_'

        location_list = chunk['geom_reformat'].tolist()

        ids_with_locations[id_string] = location_list


    return ids_with_locations


def get_isochrones_with_cache(points, layer_cache):
    '''TODO: Docstring

    Returns dictionary containing an index and a list of GeoJSON Features'''

    points_data = gpd.read_file(json.dumps(points))

    segments = divide_features(points_data, 5, 'geometry', 'id')

    params = {'location_type':'destination',
              'range': [600, 420, 300], #420/60 = 7 mins
              'range_type': 'time',
              'attributes': ['area', 'reachfactor', 'total_pop'], # Get attributes for isochrones
              'smoothing': 5
             }

    header = {
        'Accept': 'application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8',
        'Authorization': ORS_KEY,
        'Content-Type': 'application/json; charset=utf-8'
    }

    isochrone_features = layer_cache['GeoJSON']['features']
    index = layer_cache['index']

    segment_number = 1
    for id_string, locations in segments.items():
        params['locations'] = locations
        params['id'] = id_string
        id_list = np.repeat(id_string.split(sep='_'), len(params['range'])).tolist()
        index += id_list

        try:
            isos = requests.post(ORS_URL, json=params, headers=header).json()

            i = 0
            for feature in isos['features']:
                feature['properties']['id'] = id_list[i]
                i += 1
                isochrone_features.append(feature)

            save_cache(layer_cache, layer_cache['GeoJSON']['name'])
            print(f"Fetched New Isochrones: Segment {segment_number} of {len(segments.keys())}")
            segment_number +=1

        except:
            print("Waiting one minute...")
            time.sleep(61)

            isos = requests.post(ORS_URL, json=params, headers=header).json()

            i = 0
            for feature in isos['features']:
                feature['properties']['id'] = id_list[i]
                i += 1
                isochrone_features.append(feature)

            save_cache(layer_cache, layer_cache['GeoJSON']['name'])
            print(f"Fetched New Isochrones: Segment {segment_number} of {len(segments.keys())}")
            segment_number +=1

    return {'index': index, 'features': isochrone_features}


def refresh_isochrones(point_feature_collection, layer_name):
    '''TODO: Docstring

    point_feature_collection: GeoJSON,
    returns GeoJSON of '''

    layer_cache = CACHE_VAR.setdefault(f'{layer_name}_isochrones', {'index':[],'GeoJSON':{
        'type': 'FeatureCollection',
        'name': f'{layer_name}_isochrones',
        'features':[]
        }
        })

    features_in_cache = []
    features_to_fetch = []

    for feature in point_feature_collection['features']:
        if str(feature['properties']['id']) in layer_cache['index']:
            features_in_cache.append(feature)
        else:
            features_to_fetch.append(feature)

    print(f'''Using {len(features_in_cache)} cached isochrones;
                Fetching {len(features_to_fetch)} new isochrones''')

    if len(features_to_fetch) >0:
        new_isochrones = get_isochrones_with_cache({'type': 'FeatureCollection',
                                        'name': 'temp',
                                        'features': features_to_fetch}, layer_cache)

        layer_cache['index'] += new_isochrones['index']
        layer_cache['GeoJSON']['features'] += new_isochrones['features']

    save_cache(layer_cache, f'{layer_name}_isochrones')

    with open('Geospatial_Data/isochrones.geojson', 'w') as file:
        json.dump(layer_cache['GeoJSON'], file, indent=2)

    return layer_cache['GeoJSON']


def make_tracts_table(geodataframe):
    '''TODO: Docstring'''

    conn = sqlite3.connect('Geospatial_Data/map_data.sqlite')
    cur = conn.cursor()

    dataframe = geodataframe.drop(columns=['geometry'])
    value_cols = [column for column in dataframe.columns.tolist() if column != 'GEOID']

    schema = '''"geoid" TEXT PRIMARY KEY UNIQUE'''

    for column in value_cols:
        schema += f''',
        "{str(column).lower()}" TEXT NOT NULL'''

    drop_statement = '''DROP TABLE IF EXISTS "tracts";'''
    create_statement = f'''CREATE TABLE IF NOT EXISTS "tracts"(
    {schema})'''

    cur.execute(drop_statement)
    cur.execute(create_statement)

    def add_to_table(row):
        add_statement = f'''INSERT INTO tracts
        VALUES (?{', ?'*(len(row.values)-1)})'''
        values = [row['GEOID']]+row[value_cols].values.tolist()
        conn.execute(add_statement, values)

    dataframe.apply(lambda row: add_to_table(row), axis=1)

    conn.commit()
    conn.close()



def get_acs_data():

    BASE_URL = 'https://api.census.gov/data/2018/acs/acs5'
    county_fips = ['081', '061', '085', '005', '047']
    state_fips = '36'
    variables = {'total_pop':'B01003_001E',
                 'white_pop':'B02001_002E',
                 'black_pop':'B02001_003E',
                 'aian_pop':'B02001_004E',
                 'asian_pop':'B02001_005E',
                 'nhpi_pop': 'B02001_006E',
                 'other_pop':'B02001_007E',
                 'two_or_more_pop':'B02001_008E',
                 'median_age':'B01002_001E',
                 'median_hh_income':'B19049_001E'
                }

    tracts_table = gpd.read_file('Geospatial_Data/NYC_Tracts_Clipped.geojson')

    for varname, variable in variables.items():
        variable_table = pd.DataFrame({f'{variable}':'Placeholder',
                                       'state':'00',
                                       'county':'000',
                                       'tract':'000000'}, index=[0])
        for county in county_fips:
            params = {'get':variable,
                      'for':'tract:*',
                      'in':[f"state:{state_fips}",f"county:{county}"],
                      'key':CENSUS_KEY
                   }

            results = call_API_with_cache(url=BASE_URL,
                                          params=params,
                                          cache_name='census')
            variable_table = variable_table.append(pd.DataFrame(results, columns=variable_table.columns).iloc[1:,0:], ignore_index=True)

        tracts_table = tracts_table.merge(variable_table,
                                          left_on=['STATEFP', 'COUNTYFP', 'TRACTCE'],
                                          right_on=['state', 'county', 'tract'],
                                          how='left').drop(columns=['state', 'county', 'tract'])

    tracts_table.to_file('Geospatial_Data/Tracts_with_Data.geojson', driver='GeoJSON')

    make_tracts_table(tracts_table)

    return tracts_table


if __name__ == '__main__':
    #Initialize Cache
    CACHE_VAR = open_cache(CACHE_PATH)

    #Fetch Markets
    markets = get_market_data()

    #Fetch and Categorize Isochrones
    isochrones = refresh_isochrones(markets, 'markets')

    #Fetch and Join Tract Data
    get_acs_data()
