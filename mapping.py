import folium
from folium.plugins import MarkerCluster
import geopandas as gpd
import numpy as np
from flask import Flask, render_template

def get_data():
    import get_data

def make_isochrone_layers(isochrone_data):
    _5min_isos = isochrone_data[isochrone_data['value']==300]
    _7min_isos = isochrone_data[isochrone_data['value']==420]
    _10min_isos = isochrone_data[isochrone_data['value']==600]

    _5min_layer = _5min_isos.unary_union
    #_7min_layer = gpd.overlay(_7min_isos, _5min_isos, how='difference').unary_union
    _7min_layer = _7min_isos.unary_union
    #_10min_layer = gpd.overlay(_10min_isos, _7min_isos, how='difference').unary_union
    _10min_layer = _10min_isos.unary_union

    return {'5min':_5min_layer, '7min':_7min_layer, '10min':_10min_layer}

def make_market_map(market_data, isochrone_data):

    m = folium.Map(width=730, height=500, location=[40.728783, -73.992320],
                  tiles = basemap,
                  zoom_start=11)

    #Creating Clusters of Market Locations
    market_clusters = MarkerCluster(name='Markets')
    for geom, name in zip(market_data['geometry'], market_data['name']):
        folium.Marker(location = [geom.y, geom.x],
                     popup = name,
                     icon = folium.Icon(prefix='fa', icon='apple',
                                        color='white', icon_color='red')).add_to(market_clusters)

    m.add_child(market_clusters)

    isochron_layers = folium.map.FeatureGroup(name='Walking Time')
    m.add_child(isochron_layers)

    _10min = folium.plugins.FeatureGroupSubGroup(isochron_layers, '10 min.')
    m.add_child(_10min)

    _7min = folium.plugins.FeatureGroupSubGroup(isochron_layers, '7 min.')
    m.add_child(_7min)

    _5min = folium.plugins.FeatureGroupSubGroup(isochron_layers, '5 min.')
    m.add_child(_5min)


    _10min.add_child(folium.GeoJson(isochrone_data['10min'], name='10 min.', style_function = lambda x:
                                    {'fillColor': '#FE9B5B',
                                     'fillOpacity': 0.5,
                                     'weight': 1,
                                     'color': 'black'
                                    }))
    _7min.add_child(folium.GeoJson(isochrone_data['7min'], name='7 min.', style_function = lambda x:
                                    {'fillColor': '#FEEB7D',
                                     'fillOpacity': 0.5,
                                     'weight': 1,
                                     'color': 'black'
                                    }))
    _5min.add_child(folium.GeoJson(isochrone_data['5min'], name='5 min.', style_function = lambda x:
                                    {'fillColor': '#CFFF91',
                                     'fillOpacity': 0.5,
                                     'weight': 1,
                                     'color': 'black'
                                    }))

    folium.LayerControl().add_to(m)

    return m


def make_tract_map(market_data, tract_data):
    m = folium.Map(location=[40.728783, -73.992320], tiles = basemap, zoom_start=11)

    #Creating Clusters of Market Locations
    market_clusters = MarkerCluster(name='Markets')
    for geom, name in zip(market_data['geometry'], market_data['name']):
        folium.Marker(location = [geom.y, geom.x],
                     popup = name,
                     icon = folium.Icon(prefix='fa', icon='apple',
                                        color='white', icon_color='red')).add_to(market_clusters)

    m.add_child(market_clusters)


    folium.features.Choropleth(name='Median Income',
                               geo_data='Geospatial_Data/NYC_Tracts_Clipped.geojson',
                               data=tract_data, columns=['GEOID', 'B19049_001E'],
                               key_on='feature.properties.GEOID',
                               fill_color='Greens', legend_name='Median Income ($)').add_to(m)

    folium.features.Choropleth(name='Pct. Population Nonwhite',
                               geo_data='Geospatial_Data/NYC_Tracts_Clipped.geojson',
                               data=tract_data, columns=['GEOID', 'pct_nonwhite'],
                               key_on='feature.properties.GEOID',
                               fill_color='Blues', show=False, legend_name='Pct. Nonwhite').add_to(m)

    folium.features.Choropleth(name='Median Age',
                               geo_data='Geospatial_Data/NYC_Tracts_Clipped.geojson',
                               data=tract_data, columns=['GEOID', 'B01002_001E'],
                               key_on='feature.properties.GEOID',
                               fill_color='Oranges', show=False, legend_name='Median Age').add_to(m)


    folium.LayerControl().add_to(m)

    return m


def prompt_data_refresh():
    while True:
        response = input("Obtain fresh data? Y/N")
        if response.lower() == 'y':
            get_data()
            break
        elif response.lower() == 'n':
            break
        else:
            print("Please enter 'Y' or 'N'")

    pass


if __name__ == '__main__':
    prompt_data_refresh()

    basemap = 'cartodbpositron'

    try:
        markets = gpd.read_file('Geospatial_Data/markets.geojson')
    except:
        print("No data found! Refreshing data -- please wait.")
        get_data()
        markets = gpd.read_file('Geospatial_Data/markets.geojson')

    isochrones = gpd.read_file('Geospatial_Data/isochrones.geojson')
    isochrone_data = make_isochrone_layers(isochrones)

    tracts = gpd.read_file('Geospatial_Data/Tracts_with_Data.geojson')
    tracts[tracts.columns[12:22]] = tracts[tracts.columns[12:22]].astype(float)
    tracts[tracts.columns[22]] = tracts[tracts.columns[22]]*100

    make_tract_map(markets, tracts).save('static/tracts.html')
    make_market_map(markets, isochrone_data).save('static/markets.html')

    #Flask starts here
    app = Flask(__name__)

    @app.route('/')
    def index():
        return render_template('index.html')

    app.run(debug=False)
