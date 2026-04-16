import Link from "next/link";

export default function Home() {
  return (
    <main className="flex flex-col items-center justify-center h-screen gap-6 text-center px-4">
      <div>
        <h1 className="text-3xl font-bold mb-2">
          ServiceOntario Manual Search
        </h1>
        <p className="text-gray-500 text-sm max-w-md">
          Ask questions and get answers sourced directly from ServiceOntario
          manuals. No internet search — just the manuals.
        </p>
      </div>
      <Link
        href="/manuals"
        className="bg-blue-600 text-white px-6 py-3 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
      >
        Open Manual Search
      </Link>
    </main>
  );
}
