import { Link } from "@/i18n/navigation";
import { iconFor } from "@/lib/icons";
import type { PlaceCategoryGroup } from "@/lib/types";

/**
 * Un chip por grupo de categorías (categorias_reales en explorer/views.py).
 * Cada grupo enlaza al listado filtrado por su primer tipo representativo.
 */
export function PlaceTypeChips({ groups }: { groups: PlaceCategoryGroup[] }) {
  const visible = groups.filter((group) => group.subcategorias.length > 0);

  return (
    <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1 pb-1 sm:flex-wrap sm:overflow-visible">
      {visible.map((group) => {
        const Icon = iconFor(group.icon);
        const primary = group.subcategorias[0];

        return (
          <Link
            key={group.name}
            href={{ pathname: "/lugares", query: { tipo: primary.value } }}
            className="group flex shrink-0 items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-left transition hover:-translate-y-0.5 hover:border-accent-400 hover:shadow-[0_10px_24px_-12px_rgba(17,153,142,0.45)] sm:px-3.5"
          >
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-700 ring-1 ring-brand-100 transition group-hover:bg-accent-50 group-hover:text-accent-800 group-hover:ring-accent-200">
              <Icon className="size-4.5" aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-xs font-bold text-slate-900 sm:text-sm">
                {group.name}
              </span>
              <span className="block truncate text-[11px] text-slate-500">
                {group.subcategorias.length}
              </span>
            </span>
          </Link>
        );
      })}
    </div>
  );
}
