"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ArrowUpRight,
  BadgeCheck,
  ChevronDown,
  CircleAlert,
  FileCheck2,
  FileText,
  Languages,
  Landmark,
  MessageCircle,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  UploadCloud,
} from "lucide-react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

type Provider = "sarvam" | "openmodel" | "mock";

type ProviderConfig = {
  id: Provider;
  label: string;
  model: string;
  configured: boolean;
};

type Evidence = {
  document: string;
  page: number;
  field: string;
  value: string;
};

type Finding = {
  id: string;
  severity: "high" | "medium" | "low";
  title: string;
  summary: string;
  evidence: Evidence[];
};

type Dashboard = {
  documents: number;
  fields_extracted: number;
  entities_normalized: number;
  score: number;
  status: string;
  property: {
    village: string;
    taluk: string;
    district: string;
    survey: string;
    owner: string;
  };
  findings: Finding[];
  coverage: { name: string; status: string }[];
  timeline: { date: string; label: string; type: string }[];
};

const severityMeta = {
  high: { label: "High", className: "severity-high" },
  medium: { label: "Medium", className: "severity-medium" },
  low: { label: "Low", className: "severity-low" },
};

export default function BhoomiConsole() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [provider, setProvider] = useState<Provider>("mock");
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [activeFinding, setActiveFinding] = useState("F-001");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [language, setLanguage] = useState("English");
  const [uploadStatus, setUploadStatus] = useState("");
  const uploadInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/demo/case`, { cache: "no-store" }).then((r) =>
        r.json()
      ),
      fetch(`${API_BASE}/config`, { cache: "no-store" }).then((r) =>
        r.json()
      ),
    ]).then(([demo, config]) => {
      setData(demo);
      setProviders(config.providers ?? []);
      setProvider((config.default_provider as Provider) ?? "mock");
    });
  }, []);

  const finding = useMemo(
    () =>
      data?.findings.find((item) => item.id === activeFinding) ??
      data?.findings[0],
    [activeFinding, data]
  );

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploadStatus(`Preparing ${file.name}…`);

    const form = new FormData();
    form.append("file", file);
    form.append(
      "language",
      language === "English" ? "en-IN" : language === "हिन्दी" ? "hi-IN" : "kn-IN"
    );
    form.append(
      "schema",
      JSON.stringify({
        type: "object",
        properties: {
          document_type: {
            type: "string",
            description:
              "Document type such as RTC, mutation extract, sale deed, or encumbrance certificate",
          },
          owner_names: {
            type: "array",
            items: { type: "string" },
            description: "All owner or rights-holder names in the document",
          },
          survey_number: {
            type: "string",
            description: "Survey number exactly as written",
          },
          land_extent: {
            type: "string",
            description: "Recorded land extent with unit",
          },
          village: {
            type: "string",
            description: "Village name",
          },
          taluk: {
            type: "string",
            description: "Taluk name",
          },
          district: {
            type: "string",
            description: "District name",
          },
        },
      })
    );

    try {
      const response = await fetch(`${API_BASE}/documents/extract`, {
        method: "POST",
        body: form,
      });
      const body = await response.json();

      if (!response.ok) {
        throw new Error(body.detail || body.message || "Extraction request failed");
      }

      setUploadStatus(
        body.job_id
          ? `Sarvam job ${body.job_id.slice(0, 8)}… queued`
          : body.message || "Document accepted for analysis."
      );
    } catch (error) {
      setUploadStatus(
        error instanceof Error ? error.message : "Upload failed"
      );
    } finally {
      if (uploadInputRef.current) {
        uploadInputRef.current.value = "";
      }
    }
  }

  async function handleQuestion(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;

    setBusy(true);
    setAnswer("");

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, provider }),
      });
      const body = await response.json();

      if (!response.ok) {
        throw new Error(body.detail || body.message || "AI request failed");
      }

      setAnswer(body.answer);
    } catch (error) {
      setAnswer(error instanceof Error ? error.message : "The AI request failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return <main className="page-shell loading-shell">Loading case workspace…</main>;
  }

  return (
    <main className="page-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark">
            <Landmark size={18} strokeWidth={2.2} />
          </div>
          <div>
            <div className="brand-name">BhoomiLens</div>
            <div className="brand-sub">record reconciliation / India</div>
          </div>
        </div>

        <div className="topbar-actions">
          <div className="mode-pill">
            <span className="live-dot" /> Screening mode
          </div>
          <button className="icon-button" aria-label="Language">
            <Languages size={18} />
          </button>
          <div className="language-select">
            <span>{language}</span>
            <ChevronDown size={14} />
            <select
              aria-label="Language"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option>English</option>
              <option>हिन्दी</option>
              <option>ಕನ್ನಡ</option>
            </select>
          </div>
        </div>
      </header>

      <section className="hero-grid">
        <div className="hero-copy">
          <div className="eyebrow">
            <span>PS41</span> Land-record risk &amp; reconciliation
          </div>
          <h1>
            Make property records
            <br />
            <em>agree with each other.</em>
          </h1>
          <p className="hero-text">
            BhoomiLens turns messy RTC, mutation, deed and certificate bundles
            into one evidence trail — readable before you trust it.
          </p>

          <div className="hero-actions">
            <button
              className="primary-button"
              type="button"
              onClick={() => uploadInputRef.current?.click()}
            >
              <UploadCloud size={17} /> Upload documents
            </button>
            <input
              ref={uploadInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              hidden
              onChange={handleUpload}
            />
            <button className="ghost-button" type="button">
              <ScanSearch size={17} /> How reconciliation works
            </button>
          </div>
        </div>

        <div className="score-card">
          <div className="score-topline">
            <span>Record consistency</span>
            <BadgeCheck size={16} />
          </div>
          <div className="score-value">
            {data.score}
            <span>/100</span>
          </div>
          <div className="score-bar">
            <span style={{ width: `${data.score}%` }} />
          </div>
          <div className="score-foot">
            <span>{data.status}</span>
            <span>{data.findings.length} findings</span>
          </div>
          <div className="score-note">
            Not a legal title verdict. It is a consistency screen across the
            uploaded evidence.
          </div>
        </div>
      </section>

      {uploadStatus && (
        <div className="upload-status">
          <UploadCloud size={14} /> {uploadStatus}
        </div>
      )}

      <section className="stats-strip">
        <Metric
          value={data.documents}
          label="documents analyzed"
          icon={<FileText size={16} />}
        />
        <Metric
          value={data.fields_extracted}
          label="fields extracted"
          icon={<ScanSearch size={16} />}
        />
        <Metric
          value={data.entities_normalized}
          label="entities normalized"
          icon={<ShieldCheck size={16} />}
        />
        <Metric
          value={data.findings.length}
          label="findings requiring review"
          icon={<CircleAlert size={16} />}
        />
      </section>

      <section className="workspace-grid">
        <div className="property-panel panel">
          <PanelTitle kicker="PROPERTY" title="Identity snapshot" />
          <div className="property-main">
            <span className="property-label">Survey identifier</span>
            <strong>{data.property.survey}</strong>
          </div>

          <div className="detail-grid">
            <Detail label="Recorded owner" value={data.property.owner} />
            <Detail label="Village" value={data.property.village} />
            <Detail label="Taluk" value={data.property.taluk} />
            <Detail label="District" value={data.property.district} />
          </div>

          <div className="coverage-block">
            <div className="mini-heading">DOCUMENT COVERAGE</div>
            {data.coverage.map((item) => (
              <div className="coverage-row" key={item.name}>
                <span>{item.status === "present" ? "✓" : "?"}</span>
                <span>{item.name}</span>
                <small>
                  {item.status === "present" ? "provided" : "missing"}
                </small>
              </div>
            ))}
          </div>
        </div>

        <div className="findings-panel panel">
          <PanelTitle
            kicker="RECONCILIATION"
            title="Where the records disagree"
            action={<span className="count-badge">{data.findings.length}</span>}
          />

          <div className="finding-list">
            {data.findings.map((item) => {
              const meta = severityMeta[item.severity];
              const active = item.id === activeFinding;

              return (
                <button
                  className={`finding-item ${active ? "active" : ""}`}
                  key={item.id}
                  onClick={() => setActiveFinding(item.id)}
                >
                  <div className={`severity-dot ${meta.className}`} />
                  <div className="finding-item-copy">
                    <div className="finding-meta">
                      <span>{meta.label} attention</span>
                      <span>{item.id}</span>
                    </div>
                    <strong>{item.title}</strong>
                    <p>{item.summary}</p>
                  </div>
                  <ArrowUpRight size={17} className="row-arrow" />
                </button>
              );
            })}
          </div>

          <div className="review-note">
            <Sparkles size={15} />
            Findings are generated from structured comparisons; semantic
            explanation comes from the selected AI provider.
          </div>
        </div>

        <div className="evidence-panel panel">
          <PanelTitle
            kicker="EVIDENCE"
            title="Show the source, not just the warning"
          />

          {finding && (
            <>
              <div className="evidence-title">
                <span
                  className={`severity-tag ${severityMeta[finding.severity].className}`}
                >
                  {severityMeta[finding.severity].label}
                </span>
                {finding.title}
              </div>

              <p className="evidence-summary">{finding.summary}</p>

              <div className="evidence-grid">
                {finding.evidence.map((evidence, index) => (
                  <div
                    className="evidence-card"
                    key={`${evidence.document}-${index}`}
                  >
                    <div className="evidence-card-top">
                      <FileCheck2 size={15} />
                      <span>{evidence.document}</span>
                      <span>p.{evidence.page}</span>
                    </div>
                    <div className="evidence-field">
                      {evidence.field.replaceAll("_", " ")}
                    </div>
                    <div className="evidence-value">{evidence.value}</div>
                  </div>
                ))}
              </div>

              <div className="difference-callout">
                <span>Difference</span>
                <strong>
                  {finding.evidence.map((item) => item.value).join("  ≠  ")}
                </strong>
              </div>
            </>
          )}
        </div>

        <div className="timeline-panel panel">
          <PanelTitle
            kicker="OWNERSHIP THREAD"
            title="Apparent record timeline"
            action={<span className="muted-label">reconstructed</span>}
          />
          <div className="timeline">
            {data.timeline.map((item) => (
              <div className="timeline-row" key={`${item.date}-${item.label}`}>
                <div className="timeline-date">{item.date}</div>
                <div className="timeline-pin">
                  <span />
                </div>
                <div className="timeline-copy">
                  <strong>{item.label}</strong>
                  <span>{item.type}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="assistant-panel panel">
        <div className="assistant-left">
          <div className="assistant-orbit">
            <MessageCircle size={21} />
          </div>
          <div>
            <div className="mini-heading">ASK THE RECORDS</div>
            <h2>Evidence-grounded assistant</h2>
            <p>
              Ask what changed, why an item was flagged, or which page supports
              a finding.
            </p>
          </div>
        </div>

        <div className="provider-switch">
          <span className="mini-heading">AI PROVIDER</span>
          <div className="provider-buttons">
            {providers.map((item) => (
              <button
                key={item.id}
                className={provider === item.id ? "selected" : ""}
                onClick={() => setProvider(item.id)}
                disabled={!item.configured && item.id !== "mock"}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <form className="assistant-form" onSubmit={handleQuestion}>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. What is the most important inconsistency?"
          />
          <button className="send-button" disabled={busy}>
            {busy ? "Thinking…" : "Ask"}
          </button>
        </form>

        {answer && (
          <div className="assistant-answer">
            <div className="answer-label">{provider.toUpperCase()}</div>
            {answer}
          </div>
        )}
      </section>

      <footer className="footer-note">
        AI-assisted document screening only · Verify material findings against
        authoritative records and qualified professionals.
      </footer>
    </main>
  );
}

function Metric({
  value,
  label,
  icon,
}: {
  value: number;
  label: string;
  icon: ReactNode;
}) {
  return (
    <div className="metric">
      <span className="metric-icon">{icon}</span>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PanelTitle({
  kicker,
  title,
  action,
}: {
  kicker: string;
  title: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel-title">
      <div>
        <div className="mini-heading">{kicker}</div>
        <h2>{title}</h2>
      </div>
      {action}
    </div>
  );
}
