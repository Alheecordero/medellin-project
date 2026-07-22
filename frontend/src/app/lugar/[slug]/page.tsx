import SiteShell from "@/components/SiteShell";
import { getPlace } from "@/lib/api";
import { notFound } from "next/navigation";
import Image from "next/image";

export const revalidate = 300;

export default async function PlaceDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  let data;
  try {
    data = await getPlace(slug, "es");
  } catch {
    notFound();
  }

  const { lugar } = data;
  const heroImg = lugar.fotos?.[0]?.imagen_mediana || lugar.fotos?.[0]?.imagen || lugar.imagen;

  return (
    <SiteShell locale="es">
      <section className="detail-hero">
        {heroImg && (
          <Image src={heroImg} alt={lugar.nombre} fill className="object-cover opacity-50" priority />
        )}
        <div className="detail-hero__content relative z-10">
          <p className="text-sm uppercase tracking-widest text-teal-200">{lugar.tipo}</p>
          <h1 className="mt-2 text-4xl font-extrabold">{lugar.nombre}</h1>
          {lugar.rating > 0 && (
            <p className="mt-2 text-lg">★ {lugar.rating.toFixed(1)} ({lugar.total_reviews} reseñas)</p>
          )}
        </div>
      </section>

      <div className="detail-panel">
        <div className="detail-card space-y-4">
          {lugar.direccion && <p><strong>Dirección:</strong> {lugar.direccion}</p>}
          {lugar.descripcion && <p>{lugar.descripcion}</p>}
          {lugar.caracteristicas && lugar.caracteristicas.length > 0 && (
            <div className="chips">
              {lugar.caracteristicas.map((c) => (
                <span key={c} className="chip">{c}</span>
              ))}
            </div>
          )}
        </div>
      </div>
    </SiteShell>
  );
}
