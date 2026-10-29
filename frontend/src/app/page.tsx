import Link from "next/link";

const roles = [
  { title: "Property managers", copy: "Organise properties, units, leases, payments and your team in one workspace." },
  { title: "Tenants", copy: "Keep your home details, payment records and maintenance requests close at hand." },
  { title: "Staff and maintenance", copy: "See assigned work, share updates and keep property tasks moving." },
];

export default function HomePage() {
  return (
    <main className="public-home">
      <header className="public-nav">
        <Link className="brand" href="/">
          <span className="brand-mark">S</span>
          <span><span className="brand-name">SmartNest</span><span className="brand-caption">Property operations</span></span>
        </Link>
        <nav aria-label="Main navigation">
          <a href="#how-it-works">How it works</a>
          <a href="#who-its-for">Who it’s for</a>
          <Link className="button button-secondary" href="/login">Sign in</Link>
        </nav>
      </header>

      <section className="public-hero">
        <div className="public-hero-copy">
          <div className="page-eyebrow">A calmer way to manage homes</div>
          <h1>Good spaces.<br /><span>Better managed.</span></h1>
          <p>SmartNest brings property teams, tenants and maintenance into one clear place—so everyday work feels easier and everyone knows what comes next.</p>
          <div className="public-actions">
            <Link className="button button-primary" href="/login?mode=register">Create a tenant account</Link>
            <Link className="button button-secondary" href="/login">Sign in to your workspace</Link>
          </div>
          <p className="public-note">Tenant accounts are linked to a home by a property manager. Already invited? <Link href="/join">Accept your invitation</Link>.</p>
        </div>
        <div className="public-hero-card" aria-label="SmartNest property operations overview">
          <div className="public-card-top"><span className="workspace-dot" /> One connected workspace</div>
          <div className="public-home-stat"><span>Properties</span><strong>In one place</strong></div>
          <div className="public-home-stat"><span>Maintenance</span><strong>Clear next steps</strong></div>
          <div className="public-home-stat"><span>Communication</span><strong>With the right people</strong></div>
          <div className="public-card-footer">A simpler way to care for homes and the people in them.</div>
        </div>
      </section>

      <section className="public-section" id="how-it-works">
        <div className="page-eyebrow">From move-in to maintenance</div>
        <h2>Everyday property work, connected.</h2>
        <div className="public-steps">
          <article><span>01</span><h3>Set up the home</h3><p>Managers add their properties, units and tenancy details.</p></article>
          <article><span>02</span><h3>Invite the right people</h3><p>Tenants join through an invitation; staff receive access to assigned work.</p></article>
          <article><span>03</span><h3>Keep things moving</h3><p>Record handovers, follow maintenance and share updates with your team.</p></article>
        </div>
      </section>

      <section className="public-section public-roles" id="who-its-for">
        <div className="page-eyebrow">One team, clear access</div>
        <h2>Made for everyone involved in a home.</h2>
        <div className="public-role-grid">
          {roles.map((role) => <article className="public-role-card" key={role.title}><h3>{role.title}</h3><p>{role.copy}</p></article>)}
        </div>
        <p className="public-privacy">Your workspace is role-based: people see the property records and tasks needed for their role. Personal information should be shared only when it is needed to manage a tenancy or service.</p>
      </section>

      <footer className="public-footer">
        <Link className="brand" href="/">
          <span className="brand-mark">S</span>
          <span><span className="brand-name">SmartNest</span><span className="brand-caption">Homes, better managed.</span></span>
        </Link>
        <span>Property operations, made clearer.</span>
        <Link href="/login">Sign in</Link>
      </footer>
    </main>
  );
}
