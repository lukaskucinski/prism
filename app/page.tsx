import PrismMapClient from "@/components/map/PrismMapClient";

export default function Page() {
  return (
    <main
      className="relative h-screen w-screen overflow-hidden"
      style={{ height: "100dvh", width: "100vw" }}
    >
      <PrismMapClient />
    </main>
  );
}
