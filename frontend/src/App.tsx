export default function App() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
        background:
          "linear-gradient(135deg, rgba(15,23,42,1) 0%, rgba(30,41,59,1) 100%)",
        color: "#f8fafc",
        padding: "2rem",
        textAlign: "center",
      }}
    >
      <section>
        <p style={{ letterSpacing: "0.12em", textTransform: "uppercase", opacity: 0.7 }}>
          Phase 1
        </p>
        <h1 style={{ fontSize: "clamp(2rem, 5vw, 4rem)", margin: "0.5rem 0 1rem" }}>
          Event Management App
        </h1>
        <p style={{ maxWidth: "40rem", margin: 0, lineHeight: 1.6 }}>
          Frontend scaffolding is in place. Feature pages and workflows will be implemented in
          later phases.
        </p>
      </section>
    </main>
  );
}
