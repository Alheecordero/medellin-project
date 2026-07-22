import Image from "next/image";
import Link from "next/link";
import type { Locale, PlaceCard } from "@/lib/types";
import { placePath } from "@/lib/routes";

export default function PlaceCardView({ place, locale }: { place: PlaceCard; locale: Locale }) {
  const href = place.url || (place.slug ? placePath(locale, place.slug) : "#");
  const img = place.imagen_miniatura || place.imagen_mediana || place.imagen;
  const rating = Number(place.rating ?? 0);

  return (
    <article className="place-card-wrapper">
      <Link href={href} className="place-card place-card--link">
        <div className="place-card__media">
          {img ? (
            <Image
              src={img}
              alt={place.nombre}
              fill
              className="place-card__img object-cover"
              sizes="(max-width: 576px) 100vw, (max-width: 992px) 50vw, 320px"
            />
          ) : (
            <div className="place-card__placeholder">📷</div>
          )}
          <div className="place-card__media-overlay" aria-hidden="true" />
          {place.comuna && (
            <div className="place-card__zone-glass">
              <span>{place.comuna}</span>
            </div>
          )}
          {rating > 0 && (
            <div className="place-card__rating">
              ★ <span>{rating.toFixed(1)}</span>
              {place.total_reviews ? <small>({place.total_reviews})</small> : null}
            </div>
          )}
        </div>
        <div className="place-card__body">
          <h3 className="place-card__title">{place.nombre}</h3>
          <div className="place-card__badges">
            <span className="place-card__badge place-card__badge--type">{place.tipo}</span>
            {place.es_destacado && <span className="place-card__badge place-card__badge--featured">Destacado</span>}
            {place.es_exclusivo && <span className="place-card__badge place-card__badge--exclusive">Exclusivo</span>}
            {rating >= 4.5 && <span className="place-card__badge place-card__badge--top-rated">Top</span>}
          </div>
          {place.direccion && (
            <div className="place-card__address">{place.direccion}</div>
          )}
          <div className="place-card__footer">
            <span className="place-card__cta-pill">
              {locale === "en" ? "View details" : "Ver detalle"} →
            </span>
          </div>
        </div>
      </Link>
    </article>
  );
}
