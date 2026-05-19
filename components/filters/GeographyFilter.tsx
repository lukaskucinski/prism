"use client";

import { useEffect, useState } from "react";
import { useFilterStore } from "@/lib/store/filters";
import { Checkbox } from "@/components/ui/checkbox";

interface State {
  state_fips: string;
  state_abbr: string;
  state_name: string;
}

interface County {
  county_fips: string;
  state_fips: string;
  county_name: string;
}

export function GeographyFilter() {
  const states = useFilterStore((s) => s.states);
  const counties = useFilterStore((s) => s.counties);
  const setStates = useFilterStore((s) => s.setStates);
  const setCounties = useFilterStore((s) => s.setCounties);

  const [stateOptions, setStateOptions] = useState<State[]>([]);
  const [countyOptions, setCountyOptions] = useState<County[]>([]);
  const [countyLoading, setCountyLoading] = useState(false);

  useEffect(() => {
    fetch("/api/states")
      .then((r) => r.json())
      .then((j) => setStateOptions(j.states ?? []))
      .catch(() => setStateOptions([]));
  }, []);

  useEffect(() => {
    if (!states.length) {
      setCountyOptions([]);
      return;
    }
    // Resolve state_abbr → state_fips for the API
    const fipsList = stateOptions
      .filter((s) => states.includes(s.state_abbr))
      .map((s) => s.state_fips);
    if (!fipsList.length) {
      setCountyOptions([]);
      return;
    }
    setCountyLoading(true);
    fetch(`/api/counties?states=${fipsList.join(",")}`)
      .then((r) => r.json())
      .then((j) => setCountyOptions(j.counties ?? []))
      .catch(() => setCountyOptions([]))
      .finally(() => setCountyLoading(false));
  }, [states, stateOptions]);

  const toggleState = (abbr: string) => {
    setStates(
      states.includes(abbr) ? states.filter((s) => s !== abbr) : [...states, abbr]
    );
    setCounties([]); // counties reset when state set changes
  };

  const toggleCounty = (fips: string) => {
    setCounties(
      counties.includes(fips) ? counties.filter((c) => c !== fips) : [...counties, fips]
    );
  };

  return (
    <div className="space-y-3">
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[11px] text-muted-foreground">State</span>
          {states.length > 0 && (
            <button
              type="button"
              onClick={() => {
                setStates([]);
                setCounties([]);
              }}
              className="text-[10px] text-muted-foreground hover:text-foreground"
            >
              clear
            </button>
          )}
        </div>
        {stateOptions.length === 0 ? (
          <p className="text-[11px] italic text-muted-foreground">
            Run <code className="font-mono">prism.boundaries.load_tiger</code> to populate
            states.
          </p>
        ) : (
          <ul className="grid max-h-32 grid-cols-2 gap-1 overflow-y-auto pr-1">
            {stateOptions.map((s) => {
              const id = `state-${s.state_abbr}`;
              return (
                <li key={s.state_fips} className="flex items-center gap-1.5">
                  <Checkbox
                    id={id}
                    checked={states.includes(s.state_abbr)}
                    onCheckedChange={() => toggleState(s.state_abbr)}
                  />
                  <label htmlFor={id} className="cursor-pointer text-xs">
                    {s.state_abbr}
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {states.length > 0 && (
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-[11px] text-muted-foreground">
              County {countyLoading ? "(loading…)" : ""}
            </span>
            {counties.length > 0 && (
              <button
                type="button"
                onClick={() => setCounties([])}
                className="text-[10px] text-muted-foreground hover:text-foreground"
              >
                clear
              </button>
            )}
          </div>
          {countyOptions.length === 0 && !countyLoading ? (
            <p className="text-[11px] italic text-muted-foreground">
              No counties (or boundaries not loaded).
            </p>
          ) : (
            <ul className="max-h-40 space-y-0.5 overflow-y-auto pr-1">
              {countyOptions.map((c) => {
                const id = `county-${c.county_fips}`;
                return (
                  <li key={c.county_fips} className="flex items-center gap-1.5">
                    <Checkbox
                      id={id}
                      checked={counties.includes(c.county_fips)}
                      onCheckedChange={() => toggleCounty(c.county_fips)}
                    />
                    <label htmlFor={id} className="cursor-pointer text-xs">
                      {c.county_name}
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
