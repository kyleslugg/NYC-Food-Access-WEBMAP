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



def get_markets(refresh=False):
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

    with open('Geospatial_Data/markets.geojson', 'w') as file:
        json.dump(geographic_elements, file, indent=2)

    return geographic_elements


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

    new_isochrones = get_isochrones_with_cache({'type': 'FeatureCollection',
                                    'name': 'temp',
                                    'features': features_to_fetch}, layer_cache)

    layer_cache['index'] += new_isochrones['index']
    layer_cache['GeoJSON']['features'] += new_isochrones['features']

    save_cache(layer_cache, f'{layer_name}_isochrones')

    with open('Geospatial_Data/isochrones.geojson', 'w') as file:
        json.dump(layer_cache['GeoJSON'], file, indent=2)

    return layer_cache['GeoJSON']


if __name__ == '__main__':
    #Initialize Cache
    CACHE_VAR = open_cache(CACHE_PATH)

    #Fetch Markets
    markets = get_markets()

    #Fetch and Categorize Isochrones
    isochrones = refresh_isochrones(markets, 'markets')
