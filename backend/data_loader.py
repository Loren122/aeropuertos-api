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
        airports.insert_many(data)
        for airport in data:
            redis_geo.geoadd(
                'airports_geo',
                airport['location']['coordinates'][0],
                airport['location']['coordinates'][1],
                airport['iata_code']
            )
    print("Datos iniciales cargados.")