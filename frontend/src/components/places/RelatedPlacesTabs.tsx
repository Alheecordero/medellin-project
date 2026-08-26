"use client";

import { useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export type RelatedTab = {
  id: string;
  label: string;
  count: number;
  content: ReactNode;
};

/** Los grids llegan ya renderizados en el servidor; aquí solo se alternan. */
export function RelatedPlacesTabs({ tabs, emptyLabel }: { tabs: RelatedTab[]; emptyLabel: string }) {
  const available = tabs.filter((tab) => tab.count > 0);
  const [active, setActive] = useState(available[0]?.id);

  if (available.length === 0) {
    return <p className="text-sm text-slate-500">{emptyLabel}</p>;
  }

  return (
    <div>
      <div
        className="no-scrollbar flex gap-2 overflow-x-auto border-b border-slate-200 pb-px"
        role="tablist"
      >
        {available.map((tab) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`related-panel-${tab.id}`}
              id={`related-tab-${tab.id}`}
              onClick={() => setActive(tab.id)}
              className={cn(
                "-mb-px shrink-0 border-b-2 px-3 py-2 text-sm font-semibold transition",
                selected
                  ? "border-accent-500 text-brand-800"
                  : "border-transparent text-slate-500 hover:border-brand-200 hover:text-brand-700",
              )}
            >
              {tab.label}
              <span className={cn("ml-1.5 text-xs", selected ? "text-accent-700" : "text-slate-400")}>
                {tab.count}
              </span>
            </button>
          );
        })}
      </div>

      {available.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`related-panel-${tab.id}`}
          aria-labelledby={`related-tab-${tab.id}`}
          hidden={tab.id !== active}
          className="pt-4"
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}
