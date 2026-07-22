"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { Locale } from "@/lib/types";
import { aboutPath, homePath, placesListPath, switchLocalePath } from "@/lib/routes";

const labels = {
  es: {
    menu: "Abrir menú",
    home: "Inicio",
    explore: "Explorar",
    about: "Nosotros",
    search: "Buscar lugares…",
    searchLabel: "Buscar lugares en Medellín",
    searchBtn: "Buscar",
    mobileMenu: "Menú mobile",
    nav: "Navegación principal",
  },
  en: {
    menu: "Open menu",
    home: "Home",
    explore: "Explore",
    about: "About",
    search: "Search places…",
    searchLabel: "Search places in Medellín",
    searchBtn: "Search",
    mobileMenu: "Mobile menu",
    nav: "Main navigation",
  },
};

export default function Topbar({ locale }: { locale: Locale }) {
  const t = labels[locale];
  const pathname = usePathname() || "/";
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  const isHome = pathname === homePath(locale);
  const isExplore = pathname.includes("/lugares") || pathname.includes("/places");
  const isAbout = pathname.includes("nosotros") || pathname.includes("about-us");

  return (
    <header className="site-topbar" id="site-topbar">
      <div className="site-topbar__accent" aria-hidden="true" />
      <div className="container site-topbar__inner">
        <button
          type="button"
          className={`site-topbar__burger${menuOpen ? " open" : ""}`}
          id="site-burger"
          aria-label={t.menu}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((v) => !v)}
        >
          <span /><span /><span />
        </button>

        <Link href={homePath(locale)} className="site-topbar__brand">
          Vive<strong>Medellín</strong>
        </Link>

        <nav className="site-topbar__nav" aria-label={t.nav}>
          <Link href={homePath(locale)} className={`site-topbar__link${isHome ? " active" : ""}`}>{t.home}</Link>
          <Link href={placesListPath(locale)} className={`site-topbar__link${isExplore ? " active" : ""}`}>{t.explore}</Link>
          <Link href={aboutPath(locale)} className={`site-topbar__link${isAbout ? " active" : ""}`}>{t.about}</Link>
        </nav>

        <form className="site-topbar__search d-none d-md-flex" action={placesListPath(locale)} method="get" role="search">
          <i className="bi bi-search site-topbar__search-icon" aria-hidden="true" />
          <input
            type="search"
            name="q"
            className="site-topbar__search-input"
            placeholder={t.search}
            aria-label={t.searchLabel}
            autoComplete="off"
          />
        </form>

        <div className="site-topbar__right">
          <button
            type="button"
            className={`site-topbar__search-toggle d-md-none${searchOpen ? " open" : ""}`}
            id="site-search-toggle"
            aria-label={t.search}
            aria-expanded={searchOpen}
            aria-controls="site-search-panel"
            onClick={() => setSearchOpen((v) => !v)}
          >
            <i className="bi bi-search" aria-hidden="true" />
          </button>
          <div className="site-lang-switcher">
            <Link href={switchLocalePath(pathname, "es")} className={locale === "es" ? "site-lang-switcher__btn active" : "site-lang-switcher__btn"}>ES</Link>
            <Link href={switchLocalePath(pathname, "en")} className={locale === "en" ? "site-lang-switcher__btn active" : "site-lang-switcher__btn"}>EN</Link>
          </div>
        </div>
      </div>

      {menuOpen && (
        <nav className="site-topbar__mobile-menu open" id="site-mobile-menu" aria-label={t.mobileMenu}>
          <Link href={homePath(locale)} className={`site-topbar__mobile-link${isHome ? " active" : ""}`} onClick={() => setMenuOpen(false)}>{t.home}</Link>
          <Link href={placesListPath(locale)} className={`site-topbar__mobile-link${isExplore ? " active" : ""}`} onClick={() => setMenuOpen(false)}>{t.explore}</Link>
          <Link href={aboutPath(locale)} className={`site-topbar__mobile-link${isAbout ? " active" : ""}`} onClick={() => setMenuOpen(false)}>{t.about}</Link>
        </nav>
      )}

      {!searchOpen ? null : (
        <div className="site-topbar__search-panel" id="site-search-panel">
          <div className="container">
            <form action={placesListPath(locale)} method="get" role="search">
              <div className="site-topbar__search-mobile">
                <i className="bi bi-search" aria-hidden="true" />
                <input type="search" name="q" className="site-topbar__search-input" placeholder={t.search} aria-label={t.searchLabel} />
                <button type="submit" className="site-topbar__search-submit">{t.searchBtn}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </header>
  );
}
