"use client";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="fatal-shell">
      <section className="fatal-card">
        <span className="eyebrow">SIMULATION DISPLAY FAILURE</span>
        <h1>The mission data could not be rendered.</h1>
        <p>{error.message}</p>
        <button type="button" className="primary-button" onClick={reset}>
          Retry data load
        </button>
      </section>
    </main>
  );
}

