import { ArrowUpRight, MapPin } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { RemoteImage } from "@/components/ui/RemoteImage";

type Props = {
  slug: string;
  name: string;
  countLabel: string;
  /** Primera foto de un lugar de la zona; no hay miniaturas estáticas por comuna. */
  image?: string | null;
  eager?: boolean;
};

export function ZoneTile({ slug, name, countLabel, image, eager = false }: Props) {
  return (
    <Link
      href={{ pathname: "/lugares", query: { area: slug } }}
      className="group relative flex flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm ring-1 ring-transparent transition duration-300 hover:-translate-y-1 hover:border-accent-400/70 hover:shadow-[0_14px_32px_-12px_rgba(17,153,142,0.45)] hover:ring-brand-200/80"
    >
      <div className="relative aspect-[5/4] w-full overflow-hidden bg-slate-200">
        <RemoteImage
          src={image}
          alt=""
          fill
          priority={eager}
          sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 16vw"
          className="object-cover transition duration-500 group-hover:scale-110 group-hover:saturate-[1.1]"
          fallback={
            <div className="absolute inset-0 bg-gradient-to-br from-brand-500 via-brand-700 to-slate-900" />
          }
        />

        <div className="absolute inset-0 bg-gradient-to-t from-slate-950/85 via-slate-900/25 to-brand-600/15" />
        <div className="absolute inset-0 bg-brand-600/0 transition duration-300 group-hover:bg-brand-600/15" />

        <span className="absolute right-2 top-2 inline-flex max-w-[calc(100%-1rem)] items-center gap-1 rounded-full bg-accent-500 px-2 py-0.5 text-[10px] font-bold text-brand-900 shadow-[0_4px_12px_rgba(56,239,125,0.4)] sm:text-[11px]">
          <MapPin className="size-3 shrink-0" aria-hidden />
          <span className="truncate">{countLabel}</span>
        </span>

        <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 p-2.5">
          <p className="truncate text-sm font-extrabold leading-tight text-white drop-shadow-[0_1px_3px_rgba(0,0,0,0.5)]">
            {name}
          </p>
          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-white/20 text-white ring-1 ring-white/30 backdrop-blur-sm transition duration-300 group-hover:scale-110 group-hover:bg-accent-500 group-hover:text-brand-900 group-hover:ring-accent-200">
            <ArrowUpRight className="size-3.5" aria-hidden />
          </span>
        </div>
      </div>

      <div className="h-1 bg-gradient-to-r from-accent-500 via-brand-500 to-brand-700 opacity-0 transition duration-300 group-hover:opacity-100" />
    </Link>
  );
}
