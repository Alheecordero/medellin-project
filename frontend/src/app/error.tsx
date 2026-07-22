"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-lg px-4 py-16 text-center">
      <h1 className="text-2xl font-bold text-slate-900">No pudimos cargar la página</h1>
      <p className="mt-3 text-slate-600">
        {error.message.includes("fetch") || error.message.includes("API")
          ? "Verifica que Django esté corriendo en el puerto 8000."
          : error.message}
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 inline-flex rounded-full bg-teal-600 px-5 py-2 text-sm font-semibold text-white"
      >
        Reintentar
      </button>
    </div>
  );
}
