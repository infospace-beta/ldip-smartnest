import Link from "next/link";

export default function TermsPage() {
  return <main className="flow-public flow-page"><Link className="brand" href="/">SmartNest</Link>
    <h1>Terms of use</h1><p>Updated 7 November 2026</p>
    <section className="panel flow-card">
      <h2>Service and contact</h2><p>SmartNest helps invited property teams, tenants, staff and service providers coordinate property records, payments, repairs and inspections. The current individual operator can be contacted at <a href="mailto:ogonyogad@gmail.com">ogonyogad@gmail.com</a>. The operator’s legal-name details are being finalised; these terms do not claim ODPC registration.</p>
      <h2>Accounts and access</h2><p>Actual roles are approved by an administrator or property manager. Demo role selection does not grant real access. Use your own credentials, protect your authenticator and report suspected unauthorised access. Do not access other people’s records, share invitations publicly, upload unlawful material or interfere with the service. Accounts may be restricted for security, misuse or the end of an authorised role, with applicable legal rights preserved.</p>
      <h2>Records and decisions</h2><p>Submit accurate information and only material you are entitled to share. Your tenancy agreement governs rent, property access and other tenancy obligations. SmartNest does not replace that agreement, legal notice requirements or a fair review of disputed repairs, inspections and charges. Confirm payment outcomes against the relevant payment records. A recorded inspection acknowledgment is not agreement to charges.</p>
      <h2>Automations and availability</h2><p>Managers may disable automations and use manual controls. Notifications and automated assignments can be delayed; use your property’s emergency contact for urgent danger or repairs. Availability depends on infrastructure and connected providers. Planned interruptions and material service changes should be communicated through available contacts.</p>
      <h2>Fees, ending access and complaints</h2><p>No subscription purchase is offered on this page. Any paid service must provide its price, billing, cancellation and refund terms before acceptance. Request account closure, data access or a complaint through the contact above; lawful record-retention duties may continue. Nothing here removes mandatory consumer, data-protection or other rights under Kenyan law.</p>
      <h2>Privacy and changes</h2><p>Read the <Link href="/privacy">privacy notice</Link> for data use and rights. Material changes to these terms will be published with an updated date and communicated where required. These terms are governed by Kenyan law, subject to applicable mandatory rights.</p>
    </section><p><Link href="/privacy">Privacy notice</Link> · <Link href="/login">Sign in</Link></p>
  </main>;
}
