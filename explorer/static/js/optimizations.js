// optimizations.js

// Initialize search with autocomplete (only if jQuery UI is loaded)
$(document).ready(function () {
  // Guard: solo inicializar autocomplete si jQuery UI está disponible
  if (typeof $.fn.autocomplete === 'function') {
  $("#search-places").autocomplete({
    source: function (request, response) {
      $.ajax({
          url: "/api/lugares/autocompletar/",
        dataType: "json",
        data: { term: request.term },
        success: function (data) {
          response(
            $.map(data, function (item) {
              return {
                label: item.label,
                value: item.label,
                slug: item.slug,
              };
            })
          );
        },
      });
    },
    minLength: 2,
    select: function (event, ui) {
      if (ui.item.slug) {
        window.location.href = "/lugar/" + ui.item.slug + "/";
      }
    },
  });
  }

  // Smooth scroll for anchor links
  $('a[href^="#"]').on("click", function (e) {
    e.preventDefault();
    const target = $(this.getAttribute("href"));
    if (target.length) {
      $("html, body").animate(
        {
          scrollTop: target.offset().top - 80, // Ajustar por altura de navbar fijo
        },
        800
      );
    }
  });
});

// Modal de imagen ampliada para detalles de lugar
const galleryItems = document.querySelectorAll(".gallery-item");
const modalImage = document.getElementById("modalImage");

galleryItems.forEach((item) => {
  item.addEventListener("click", function (e) {
    e.preventDefault();
    const imgSrc = this.getAttribute("data-src");
    modalImage.src = imgSrc;
  });
});

// Modal de fotos de reseñas
const reviewPhotoItems = document.querySelectorAll(".review-photo-item");
const reviewModalImage = document.getElementById("reviewModalImage");

reviewPhotoItems.forEach((item) => {
  item.addEventListener("click", function (e) {
    e.preventDefault();
    const imgSrc = this.getAttribute("data-src");
    reviewModalImage.src = imgSrc;
  });
});

// Compartir por WhatsApp
window.compartirWhatsApp = function () {
  const url = window.location.href;
  const title = "{{ lugar.nombre }}"; // Necesitará ser pasado desde el contexto o ser global
  const whatsappUrl = `https://wa.me/?text=${encodeURIComponent(
    title + " - " + url
  )}`;
  window.open(whatsappUrl, "_blank");
};

// Copiar enlace
window.copiarEnlace = function () {
  const url = window.location.href;
  navigator.clipboard
    .writeText(url)
    .then(() => {
      alert("Enlace copiado al portapapeles");
    })
    .catch((err) => {
      console.error("Error al copiar: ", err);
    });
};
