"use client";

import dynamic from "next/dynamic";

const PrismMap = dynamic(() => import("./PrismMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-screen w-screen items-center justify-center bg-background text-muted-foreground">
      <div className="text-sm tracking-wide">Loading map…</div>
    </div>
  ),
});

export default function PrismMapClient() {
  return <PrismMap />;
}
