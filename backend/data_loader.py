from pymongo import MongoClient
import redis
import json
import os

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://mongo:27017')
REDIS_GEO_HOST = os.getenv('REDIS_GEO_HOST', 'redis-geo')

mongo_client = MongoClient(MONGO_URI)
db = mongo_client.airport_db
airports = db.airports

redis_geo = redis.Redis(host=REDIS_GEO_HOST, port=6379, db=0)

if airports.count_documents({}) == 0:
    with open('airports.json') as f:
        data = json.load(f)

        transformed_data = []
        for airport in data:
            transformed_airport = {
                'iata_code': airport['iata_faa'],
                'name': airport['name'],
                'city': airport['city'],
                'country': airport['city'].split(', ')[-1],
                'location': {
                    'type': 'Point',
                    'coordinates': [airport['lng'], airport['lat']]
                },
                'alt': airport['alt'],
                'tz': airport['tz'],
            }
            transformed_data.append(transformed_airport)
        
        airports.insert_many(transformed_data)

        for airport in transformed_data:
            for airport in transformed_data:
                redis_geo.geoadd(
                    'airports_geo',
                    airport['location']['coordinates'][0], # lng
                    airport['location']['coordinates'][1], # lat
                    airport['iata_code']
                )
    print("Datos iniciales transformados y cargados.")