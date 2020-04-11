import requests
import pandas
import secrets

SODA_BASE = 'https://data.ny.gov/resource/9a8c-vfzj.json'
SODA_KEY = secrets.SODA_KEY_ID

in_city = '$where=County in(New York, Kings, Queens, Bronx, Richmond)'

markets_in_city =
