from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
import redis
import os
import json

app = Flask(__name__)
CORS(app)

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
REDIS_GEO_HOST = os.getenv('REDIS_GEO_HOST', 'redis-geo')
REDIS_POP_HOST = os.getenv('REDIS_POP_HOST', 'redis-pop')

mongo_client = MongoClient(MONGO_URI)
db = mongo_client.airport_db
airports = db.airports

redis_geo = redis.Redis(host=REDIS_GEO_HOST, port=6379, db=0)
redis_pop = redis.Redis(host=REDIS_POP_HOST, port=6379, db=0)

# CRUD
@app.route('/airports', methods=['POST'])
def create_airport():
    data = request.json
    result = airports.insert_one(data)
    redis_geo.geoadd(
        'airports_geo',
        (
            data['location']['coordinates'][0],
            data['location']['coordinates'][1],
            data['iata_code']
        )
    )
    return jsonify({'status': 'created', 'id': str(result.inserted_id)}), 201

@app.route('/airports', methods= ['GET'])
def get_all_airports():
    all_airports = list(airports.find({}, {
        '_id': 0,
        'iata_code': 1,
        'name': 1,
        'city': 1,
        'country': 1,
        'location': 1
    }))
    return jsonify(all_airports)

@app.route('/airports/<iata_code>', methods=['GET'])
def get_airport(iata_code):
    airport = airports.find_one({'iata_code': iata_code}, {'_id': 0})
    if airport:
        redis_pop.zincrby('airport_popularity', 1, iata_code)
        if redis_pop.ttl('airport_popularity') == -1:
            redis_pop.expire('airport_popularity', 86400)  # 24 horas
        return jsonify(airport)
    return jsonify({'error': 'Airport not found'}), 404

@app.route('/airports/<iata_code>', methods=['PUT'])
def update_airport(iata_code):
    data = request.json
    result = airports.update_one({'iata_code': iata_code}, {'$set': data})
    if result.modified_count:
        if 'location' in data:
            redis_geo.geoadd(
                'airports_geo',
                (
                    data['location']['coordinates'][0],
                    data['location']['coordinates'][1],
                    iata_code
                )
            )
        return jsonify({'status': 'updated'})
    return jsonify({'error': 'Airport not found or no changes made'}), 404

@app.route('/airports/<iata_code>', methods=['DELETE'])
def delete_airport(iata_code):
    result = airports.delete_one({'iata_code': iata_code})
    if result.deleted_count:
        redis_geo.zrem('airports_geo', iata_code)
        redis_pop.zrem('airport_popularity', iata_code)
        return jsonify({'status': 'deleted'})
    return jsonify({'error': 'Airport not found'}), 404

# Consultas Geoespaciales
@app.route('/airports/nearby', methods=['GET'])
def nearby_airports():
    lat = float(request.args.get('lat'))
    lng = float(request.args.get('lng'))
    radius = float(request.args.get('radius', 100))
    results = redis_geo.georadius(
        'airports_geo',
        lng, lat,
        radius,
        unit='km',
        withdist=True,
    )
    return jsonify([
        {'iata_code': res[0].decode(), 'distance_km': res[1]}
        for res in results
    ])

@app.route('/airports/popular', methods=['GET'])
def popular_airports():
    results = redis_pop.zrevrange(
        'airport_popularity',
        0, 9, # Top 10
        withscores=True
    )
    return jsonify([
        {'iata_code': res[0].decode(), 'visits': res[1]}
        for res in results
    ])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
