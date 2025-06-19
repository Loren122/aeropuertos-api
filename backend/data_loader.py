from pymongo import MongoClient
import redis
import json
import os
import logging
from pymongo.errors import DuplicateKeyError
from bson import ObjectId

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("data_loader")

# Configuración
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
REDIS_GEO_HOST = os.getenv("REDIS_GEO_HOST", "redis-geo")

# Conexiones
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.airport_db
airports = db.airports

redis_geo = redis.Redis(host=REDIS_GEO_HOST, port=6379, db=0)
airports.create_index("icao", unique=True, sparse=True)

if os.path.exists('airports.json'):
    airports.delete_many({})
    redis_geo.delete("airports_geo")
    
    with open('airports.json') as f:
        data = json.load(f)
        
        # Contadores para estadísticas
        loaded_count = 0
        skipped_count = 0
        no_identifier_count = 0
        coord_errors = 0
        geo_errors = 0
        duplicate_count = 0
        other_errors = 0
        
        for airport in data:
            identifier = airport.get("iata_faa") or airport.get("icao")
            
            if not identifier:
                logger.warning(f"Aeropuerto omitido: No tiene iata_faa ni icao - {airport['name']}")
                skipped_count += 1
                no_identifier_count += 1
                continue

            try:
                lng = float(airport["lng"])
                lat = float(airport["lat"])

                lng = round(lng, 6)
                lat = round(lat, 6)
                
                if not (-180 <= lng <= 180):
                    raise ValueError(f"Longitud {lng} fuera de rango [-180, 180]")
                
                if lat > 85.05112878:
                    logger.warning(f"Latitud ajustada para {identifier}: {lat} → 85.05112878")
                    lat = 85.05112878
                elif lat < -85.05112878:
                    logger.warning(f"Latitud ajustada para {identifier}: {lat} → -85.05112878")
                    lat = -85.05112878
                    
            except (TypeError, ValueError, KeyError) as e:
                logger.error(f"Coordenadas inválidas para {identifier}: lng={airport.get('lng')}, lat={airport.get('lat')} - {str(e)}")
                skipped_count += 1
                coord_errors += 1
                continue
            
            city_parts = airport["city"].split(", ")
            country = city_parts[-1] if len(city_parts) > 1 else "Unknown"
            
            transformed_airport = {
                "name": airport["name"],
                "city": airport["city"],
                "country": country,
                "location": {
                    "type": "Point",
                    "coordinates": [lng, lat]
                },
                "alt": airport.get("alt"),
                "tz": airport.get("tz"),
                "iata_faa": airport.get("iata_faa"),
                "icao": airport.get("icao")
            }
            
            try:
                result = airports.insert_one(transformed_airport)
                inserted_id = str(result.inserted_id)

                member = f"{identifier}|{inserted_id}"
                
                try:
                    # Versión segura para redis-py 4.x
                    added = redis_geo.geoadd(
                        "airports_geo", 
                        [(lng, lat, member)]
                    )
                    if added == 1:
                        logger.debug(f"Añadido a Redis: {member} ({lng}, {lat})")
                    else:
                        logger.warning(f"Duplicado en Redis: {member}")
                except Exception as geo_e:
                    # Fallback para versiones antiguas
                    try:
                        added = redis_geo.execute_command(
                            "GEOADD airports_geo", 
                            lng, lat, member
                        )
                        logger.debug(f"Añadido con comando directo: {member}")
                    except Exception as fallback_e:
                        logger.error(f"Error GEOADD definitivo para {identifier}: {str(fallback_e)}")
                        geo_errors += 1
                        skipped_count += 1
                        airports.delete_one({"_id": result.inserted_id})
                        continue
                
                loaded_count += 1
                
            except DuplicateKeyError:
                logger.warning(f"Duplicado omitido: {identifier} - {airport['name']}")
                skipped_count += 1
                duplicate_count += 1
            except Exception as e:
                logger.error(f"Error general para {identifier}: {str(e)}")
                skipped_count += 1
                other_errors += 1
        
        logger.info(f"Carga completada: {loaded_count} aeropuertos cargados")
        logger.info(f"Omitidos: {skipped_count} (sin identificador: {no_identifier_count}, duplicados: {duplicate_count}, coord inválidas: {coord_errors}, errores GEO: {geo_errors}, otros: {other_errors})")
        
        # Crear ZSET vacío para popularidad
        redis_pop = redis.Redis(host=os.getenv("REDIS_POP_HOST", "redis-pop"), port=6379, db=0)
        redis_pop.zadd("airport_popularity", {"init": 0})
        redis_pop.expire("airport_popularity", 86400)  # TTL de 1 día
        logger.info("Creado ZSET de popularidad en Redis")
else:
    logger.info("Archivo airports.json no encontrado. Saltando carga inicial.")