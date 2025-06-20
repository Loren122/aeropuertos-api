from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
import redis
import os
import json
from bson import ObjectId

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

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

    if not data.get('iata_faa') and not data.get('icao'):
        return jsonify({'error': 'Airport must have either IATA or ICAO code'}), 400

    identifier = data.get('iata_faa') or data.get('icao')
    data['identifier'] = identifier
    
    result = airports.insert_one(data)
    inserted_id = str(result.inserted_id)

    member = f"{identifier}|{inserted_id}"

    redis_geo.geoadd(
        'airports_geo',
        data['location']['coordinates'][0],
        data['location']['coordinates'][1],
        member
    )
    
    return jsonify({
        'status': 'created', 
        'id': str(result.inserted_id),
        'identifier': identifier
    }), 201

@app.route('/airports', methods=['GET'])
def get_all_airports():
    all_airports = list(airports.find({}, {
        '_id': 0,
        'name': 1,
        'city': 1,
        'country': 1,
        'location': 1,
        'alt': 1,
        'tz': 1,
        'iata_faa': 1,
        'icao': 1,
        'identifier': 1
    }))
    return jsonify(all_airports)

@app.route('/airports/<identifier>', methods=['GET'])
def get_airport(identifier):
    airport = airports.find_one({
        '$or': [
            {'iata_faa': identifier},
            {'icao': identifier},
            {'identifier': identifier}
        ]
    }, {'_id': 0})
    
    if airport:

        redis_pop.zincrby('airport_popularity', 1, airport.get('identifier', identifier))
        
        if redis_pop.ttl('airport_popularity') == -1:
            redis_pop.expire('airport_popularity', 86400)  # 24 horas
        
        return jsonify(airport)
    return jsonify({'error': 'Airport not found'}), 404

@app.route('/airports/<identifier>', methods=['PUT'])
def update_airport(identifier):
    data = request.json

    existing = airports.find_one({
        '$or': [
            {'iata_faa': identifier},
            {'icao': identifier},
            {'identifier': identifier}
        ]
    })
    
    if not existing:
        return jsonify({'error': 'Airport not found'}), 404

    new_identifier = data.get('iata_faa') or data.get('icao') or existing.get('identifier')
    data['identifier'] = new_identifier

    result = airports.update_one(
        {'_id': existing['_id']},
        {'$set': data}
    )
    
    if result.modified_count:
        old_member = f"{identifier}|{str(existing['_id'])}"
        new_member = f"{new_identifier}|{str(existing['_id'])}"
        
        redis_geo.zrem('airports_geo', old_member)
        
        redis_geo.geoadd(
            'airports_geo',
            data['location']['coordinates'][0],
            data['location']['coordinates'][1],
            new_member
        )
        
        return jsonify({'status': 'updated', 'new_identifier': new_identifier})
    
    return jsonify({'error': 'No changes made'}), 400

@app.route('/airports/<identifier>', methods=['DELETE'])
def delete_airport(identifier):
    airport = airports.find_one({
        '$or': [
            {'iata_faa': identifier},
            {'icao': identifier},
            {'identifier': identifier}
        ]
    })
    
    if airport:
        member = f"{identifier}|{str(airport['_id'])}"
        
        airports.delete_one({'_id': airport['_id']})
        
        redis_geo.zrem('airports_geo', member)
        
        redis_pop.zrem('airport_popularity', identifier)
        redis_pop.zrem('airport_popularity', airport.get('identifier', ''))
        
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
        withcoord=True
    )
    
    airports_list = []
    for result in results:
        member, distance, coords = result
        member_str = member.decode('utf-8')
        identifier, mongo_id = member_str.split('|', 1)
        
        airport = airports.find_one(
            {'_id': ObjectId(mongo_id)},
            {'_id': 0, 'name': 1, 'city': 1, 'country': 1, 'iata_faa': 1, 'icao': 1}
        )
        
        if airport:
            airports_list.append({
                'identifier': identifier,
                'name': airport.get('name'),
                'distance_km': distance,
                'coordinates': coords,
                'iata_faa': airport.get('iata_faa'),
                'icao': airport.get('icao')
            })
    
    return jsonify(airports_list)

@app.route('/airports/popular', methods=['GET'])
def popular_airports():
    results = redis_pop.zrevrange(
        'airport_popularity',
        0, 9,  # Top 10
        withscores=True
    )
    
    popular_list = []
    for res in results:
        identifier = res[0].decode('utf-8')
        visits = res[1]
        
        airport = airports.find_one(
            {'identifier': identifier},
            {'_id': 0, 'name': 1, 'city': 1, 'country': 1}
        )
        
        if airport:
            popular_list.append({
                'identifier': identifier,
                'name': airport.get('name'),
                'city': airport.get('city'),
                'country': airport.get('country'),
                'visits': int(visits)
            })
    
    return jsonify(popular_list)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)