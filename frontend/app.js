const map = L.map('map').setView([40.0, -100.0], 4);
const backendUrl = 'http://localhost:5000';

// Capa base
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap'
}).addTo(map);

// Clúster de marcadores
const markers = L.markerClusterGroup();

// Cargar aeropuertos
fetch(`${backendUrl}/airports`)
    .then(res => res.json())
    .then(data => {
        data.forEach(airport => {
            if (!airport.location || !airport.location.coordinates) {
                console.warn(`Aeropuerto sin coordenadas: ${airport.name}`);
                return;
            }

            const [lng, lat] = airport.location.coordinates;

            const marker = L.marker([lat, lng]);

            const airportCode = airport.iata_faa || airport.icao || 'N/A';

            const identifier = airport.iata_faa || airport.icao;

            marker.bindPopup(`
                <b>${airport.name}</b><br>
                ${airportCode ? `Código: ${airportCode}<br>` : ''}
                ${airport.city}, ${airport.country}
                ${airport.alt ? `<br>Altitud: ${airport.alt} ft` : ''}
            `);

            if (identifier) {
                marker.on('click', () => {
                    fetch(`${backendUrl}/airports/${identifier}`);

                    fetch(`${backendUrl}/airports/${identifier}/click`, {
                        method: 'POST'
                    });
                });
            }

            markers.addLayer(marker);
        });
        map.addLayer(markers);
    })
    .catch(error => {
        console.error('Error cargando aeropuertos:', error);
    });