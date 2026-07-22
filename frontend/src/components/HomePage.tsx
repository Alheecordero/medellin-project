import Link from "next/link";
import type { Locale } from "@/lib/types";
import type { HomeResponse } from "@/lib/types";
import { comunaPath, placePath, placesListPath } from "@/lib/routes";

const copy = {
  es: {
    kicker: "La guía local para vivir Medellín",
    title: "Encuentra los mejores lugares para vivir Medellín",
    sub: "Busca restaurantes, bares, cafés, cultura y planes por zona o cerca de ti.",
    searchPh: "¿Qué buscas? Ej. bares en El Poblado",
    nearMe: "Buscar cerca de mí",
    byZone: "Explorar por zonas",
    intentions: "Explorar por intención",
    intentionsSub: "Restaurantes, bares, cafés y más en Medellín",
    seeAll: "Ver todos",
    seeAllArrow: "Ver todos →",
    zones: "Zonas populares",
    seeAllZones: "Ver todas →",
    moreZones: "+ Ver más",
    imperdibles: "Imperdibles ahora",
    exploreZones: "Explora por zonas",
    restaurants: "Restaurantes",
    bars: "Bares",
    cafes: "Cafés",
    liveMusic: "Música en vivo",
    terraces: "Terrazas",
    petFriendly: "Pet friendly",
  },
  en: {
    kicker: "The local guide to experience Medellín",
    title: "Find the best places to experience Medellín",
    sub: "Search restaurants, bars, cafés, culture and plans by area or near you.",
    searchPh: "What are you looking for? e.g. bars in El Poblado",
    nearMe: "Search near me",
    byZone: "Explore by area",
    intentions: "Explore by intent",
    intentionsSub: "Restaurants, bars, cafés and more in Medellín",
    seeAll: "View all",
    seeAllArrow: "View all →",
    zones: "Popular areas",
    seeAllZones: "View all →",
    moreZones: "+ View more",
    imperdibles: "Must-see picks",
    exploreZones: "Explore by area",
    restaurants: "Restaurants",
    bars: "Bars",
    cafes: "Cafés",
    liveMusic: "Live music",
    terraces: "Terraces",
    petFriendly: "Pet friendly",
  },
};

const intentions = [
  { href: (l: Locale) => `${placesListPath(l)}?tipo=restaurant`, icon: "bi-egg-fried", labelKey: "restaurants" as const },
  { href: (l: Locale) => `${placesListPath(l)}?tipo=bar`, icon: "bi-cup-straw", labelKey: "bars" as const },
  { href: (l: Locale) => `${placesListPath(l)}?tipo=cafe`, icon: "bi-cup-hot", labelKey: "cafes" as const },
  { href: (l: Locale) => `${placesListPath(l)}?live_music=true`, icon: "bi-music-note-beamed", labelKey: "liveMusic" as const },
  { href: (l: Locale) => `${placesListPath(l)}?outdoor_seating=true`, icon: "bi-umbrella", labelKey: "terraces" as const },
  { href: (l: Locale) => `${placesListPath(l)}?allows_dogs=true`, icon: "bi-heart", labelKey: "petFriendly" as const },
];

export default function HomePage({ data, locale }: { data: HomeResponse; locale: Locale }) {
  const t = copy[locale];
  const chips = data.filtros.comunas_medellin_chips.slice(0, 8);
  const zoneCards = data.filtros.comunas_medellin_chips.slice(0, 6);

  return (
    <div className="home-page">
      <section className="hero-v3">
        <div className="hero-v3__bg" aria-hidden="true">
          <img src="/img/hero-medellin.jpg" alt="" className="hero-v3__bg-img" fetchPriority="high" />
          <div className="hero-v3__overlay" />
        </div>
        <div className="container hero-v3__body">
          <div className="hero-v3__content">
            <div className="home-kicker-v3">{t.kicker}</div>
            <h1 className="hero-v3__title">{t.title}</h1>
            <p className="hero-v3__sub">{t.sub}</p>
            <div className="hero-v3__search d-none d-md-block">
              <div className="search-bar-v3">
                <i className="bi bi-search search-bar-v3__icon" />
                <input type="text" className="search-bar-v3__input" placeholder={t.searchPh} aria-label={t.searchPh} />
                <button className="search-bar-v3__btn" type="button" aria-label={t.seeAll}>
                  <i className="bi bi-search" />
                </button>
              </div>
            </div>
            <div className="hero-v3__ctas">
              <button id="cerca-de-mi-btn" className="btn-hero-primary" type="button">
                <i className="bi bi-geo-fill" id="ubicacion-icon" />
                <span id="ubicacion-text">{t.nearMe}</span>
              </button>
              <Link href={placesListPath(locale)} className="btn-hero-secondary">
                <i className="bi bi-map" />{t.byZone}
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="intentions-section">
        <div className="container">
          <div className="intentions-panel">
            <div className="section-row-v2 intentions-panel__head">
              <div>
                <span className="section-row-v2__label">{t.intentions}</span>
                <p className="intentions-panel__sub">{t.intentionsSub}</p>
              </div>
              <Link href={placesListPath(locale)} className="section-row-v2__link">{t.seeAllArrow}</Link>
            </div>
            <div className="intentions-grid" aria-label={t.intentions}>
              {intentions.map((item) => (
                <Link key={item.labelKey} href={item.href(locale)} className="intention-chip">
                  <span className="intention-chip__icon"><i className={`bi ${item.icon}`} /></span>
                  <span className="intention-chip__label">{t[item.labelKey]}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      {chips.length > 0 && (
        <section className="zonas-pills-section">
          <div className="container">
            <div className="section-row-v2 mb-3">
              <span className="section-row-v2__label">{t.zones}</span>
              <Link href={placesListPath(locale)} className="section-row-v2__link">{t.seeAllZones}</Link>
            </div>
            <div className="zonas-pills-row">
              {chips.map((area) => (
                <Link key={area.slug} href={comunaPath(locale, area.slug)} className="zona-pill">
                  {area.name}
                </Link>
              ))}
              <Link href={placesListPath(locale)} className="zona-pill zona-pill--all">{t.moreZones}</Link>
            </div>
          </div>
        </section>
      )}

      {data.lugares_imperdibles.length > 0 && (
        <section className="imperdibles-section">
          <div className="container">
            <div className="section-row-v2 mb-4">
              <h2 className="section-row-v2__title">{t.imperdibles}</h2>
              <Link href={placesListPath(locale)} className="section-row-v2__link">{t.seeAllArrow}</Link>
            </div>
            <div className="imperdibles-scroll">
              {data.lugares_imperdibles.map((lugar) => (
                <Link
                  key={lugar.slug}
                  href={placePath(locale, lugar.slug)}
                  className="imp-card"
                  title={lugar.nombre}
                >
                  <div className="imp-card__img-wrap">
                    {lugar.imagen ? (
                      <img src={lugar.imagen} alt={lugar.nombre} loading="lazy" decoding="async" />
                    ) : null}
                    <div className="imp-card__placeholder" />
                    <span className="imp-card__badge">
                      <i className="bi bi-star-fill" /> {Number(lugar.rating ?? 0).toFixed(1)}
                    </span>
                  </div>
                  <div className="imp-card__body">
                    <div className="imp-card__title">{lugar.nombre}</div>
                    <div className="imp-card__meta">
                      <span className="imp-card__type">{lugar.tipo}</span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {zoneCards.length > 0 && (
        <section className="zonas-img-section">
          <div className="container">
            <div className="section-row-v2 mb-4">
              <h2 className="section-row-v2__title">{t.exploreZones}</h2>
            </div>
            <div className="zonas-img-grid">
              {zoneCards.map((area, idx) => (
                <Link
                  key={area.slug}
                  href={comunaPath(locale, area.slug)}
                  className={`zona-img-card zona-img-card--${idx + 1}`}
                >
                  <div className="zona-img-card__overlay" />
                  <div className="zona-img-card__text">
                    <span className="zona-img-card__name">{area.name}</span>
                    <span className="zona-img-card__arrow">→</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
