import Link from "next/link";
import type { Locale } from "@/lib/types";
import { aboutPath, comunaPath, homePath, placesListPath } from "@/lib/routes";

export default function Footer({ locale }: { locale: Locale }) {
  const es = locale === "es";
  const comuna = (slug: string, label: string) => (
    <li>
      <Link href={comunaPath(locale, slug)}>{label}</Link>
    </li>
  );

  return (
    <>
      <footer className="site-footer" role="contentinfo">
        <div className="site-footer__body">
          <div className="container">
            <div className="site-footer__grid">
              <div className="site-footer__col site-footer__col--brand">
                <Link href={homePath(locale)} className="site-footer__brand" aria-label="ViveMedellín — Inicio">
                  <span className="site-footer__mark" aria-hidden="true"><i className="bi bi-compass" /></span>
                  <span className="site-footer__brand-text">Vive<strong>Medellín</strong></span>
                </Link>
                <p className="site-footer__tagline">
                  {es
                    ? "Guía local de bares, restaurantes y vida nocturna en Medellín. Datos reales para explorar como un local."
                    : "Local guide to bars, restaurants and nightlife in Medellín. Real data to explore like a local."}
                </p>
                <Link href={placesListPath(locale)} className="site-footer__cta">
                  <i className="bi bi-search" aria-hidden="true" />
                  {es ? "Explorar lugares" : "Explore places"}
                </Link>
                <p className="site-footer__location">
                  <i className="bi bi-geo-alt-fill" aria-hidden="true" />
                  Medellín, Colombia
                </p>
              </div>

              <div className="site-footer__col">
                <h2 className="site-footer__col-title">{es ? "Explorar" : "Explore"}</h2>
                <ul className="site-footer__links">
                  <li><Link href={`${placesListPath(locale)}?tipo=restaurant`}>{es ? "Restaurantes" : "Restaurants"}</Link></li>
                  <li><Link href={`${placesListPath(locale)}?tipo=bar`}>{es ? "Bares" : "Bars"}</Link></li>
                  <li><Link href={`${placesListPath(locale)}?tipo=cafe`}>{es ? "Cafés" : "Cafés"}</Link></li>
                  <li><Link href={`${placesListPath(locale)}?tipo=night_club`}>{es ? "Vida nocturna" : "Nightlife"}</Link></li>
                  <li><Link href={`${placesListPath(locale)}?live_music=true`}>{es ? "Música en vivo" : "Live music"}</Link></li>
                  <li><Link href={`${placesListPath(locale)}?outdoor_seating=true`}>{es ? "Con terraza" : "Outdoor seating"}</Link></li>
                </ul>
              </div>

              <div className="site-footer__col">
                <h2 className="site-footer__col-title">{es ? "Zonas" : "Areas"}</h2>
                <ul className="site-footer__links">
                  {comuna("el-poblado", "El Poblado")}
                  {comuna("laureles-estadio", "Laureles")}
                  {comuna("envigado", "Envigado")}
                  {comuna("belen", es ? "Belén" : "Belén")}
                  {comuna("sabaneta", "Sabaneta")}
                  <li>
                    <Link href={placesListPath(locale)} className="site-footer__link-more">
                      {es ? "Ver todas" : "View all"}<i className="bi bi-arrow-right" aria-hidden="true" />
                    </Link>
                  </li>
                </ul>
              </div>

              <div className="site-footer__col">
                <h2 className="site-footer__col-title">{es ? "Empresa" : "Company"}</h2>
                <ul className="site-footer__links">
                  <li><Link href={aboutPath(locale)}>{es ? "Nosotros" : "About"}</Link></li>
                  <li><Link href="/contacto/">{es ? "Contacto" : "Contact"}</Link></li>
                  <li><Link href="/politica-de-privacidad/">{es ? "Privacidad" : "Privacy"}</Link></li>
                  <li><Link href="/terminos-y-condiciones/">{es ? "Términos" : "Terms"}</Link></li>
                </ul>
                <a href="mailto:info@vivemedellin.co" className="site-footer__email">
                  <i className="bi bi-envelope" aria-hidden="true" />
                  info@vivemedellin.co
                </a>
              </div>
            </div>
          </div>
        </div>

        <div className="site-footer__bar">
          <div className="container site-footer__bar-inner">
            <p className="site-footer__copy">© {new Date().getFullYear()} ViveMedellín</p>
            <nav className="site-footer__legal" aria-label={es ? "Enlaces legales" : "Legal links"}>
              <Link href="/politica-de-privacidad/">{es ? "Privacidad" : "Privacy"}</Link>
              <span className="site-footer__sep" aria-hidden="true">·</span>
              <Link href="/terminos-y-condiciones/">{es ? "Términos" : "Terms"}</Link>
              <span className="site-footer__sep" aria-hidden="true">·</span>
              <Link href="/contacto/">{es ? "Contacto" : "Contact"}</Link>
            </nav>
          </div>
        </div>
      </footer>
    </>
  );
}
