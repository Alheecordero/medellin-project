import SiteShell from "@/components/SiteShell";
import PlaceCardView from "@/components/PlaceCard";
import { getPlaces } from "@/lib/api";

export const revalidate = 60;

export default async function PlacesListPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const query: Record<string, string> = {};
  for (const [key, value] of Object.entries(params)) {
    if (typeof value === "string") query[key] = value;
  }
  const data = await getPlaces(query, "es");

  return (
    <SiteShell locale="es">
      <section className="section">
        <div className="section__header">
          <h2>Lugares en Medellín</h2>
          <span className="text-sm text-slate-500">{data.total} resultados</span>
        </div>
        <div className="cards-grid">
          {data.lugares.map((place) => (
            <PlaceCardView key={place.slug} place={place} locale="es" />
          ))}
        </div>
      </section>
    </SiteShell>
  );
}
