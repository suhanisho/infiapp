import { BackendButton } from "./backend-button";

export default function Home() {
  return (
    <main className="shell">
      <section className="hero" aria-labelledby="home-title">
        <p className="eyebrow">Infiapp starter</p>
        <h1 id="home-title">Hi from infiapp</h1>
        <BackendButton />
      </section>
    </main>
  );
}
