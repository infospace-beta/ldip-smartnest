import Link from 'next/link';
export default function NotFound() {
  return <main className="flow-public" style={{maxWidth:620,paddingTop:100}}><Link className="brand" href="/">SmartNest</Link><p className="page-eyebrow">404 · Page not found</p><h1>Let’s get you back home.</h1><p>This page may have moved, or the link may be incomplete. Your saved records have not been deleted.</p><div className="flow-actions" style={{marginTop:24}}><Link className="button button-primary" href="/">Go to home page</Link><Link className="button button-secondary" href="/dashboard">Open workspace</Link></div></main>;
}
