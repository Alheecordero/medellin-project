// Búsqueda semántica para la barra del home
(function() {
	function ejecutarBusquedaSemantica(texto) {
		if (!texto || texto.length < 2) return;
		var loading = document.getElementById('ajax-loading');
		var results = document.getElementById('ajax-results');
		var resultsSection = document.getElementById('search-results-section');
		if (loading) loading.style.display = 'block';
		if (results) results.style.display = 'none';
		if (resultsSection) resultsSection.style.display = 'none';

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
		html += '<div class="semantic-home-wrapper">';
		html += '  <div class="semantic-home-header text-center mb-4 text-white">';
		html += '    <h2 class="fw-bold semantic-home-title">Resultados semánticos</h2>';
		html += '    <p class="lead mb-0">Consulta: <span class="semantic-home-query">“' + (data.query || '') + '”</span></p>';
		html += '  </div>';
		html += '  <div class="semantic-home-grid">';
		(data.lugares || []).forEach(function(lugar) {
			html += '    <div class="semantic-home-item">';
			html += '      <div class="card h-100 shadow-sm border-0 rounded-4 semantic-home-card">';
			html += '        <div class="semantic-home-media position-relative">';
			if (lugar.imagen) {
				html += '          <img src="' + lugar.imagen + '" class="semantic-home-img" alt="' + (lugar.nombre || '') + '" loading="lazy">';
			} else {
				html += '          <div class="semantic-home-placeholder d-flex align-items-center justify-content-center">';
				html += '            <i class="bi bi-image text-muted fs-2"></i>';
				html += '          </div>';
			}
			if (typeof lugar.rating === 'number') {
				html += '          <div class="semantic-home-rating badge rounded-pill">';
				html += '            <i class="bi bi-star-fill me-1"></i><span class="fw-semibold">' + lugar.rating.toFixed(1) + '</span>';
				html += '          </div>';
			}
			html += '        </div>';

			html += '        <div class="card-body d-flex flex-column semantic-home-body">';
			html += '          <h5 class="card-title fw-semibold mb-2 semantic-home-title-card">' + (lugar.nombre || '') + '</h5>';

			html += '          <div class="d-flex flex-wrap align-items-center gap-2 mb-2 small">';
			if (lugar.tipo) {
				html += '            <span class="badge semantic-type-pill"><i class="bi bi-geo-alt me-1"></i>' + lugar.tipo + '</span>';
			}
			if (lugar.es_destacado) {
				html += '            <span class="badge semantic-flag-featured"><i class="bi bi-star-fill me-1"></i>Destacado</span>';
			}
			if (lugar.es_exclusivo) {
				html += '            <span class="badge semantic-flag-exclusive"><i class="bi bi-gem me-1"></i>Exclusivo</span>';
			}
			html += '          </div>';

			if (typeof lugar.rating === 'number') {
				html += '          <div class="small text-muted mb-2">';
				html += '            <i class="bi bi-star-fill text-warning me-1"></i><span class="fw-semibold">' + lugar.rating.toFixed(1) + '</span>/5';
				html += '          </div>';
			}

			if (lugar.direccion) {
				html += '          <div class="small text-muted mb-3"><i class="bi bi-map me-1"></i>' + lugar.direccion + '</div>';
			}

			if (lugar.url) {
				html += '          <a href="' + lugar.url + '" class="btn mt-auto w-100 rounded-pill semantic-home-cta"><i class="bi bi-eye me-1"></i>Ver detalles</a>';
			} else {
				html += '          <span class="btn btn-outline-secondary disabled mt-auto w-100 rounded-pill">Sin detalles</span>';
			}

			html += '        </div>';
			html += '      </div>';
			html += '    </div>';
		});
		html += '  </div>';
		html += '</div>';
		results.innerHTML = html;
		results.style.display = 'block';
		var resultsSection = document.getElementById('search-results-section');
		if (resultsSection) resultsSection.style.display = 'block';
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