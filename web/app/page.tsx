import Link from "next/link";

export default function Home() {
  return (
    <main>
      <p className="title">Prior authorization, with the decision left to a person</p>
      <p className="muted" style={{ maxWidth: 640 }}>
        The library reads an insurance document, a second model flags risk, and a reviewer accepts each rule before it can touch a chart. Answers quote the synthetic chart. A clinician verifies every rule before anything is submitted.
      </p>
      <div className="row" style={{ marginTop: 16 }}>
        <Link className="btn" href="/admin/policies">Review policies</Link>
        <Link className="btn secondary" href="/doctor">Open an order</Link>
      </div>
    </main>
  );
}
