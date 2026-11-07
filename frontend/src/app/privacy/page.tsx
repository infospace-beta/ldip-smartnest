import Link from "next/link";

export default function PrivacyPage() {
  return <main className="flow-public flow-page">
    <Link className="brand" href="/">SmartNest</Link>
    <h1>Privacy notice</h1><p>Updated 7 November 2026</p>
    <section className="panel flow-card">
      <h2>Who to contact</h2>
      <p>SmartNest is currently operated by an individual. For account privacy questions, rights requests or security concerns, contact <a href="mailto:ogonyogad@gmail.com">ogonyogad@gmail.com</a>. For decisions about your tenancy, payments or inspections, contact your property manager as well.</p>
      <p>The operator’s full legal name and registration details are being finalised. SmartNest does not currently hold an ODPC registration certificate. This notice does not claim registration or regulatory approval.</p>
      <h2>What we use and why</h2>
      <p>We process account identifiers, contact details, approved roles, property and tenancy records, payment records, repair requests, inspection reports, messages and photos you or your property team provide. These support account security, tenancy administration, repairs, inspections, communication and record keeping. Do not upload unnecessary identification documents, health information or photos of other people.</p>
      <p>The relevant lawful basis depends on the purpose, such as a tenancy or service contract, a legal obligation, a documented legitimate interest or consent where required. Optional photos and marketing must not be treated as blanket consent for unrelated processing.</p>
      <h2>Who can access information</h2>
      <p>Access depends on your role, property assignments, message recipients and linked tasks. Repair providers receive the details needed for assigned work. Important notices may be visible to administrators as ciphertext; notices addressed to an administrator can be read by that administrator. Notice encryption is server-side, not end-to-end encryption.</p>
      <p>Supabase provides sign-in services, and the configured email service handles account messages. Production hosting providers, locations, subprocessors and any overseas-transfer safeguards must be confirmed before public deployment. We do not sell your personal information.</p>
      <h2>Retention and security</h2>
      <p>We use access controls and safeguards appropriate to the information. Records are kept for their documented operational or legal purpose and should then be deleted or anonymised, including under the backup lifecycle. A category-specific retention schedule is being finalised; contact us for the period applicable to a particular record. Closing an account does not automatically remove records that must lawfully be retained.</p>
      <h2>Your choices and rights</h2>
      <p>You may request information about processing, access, correction, objection, restriction or deletion as applicable under Kenyan law. Email the contact above with the type of request; we may need to verify your identity without collecting excessive information. Do not send passwords, reset links or authenticator codes. You can also complain to the <a href="https://www.odpc.go.ke/" rel="noreferrer">Office of the Data Protection Commissioner</a>.</p>
      <p>Managers can disable workflow automations and use manual controls. Inspection acknowledgments are separate from agreement with findings; use the review/dispute controls or contact your manager.</p>
      <h2>Cookies and demo</h2>
      <p>Essential cookies maintain sign-in and your trusted-device choice. Always sign out on shared devices. The public demo uses sample records and does not activate a real account. Any future optional analytics or marketing must be disclosed with appropriate choices.</p>
      <p>Material changes to this notice will be identified here and communicated where required.</p>
    </section><p><Link href="/terms">Terms of use</Link> · <Link href="/login">Sign in</Link></p>
  </main>;
}
