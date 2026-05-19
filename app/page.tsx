import dynamic from "next/dynamic";

const PrismMap = dynamic(() => import("@/components/map/PrismMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-screen w-screen items-center justify-center bg-background text-muted-foreground">
      <div className="text-sm tracking-wide">Loading map…</div>
    </div>
  ),
});

export default function Page() {
  return (
    <main className="relative h-screen w-screen overflow-hidden">
      <PrismMap />
    </main>
  );
}
