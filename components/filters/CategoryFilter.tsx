"use client";

import { useFilterStore } from "@/lib/store/filters";
import {
  CATEGORY_LABELS,
  FRICTION_CATEGORIES,
  type FrictionCategory,
} from "@/lib/h3/categories";
import { Checkbox } from "@/components/ui/checkbox";

export function CategoryFilter() {
  const categories = useFilterStore((s) => s.categories);
  const toggle = useFilterStore((s) => s.toggleCategory);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] text-muted-foreground">Layer category</span>
        {categories.length > 0 && (
          <button
            type="button"
            onClick={() => useFilterStore.getState().setCategories([])}
            className="text-[10px] text-muted-foreground hover:text-foreground"
          >
            clear
          </button>
        )}
      </div>
      <ul className="space-y-1.5">
        {FRICTION_CATEGORIES.map((cat: FrictionCategory) => {
          const id = `cat-${cat}`;
          const checked = categories.includes(cat);
          return (
            <li key={cat} className="flex items-center gap-2">
              <Checkbox
                id={id}
                checked={checked}
                onCheckedChange={() => toggle(cat)}
              />
              <label
                htmlFor={id}
                className="cursor-pointer text-xs text-foreground/90 hover:text-foreground"
              >
                {CATEGORY_LABELS[cat]}
              </label>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
