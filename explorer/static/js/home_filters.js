// Búsqueda semántica para la barra del home
(function() {
	function ejecutarBusquedaSemantica(texto) {
		if (!texto || texto.length < 2) return;
		var loading = document.getElementById('ajax-loading');
		var results = document.getElementById('ajax-results');
		if (loading) loading.style.display = 'block';
		if (results) results.style.display = 'none';

		var xhr = new XMLHttpRequest();
		xhr.open('GET', '/api/semantic-search/?q=' + encodeURIComponent(texto) + '&top=12', true);
		xhr.onreadystatechange = function() {
			if (xhr.readyState === 4) {
				if (loading) loading.style.display = 'none';
				if (xhr.status === 200) {
					try {
						var data = JSON.parse(xhr.responseText);
						renderizarResultadosSemanticos(data);
					} catch (e) {
						mostrarError('Respuesta inválida del servidor');
					}
				} else {
					mostrarError('Error de conexión: ' + xhr.status);
				}
			}
		};
		xhr.send();
	}

	function renderizarResultadosSemanticos(data) {
		var results = document.getElementById('ajax-results');
		if (!results) return;
		var html = '';
		html += '<div class="container py-5">';
		html += '  <div class="text-center mb-5 text-white">';
		html += '    <h2 class="fw-bold">Resultados Semánticos</h2>';
		html += '    <p class="lead">Consulta: ' + (data.query || '') + '</p>';
		html += '  </div>';
		html += '  <div class="row g-4">';
		(data.lugares || []).forEach(function(lugar) {
			html += '    <div class="col-md-4">';
			html += '      <div class="card h-100 shadow-sm border-0 rounded-4">';
			html +=          (lugar.imagen ? ('<img src="' + lugar.imagen + '" class="card-img-top rounded-top-4" alt="' + (lugar.nombre || '') + '" style="height: 200px; object-fit: cover;" loading="lazy">') : ('<div class="bg-light d-flex align-items-center justify-content-center rounded-top-4" style="height: 200px;"><i class="bi bi-image text-muted fs-2"></i></div>'));
			html += '        <div class="card-body d-flex flex-column">';
			html += '          <h5 class="card-title fw-semibold mb-2">' + (lugar.nombre || '') + '</h5>';
			// Badges de estado como en "cerca de mí"
			html += '          <div class="mb-3">';
			html += lugar.es_destacado ? '<span class="badge bg-warning text-dark me-1"><i class="bi bi-star-fill me-1"></i>Destacado</span>' : '';
			html += lugar.es_exclusivo ? '<span class="badge bg-success me-1"><i class="bi bi-gem me-1"></i>Exclusivo</span>' : '';
			html += (lugar.rating >= 4.5 ? '<span class="badge bg-info text-dark"><i class="bi bi-award me-1"></i>Top Valorado</span>' : '');
			html += '          </div>';
			// Rating y tipo similares
			html += (typeof lugar.rating === 'number' ? '<div class="small text-muted mb-2"><i class="bi bi-star-fill text-warning me-1"></i><span class="fw-semibold">' + lugar.rating + '</span> / 5 ' + (lugar.total_reviews ? ('<span class="ms-1">(' + lugar.total_reviews + ' reseñas)</span>') : '') + '</div>' : '');
			html += '          <div class="small text-muted mb-2">' + (lugar.tipo || '') + '</div>';
			if (lugar.direccion) {
				html += '      <div class="small text-muted mb-3"><i class="bi bi-map me-1"></i>' + lugar.direccion + '</div>';
			}
			html +=          (lugar.url ? ('<a href="' + lugar.url + '" class="btn btn-gradient-purple mt-auto w-100 rounded-pill"><i class="bi bi-eye me-1"></i>Ver detalles</a>') : ('<span class="btn btn-outline-secondary disabled mt-auto w-100 rounded-pill">Sin detalles</span>'));
			html += '        </div>';
			html += '      </div>';
			html += '    </div>';
		});
		html += '  </div>';
		html += '</div>';
		results.innerHTML = html;
		results.style.display = 'block';
		try { window.scrollTo({ top: results.getBoundingClientRect().top + window.scrollY - 100, behavior: 'smooth' }); } catch(_) {}
	}

	function mostrarError(mensaje) {
		var results = document.getElementById('ajax-results');
		if (!results) return;
		results.innerHTML = '<div class="container py-5"><div class="text-center text-white"><i class="bi bi-exclamation-triangle fs-1 text-warning mb-3"></i><h3>¡Ups! Algo salió mal</h3><p class="lead">' + mensaje + '</p></div></div>';
		results.style.display = 'block';
	}

	document.addEventListener('DOMContentLoaded', function() {
		var input = document.getElementById('search-places');
		var button = document.querySelector('.search-modern-clean button');
		if (input) {
			input.addEventListener('keydown', function(e) {
				if (e.key === 'Enter') {
					e.preventDefault();
					ejecutarBusquedaSemantica(input.value.trim());
				}
			});
		}
		if (button && input) {
			button.addEventListener('click', function() {
				ejecutarBusquedaSemantica(input.value.trim());
			});
		}
	});
})(); 