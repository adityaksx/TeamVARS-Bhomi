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
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Download,
  FileCheck2,
  FileText,
  Languages,
  Landmark,
  LoaderCircle,
  MessageCircle,
  ScanSearch,
  ShieldCheck,
  Settings,
  Sparkles,
  UploadCloud,
} from "lucide-react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

type Provider = "auto" | "sarvam" | "gemini" | "grok" | "ollama" | "local" | "mock";

type ProviderConfig = {
  id: Provider;
  label: string;
  model: string;
  configured: boolean;
};

type EvidenceAnchor = {
  page: number;
  page_width: number;
  page_height: number;
  bbox: [number, number, number, number];
  text: string;
  method: string;
};

type Evidence = {
  document_id?: string;
  document: string;
  page: number;
  field: string;
  value: unknown;
  anchor?: EvidenceAnchor | null;
};

type Finding = {
  id: string;
  kind: string;
  severity: "high" | "medium" | "low";
  title: string;
  summary: string;
  score_impact: number;
  evidence: Evidence[];
  confidence?: number;
  verification_action?: string;
  resolutions?: { left_value: string; right_value: string; similarity: number; state: string; rationale: string }[];
};

type Dashboard = {
  case_id?: string;
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
  extraction_status?: string;
  reasoning_provider?: Provider;
  confidence?: number;
};

const severityMeta = {
  high: { label: "High", className: "severity-high" },
  medium: { label: "Medium", className: "severity-medium" },
  low: { label: "Low", className: "severity-low" },
};

async function jsonFetch(path: string, init?: RequestInit) {
  const response = await fetch(`${API_BASE}${path}`, init);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail || body.message || "Request failed");
  }
  return body;
}

export default function BhoomiConsole() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [provider, setProvider] = useState<Provider>("auto");
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [apiKeys, setApiKeys] = useState({ sarvam: "", gemini: "", grok: "" });
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState("http://localhost:11434/v1");
  const [ollamaModel, setOllamaModel] = useState("qwen3:8b");
  type DiagState = { message: string; status: "pass" | "fail" | "pending" };
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [providerTest, setProviderTest] = useState<Record<string, DiagState>>({});
  const [activeFinding, setActiveFinding] = useState("F-001");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [explanation, setExplanation] = useState("");
  const [busy, setBusy] = useState(false);
  const [explaining, setExplaining] = useState(false);
  const [language, setLanguage] = useState("English");
  const [uploadStatus, setUploadStatus] = useState("");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [caseId, setCaseId] = useState("");
  const [analysisRunning, setAnalysisRunning] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [activeEvidence, setActiveEvidence] = useState<Evidence | null>(null);
  const [diagnostics, setDiagnostics] = useState<{
    id: string;
    filename: string;
    type: string;
    stage: string;
    status: string;
    pageCount: number;
  }[] | null>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try {
      // Security: purge any previously persisted API keys from localStorage
      localStorage.removeItem("bhoomilens_sarvam_key");
      localStorage.removeItem("bhoomilens_gemini_key");
      localStorage.removeItem("bhoomilens_grok_key");
      setOllamaBaseUrl(localStorage.getItem("bhoomilens_ollama_url") ?? "http://localhost:11434");
      setOllamaModel(localStorage.getItem("bhoomilens_ollama_model") ?? "qwen3:8b");
    } catch {}
  }, []);

  async function refreshOllamaModels() {
    try {
      const body = await jsonFetch("/ollama/models", { headers: { "X-Ollama-Base-Url": ollamaBaseUrl } });
      const names = (body.models ?? []).map((item: { name?: string }) => item.name).filter(Boolean) as string[];
      setOllamaModels(names);
      if (names.length && !names.includes(ollamaModel)) {
        const preferred = names.find((name) => name === "qwen3:8b") ?? names.find((name) => name === "qwen3-vl:4b") ?? names[0];
        setOllamaModel(preferred);
      }
      setProviderTest((state) => ({ ...state, ollama: { message: `${names.length} local model${names.length === 1 ? "" : "s"} found`, status: "pass" } }));
    } catch (error) {
      setProviderTest((state) => ({ ...state, ollama: { message: error instanceof Error ? error.message : "Ollama is unreachable", status: "fail" } }));
    }
  }

  async function testProviderConnection(id: "sarvam" | "gemini" | "grok" | "ollama") {
    setProviderTest((state) => ({ ...state, [id]: { message: "Testing connection…", status: "pending" } }));
    try {
      const body = await jsonFetch(`/provider/test?provider=${id}`, { method: "POST", headers: requestHeaders() });
      if (body.ok || body.usable) {
        const latency = body.latency_ms ? ` (${body.latency_ms} ms)` : "";
        const speed = body.details?.tokens_per_sec ? ` · ${body.details.tokens_per_sec} tok/s` : "";
        setProviderTest((state) => ({
          ...state,
          [id]: { message: `Connected · ${body.model}${latency}${speed}`, status: "pass" },
        }));
      } else {
        const code = body.error_code ? `[${body.error_code}] ` : "";
        setProviderTest((state) => ({
          ...state,
          [id]: { message: `${code}${body.error_message || "Test failed"}`, status: "fail" },
        }));
      }
    } catch (error) {
      setProviderTest((state) => ({
        ...state,
        [id]: { message: error instanceof Error ? error.message : "Connection failed", status: "fail" },
      }));
    }
  }
  function saveSettings() {
    try {
      // Security: never persist API keys in localStorage
      localStorage.removeItem("bhoomilens_sarvam_key");
      localStorage.removeItem("bhoomilens_gemini_key");
      localStorage.removeItem("bhoomilens_grok_key");
      localStorage.setItem("bhoomilens_ollama_url", ollamaBaseUrl);
      localStorage.setItem("bhoomilens_ollama_model", ollamaModel);
    } catch {}
    setSettingsOpen(false);
    setUploadStatus("Preferences saved. API keys remain in-memory for this session only.");
  }

  function requestHeaders() {
    return {
      ...(apiKeys.sarvam ? { "X-Sarvam-Api-Key": apiKeys.sarvam } : {}),
      ...(apiKeys.gemini ? { "X-Gemini-Api-Key": apiKeys.gemini } : {}),
      ...(apiKeys.grok ? { "X-Grok-Api-Key": apiKeys.grok } : {}),
      ...(ollamaBaseUrl ? { "X-Ollama-Base-Url": ollamaBaseUrl } : {}),
      ...(ollamaModel ? { "X-Ollama-Model": ollamaModel } : {}),
    };
  }

  function resolvedProvider(): Provider {
    if (provider !== "auto") return provider;
    if (apiKeys.sarvam) return "sarvam";
    if (apiKeys.gemini) return "gemini";
    if (apiKeys.grok) return "grok";
    if (ollamaBaseUrl && ollamaModel) return "ollama";
    return "mock";
  }

  function providerConfigured(id: Provider) {
    if (id === "auto" || id === "mock") return true;
    if (id === "sarvam") return Boolean(apiKeys.sarvam);
    if (id === "gemini") return Boolean(apiKeys.gemini);
    if (id === "grok") return Boolean(apiKeys.grok);
    if (id === "ollama" || id === "local") return Boolean(ollamaBaseUrl && ollamaModel);
    return false;
  }

  useEffect(() => {
    if (ollamaBaseUrl) refreshOllamaModels();
  }, [ollamaBaseUrl]);

  useEffect(() => {
    Promise.all([
      jsonFetch("/demo/case"),
      jsonFetch("/config"),
    ])
      .then(([demo, config]) => {
        setData(demo);
        setProviders(config.providers ?? []);
        setProvider((config.default_provider as Provider) ?? "auto");
      })
      .catch((error) => {
        setUploadStatus(
          error instanceof Error
            ? `Backend unavailable: ${error.message}`
            : "Backend unavailable."
        );
      });
  }, []);

  const finding = useMemo(
    () =>
      data?.findings.find((item) => item.id === activeFinding) ??
      data?.findings[0],
    [activeFinding, data]
  );

  useEffect(() => {
    setActiveEvidence(finding?.evidence[0] ?? null);
  }, [finding]);

  function openEvidence(evidence: Evidence) {
    setActiveEvidence(evidence);
  }

  function handleFileSelect(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    setSelectedFiles(files);
    setUploadStatus(
      files.length
        ? `${files.length} document${files.length > 1 ? "s" : ""} ready for analysis.`
        : ""
    );
  }

  async function startAnalysis() {
    if (!selectedFiles.length) {
      uploadInputRef.current?.click();
      return;
    }

    setAnalysisRunning(true);
    setExplanation("");
    setAnswer("");

    try {
      let activeCaseId = caseId;

      if (!activeCaseId) {
        const created = await jsonFetch("/cases", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...requestHeaders() },
          body: JSON.stringify({
            name: `Property review — ${new Date().toLocaleDateString("en-IN")}`,
          }),
        });
        activeCaseId = created.id;
        setCaseId(activeCaseId);
      }

      const form = new FormData();
      selectedFiles.forEach((file) => form.append("files", file));

      setUploadStatus("Uploading document bundle…");
      await jsonFetch(`/cases/${activeCaseId}/documents`, {
        method: "POST",
        body: form,
        headers: requestHeaders(),
      });

      setUploadStatus("Reconciliation queued…");
      await jsonFetch(
        `/cases/${activeCaseId}/analyze?reasoning_provider=${resolvedProvider()}`,
        { method: "POST", headers: requestHeaders() }
      );

      let completed = false;
      for (let attempt = 0; attempt < 80; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        const caseState = await jsonFetch(`/cases/${activeCaseId}`);

        if (caseState.documents) {
          const docs = Object.values(caseState.documents) as {
            id: string;
            filename: string;
            stage?: string;
            status?: string;
            page_count?: number;
            normalized?: { document_type?: string };
            extracted?: { document_type?: string };
          }[];
          setDiagnostics(
            docs.map((doc) => ({
              id: doc.id,
              filename: doc.filename,
              type: doc.normalized?.document_type || doc.extracted?.document_type || "Detecting…",
              stage: doc.stage || doc.status || "processing",
              status: doc.status || "processing",
              pageCount: doc.page_count || 1,
            }))
          );
        }

        if (caseState.status === "completed") {
          const dashboard = await jsonFetch(
            `/cases/${activeCaseId}/dashboard`
          );
          setData(dashboard);
          setActiveFinding(dashboard.findings?.[0]?.id ?? "");
          setUploadStatus(
            `Analysis complete · ${dashboard.documents} documents reconciled.`
          );
          completed = true;
          break;
        }

        if (caseState.status === "failed") {
          const errCode = caseState.analysis?.error_code ? `[${caseState.analysis.error_code}] ` : "";
          const stageInfo = caseState.stage ? ` (at stage: ${caseState.stage})` : "";
          throw new Error(
            `${errCode}${caseState.analysis?.error ?? "Document analysis failed"}${stageInfo}`
          );
        }

        const stage = caseState.stage || caseState.status;
        const stageLabels: Record<string, string> = {
          queued: "Reconciliation queued…",
          detecting_document: "Detecting document layout & structure…",
          extracting_text: "Extracting machine-readable text…",
          ocr_fallback: "Running OCR / visual document extraction fallback…",
          sarvam_extraction: "Processing with Sarvam Document AI…",
          ai_extraction: "Extracting land record entities with AI…",
          normalizing: "Normalizing entities & running cross-record reconciliation…",
          processing: "Reconciling records…",
        };
        const label = stageLabels[stage] || `Processing (${stage})…`;
        setUploadStatus(`${label} (${attempt + 1}/80)`);
      }

      if (!completed) {
        throw new Error(
          "Analysis timed out after 120s. Check provider connection and retry."
        );
      }
    } catch (error) {
      setUploadStatus(
        error instanceof Error ? error.message : "Analysis failed"
      );
    } finally {
      setAnalysisRunning(false);
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
      const context = {
        property: data?.property,
        findings: data?.findings,
        coverage: data?.coverage,
        timeline: data?.timeline,
      };

      const body = await jsonFetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...requestHeaders() },
        body: JSON.stringify({
          message: `${question}\n\nCASE EVIDENCE:\n${JSON.stringify(context)}`,
          provider,
        }),
      });

      setAnswer(body.answer);
    } catch (error) {
      setAnswer(error instanceof Error ? error.message : "The AI request failed.");
    } finally {
      setBusy(false);
    }
  }

  async function explainFinding() {
    if (!finding || !caseId) {
      setExplanation(
        "Run a document analysis first. The explanation layer will then use the selected provider against the stored evidence."
      );
      return;
    }

    setExplaining(true);
    setExplanation("");

    try {
      const body = await jsonFetch(`/cases/${caseId}/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...requestHeaders() },
        body: JSON.stringify({ provider, finding }),
      });
      setExplanation(body.answer);
    } catch (error) {
      setExplanation(
        error instanceof Error ? error.message : "Could not explain this finding."
      );
    } finally {
      setExplaining(false);
    }
  }

  async function downloadPdfReport() {
    if (!caseId) return;
    setReporting(true);
    try {
      const response = await fetch(`${API_BASE}/cases/${caseId}/report/pdf`);
      if (!response.ok) throw new Error("Could not generate PDF report.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `bhoomilens-${caseId}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setUploadStatus(error instanceof Error ? error.message : "Could not generate PDF report.");
    } finally {
      setReporting(false);
    }
  }

  async function downloadReport() {
    if (!caseId) return;
    setReporting(true);
    try {
      const response = await fetch(`${API_BASE}/cases/${caseId}/report`);
      if (!response.ok) throw new Error("Could not generate report.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `bhoomilens-${caseId}.txt`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setUploadStatus(error instanceof Error ? error.message : "Could not generate report.");
    } finally {
      setReporting(false);
    }
  }

  if (!data) {
    return <main className="page-shell loading-shell">Loading case workspace…</main>;
  }

  const extractedReady = data.extraction_status === "completed";

  return (
    <main className="page-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark">
            <Landmark size={18} strokeWidth={2.2} />
          </div>
          <div>
            <div className="brand-name">BhoomiLens</div>
            <div className="brand-sub">UP land records / India</div>
          </div>
        </div>

        <div className="topbar-actions">
          <div className="mode-pill">
            <span className="live-dot" /> UP screening mode
          </div>
          <button className="icon-button" aria-label="Language">
            <Languages size={18} />
          </button>
          <button className="icon-button settings-trigger" aria-label="AI settings" title="AI provider settings" onClick={() => setSettingsOpen(true)}>
            <Settings size={18} />
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
            </select>
          </div>
        </div>
      </header>

      <section className="hero-grid">
        <div className="hero-copy">
          <div className="eyebrow">
            <span>UP • PS41</span> Land-record risk &amp; reconciliation
          </div>
          <h1>
            Make property records
            <br />
            <em>agree with each other.</em>
          </h1>
          <p className="hero-text">
            Upload the records you actually have. BhoomiLens extracts the
            facts, normalizes names and Gata references, then shows exactly where
            the land-record story diverges.
          </p>

          <div className="hero-actions">
            {caseId && data.extraction_status === "completed" && (
              <button
                className="report-button"
                type="button"
                onClick={downloadPdfReport}
                disabled={reporting}
              >
                {reporting ? <LoaderCircle className="spin" size={16} /> : <Download size={16} />}
                Export PDF
              </button>
            )}
            <button
              className="primary-button"
              type="button"
              onClick={() => uploadInputRef.current?.click()}
              disabled={analysisRunning}
            >
              <UploadCloud size={17} /> Choose documents
            </button>
            <input
              ref={uploadInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              hidden
              multiple
              onChange={handleFileSelect}
            />
            <button
              className="ghost-button"
              type="button"
              onClick={startAnalysis}
              disabled={analysisRunning}
            >
              {analysisRunning ? (
                <LoaderCircle className="spin" size={17} />
              ) : (
                <ScanSearch size={17} />
              )}
              {analysisRunning ? "Analyzing bundle…" : "Analyze bundle"}
            </button>
          </div>

          <div className="up-record-strip">
            <span className="up-state-badge">UTTAR PRADESH</span>
            <span>Khatauni</span>
            <span>Gata / Khasra</span>
            <span>Mutation / Namantaran</span>
            <span>Sale Deed</span>
          </div>

          {selectedFiles.length > 0 && (
            <div className="selected-files">
              {selectedFiles.map((file) => (
                <div className="selected-file" key={`${file.name}-${file.size}`}>
                  <FileText size={13} />
                  <span>{file.name}</span>
                  <CheckCircle2 size={13} />
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="score-card">
          <div className="score-topline">
            <span>UP record consistency</span>
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
          <div className="score-note">Finding confidence: {Math.round((data.confidence ?? 1) * 100)}%</div>
          <div className="score-note">
            {extractedReady
              ? "Computed from structured comparisons across this case."
              : "UP demo dataset. Upload Khatauni, Gata/Khasra, mutation and deed records to run live reconciliation."}
          </div>
        </div>
      </section>

      {uploadStatus && (
        <div className="upload-status">
          {analysisRunning ? (
            <LoaderCircle className="spin" size={14} />
          ) : (
            <UploadCloud size={14} />
          )}
          {uploadStatus}
        </div>
      )}

      <section className="stats-strip">
        <Metric value={data.documents} label="documents analyzed" icon={<FileText size={16} />} />
        <Metric value={data.fields_extracted} label="fields extracted" icon={<ScanSearch size={16} />} />
        <Metric value={data.entities_normalized} label="entities normalized" icon={<ShieldCheck size={16} />} />
        <Metric value={data.findings.length} label="findings requiring review" icon={<CircleAlert size={16} />} />
      </section>

      <section className="workspace-grid">
        <div className="property-panel panel">
          <PanelTitle kicker="UP PROPERTY" title="Identity snapshot" />
          <div className="property-main">
            <span className="property-label">Gata / Khasra identifier</span>
            <strong>{data.property.survey}</strong>
            <span className="property-state-note">Uttar Pradesh · Revenue record context</span>
          </div>

          <div className="detail-grid">
            <Detail label="Recorded owner / Khatedar" value={data.property.owner} />
            <Detail label="Village / Gram" value={data.property.village} />
            <Detail label="Tehsil" value={data.property.taluk} />
            <Detail label="District / Janpad" value={data.property.district} />
          </div>

          <div className="coverage-block">
            <div className="mini-heading">UP DOCUMENT COVERAGE</div>
            {data.coverage.map((item) => (
              <div className="coverage-row" key={item.name}>
                <span>{item.status === "present" ? "✓" : "?"}</span>
                <span>{item.name}</span>
                <small>{item.status === "present" ? "provided" : "missing"}</small>
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
            {data.findings.length ? (
              data.findings.map((item) => {
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
              })
            ) : (
              <div className="empty-findings">
                <CheckCircle2 size={18} />
                <strong>No contradictions detected yet.</strong>
                <span>Upload and analyze the document bundle to populate findings.</span>
              </div>
            )}
          </div>

          <div className="review-note">
            <Sparkles size={15} />
            UP-specific reconciliation rules detect contradictions. AI providers explain
            ambiguous findings rather than inventing facts outside supplied records.
          </div>
        </div>

        <div className="evidence-panel panel">
          <PanelTitle kicker="EVIDENCE" title="Show the source, not just the warning" />

          {finding ? (
            <>
              <div className="evidence-title">
                <span className={`severity-tag ${severityMeta[finding.severity].className}`}>
                  {severityMeta[finding.severity].label}
                </span>
                {finding.title}
              </div>

              <p className="evidence-summary">{finding.summary}</p>

              <div className="difference-callout">
                <span>Confidence</span>
                <strong>{Math.round((finding.confidence ?? 1) * 100)}%</strong>
              </div>

              <div className="evidence-grid">
                {finding.evidence.map((evidence, index) => {
                  const selected =
                    activeEvidence?.document_id === evidence.document_id &&
                    activeEvidence?.page === evidence.page &&
                    activeEvidence?.field === evidence.field;
                  return (
                    <button
                      className={`evidence-card ${selected ? "selected" : ""}`}
                      key={`${evidence.document}-${index}`}
                      type="button"
                      onClick={() => openEvidence(evidence)}
                      title="Open this source page"
                    >
                      <div className="evidence-card-top">
                        <FileCheck2 size={15} />
                        <span>{evidence.document}</span>
                        <span>p.{evidence.page}</span>
                      </div>
                      <div className="evidence-field">
                        {evidence.field.replaceAll("_", " ")}
                      </div>
                      <div className="evidence-value">
                        {typeof evidence.value === "string"
                          ? evidence.value
                          : JSON.stringify(evidence.value)}
                      </div>
                      <div className="evidence-open-label">
                        {selected ? "Source open" : "Open source page →"}
                      </div>
                    </button>
                  );
                })}
              </div>

              {activeEvidence?.document_id && caseId && (
                <div className="source-viewer">
                  <div className="source-viewer-head">
                    <div>
                      <div className="mini-heading">SOURCE VIEWER</div>
                      <strong>{activeEvidence.document} · page {activeEvidence.page}</strong>
                    </div>
                    <span>
                      {activeEvidence.anchor ? "Visual anchor found" : "Source page"}
                    </span>
                  </div>
                  <div className="source-page">
                    <img
                      className="source-page-image"
                      src={`${API_BASE}/cases/${caseId}/documents/${activeEvidence.document_id}/page/${activeEvidence.page}`}
                      alt={`${activeEvidence.document} page ${activeEvidence.page}`}
                    />
                    {activeEvidence.anchor && (
                      <div
                        className="source-highlight"
                        style={{
                          left: `${(activeEvidence.anchor.bbox[0] / activeEvidence.anchor.page_width) * 100}%`,
                          top: `${(activeEvidence.anchor.bbox[1] / activeEvidence.anchor.page_height) * 100}%`,
                          width: `${((activeEvidence.anchor.bbox[2] - activeEvidence.anchor.bbox[0]) / activeEvidence.anchor.page_width) * 100}%`,
                          height: `${((activeEvidence.anchor.bbox[3] - activeEvidence.anchor.bbox[1]) / activeEvidence.anchor.page_height) * 100}%`,
                        }}
                        title={activeEvidence.anchor.text || activeEvidence.field}
                      />
                    )}
                  </div>
                  <div className="source-viewer-note">
                    {activeEvidence.anchor
                      ? "The highlighted region is a deterministic text anchor matched against the stored source page."
                      : "The source page is available, but no deterministic text anchor was found for this evidence value. Scanned-document visual anchoring can be added through Sarvam Digitise."}
                  </div>
                </div>
              )}
              <div className="difference-callout">
                <span>Verify next</span>
                <strong>{finding.verification_action || "Review the original source records."}</strong>
              </div>

              <div className="difference-callout">
                <span>Difference</span>
                <strong>
                  {finding.evidence.length
                    ? finding.evidence.map((item) =>
                        typeof item.value === "string"
                          ? item.value
                          : JSON.stringify(item.value)
                      ).join("  ≠  ")
                    : "Evidence relationship requires review"}
                </strong>
              </div>

              <button
                className="explain-button"
                type="button"
                onClick={explainFinding}
                disabled={explaining}
              >
                {explaining ? (
                  <LoaderCircle className="spin" size={15} />
                ) : (
                  <Sparkles size={15} />
                )}
                {explaining
                  ? `Explaining with ${provider}…`
                  : `Explain this finding with ${provider}`}
              </button>

              {explanation && (
                <div className="explanation-box">
                  <div className="answer-label">{provider.toUpperCase()} EXPLANATION</div>
                  {explanation}
                </div>
              )}
            </>
          ) : (
            <div className="empty-evidence">Select a finding to inspect its source evidence.</div>
          )}
        </div>

        <div className="timeline-panel panel">
          <PanelTitle
            kicker="OWNERSHIP THREAD"
            title="Apparent record timeline"
            action={<span className="muted-label">reconstructed</span>}
          />
          <div className="timeline">
            {data.timeline.length ? (
              data.timeline.map((item) => (
                <div className="timeline-row" key={`${item.date}-${item.label}`}>
                  <div className="timeline-date">{item.date}</div>
                  <div className="timeline-pin"><span /></div>
                  <div className="timeline-copy">
                    <strong>{item.label}</strong>
                    <span>{item.type}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="empty-timeline">
                Timeline events will appear when date-bearing records are extracted.
              </div>
            )}
          </div>
        </div>
      </section>

      {diagnostics && diagnostics.length > 0 && (
        <section className="diagnostics-panel panel">
          <PanelTitle
            kicker="PROCESSING AUDIT"
            title="Document pipeline diagnostics"
            action={<span className="count-badge">{diagnostics.length} documents</span>}
          />
          <div className="diagnostics-table-wrap">
            <table className="diagnostics-table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Detected record type</th>
                  <th>Processing stage</th>
                  <th>Pages</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {diagnostics.map((diag) => (
                  <tr key={diag.id}>
                    <td><strong>{diag.filename}</strong></td>
                    <td>{diag.type}</td>
                    <td><code>{diag.stage}</code></td>
                    <td>{diag.pageCount}</td>
                    <td>
                      <span
                        className={`status-pill ${
                          diag.status === "completed"
                            ? "pill-pass"
                            : diag.status === "failed"
                            ? "pill-fail"
                            : "pill-pending"
                        }`}
                      >
                        {diag.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="assistant-panel panel">
        <div className="assistant-left">
          <div className="assistant-orbit"><MessageCircle size={21} /></div>
          <div>
            <div className="mini-heading">ASK THE RECORDS</div>
            <h2>Evidence-grounded assistant</h2>
            <p>Ask what changed, why an item was flagged, or which record supports it.</p>
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
                disabled={!providerConfigured(item.id as Provider) && item.id !== "mock"}
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

      {settingsOpen && (
        <div className="settings-backdrop" onClick={() => setSettingsOpen(false)}>
          <section className="settings-modal" onClick={(event) => event.stopPropagation()}>
            <div className="settings-head">
              <div><div className="mini-heading">AI CONNECTIONS</div><h2>Provider settings</h2></div>
              <button className="icon-button" onClick={() => setSettingsOpen(false)} aria-label="Close settings">×</button>
            </div>
            <p className="settings-note">Keys are stored in this browser and sent to the backend only when that provider is used.</p>
            <ProviderKey label="Sarvam AI API key" value={apiKeys.sarvam} onChange={(value) => setApiKeys((state) => ({ ...state, sarvam: value }))} />
            <button className="ghost-button" type="button" onClick={() => testProviderConnection("sarvam")}>Test Sarvam</button>
            {providerTest.sarvam && <div className={`settings-diag ${providerTest.sarvam.status}`}>{providerTest.sarvam.message}</div>}
            <ProviderKey label="Gemini API key" value={apiKeys.gemini} onChange={(value) => setApiKeys((state) => ({ ...state, gemini: value }))} />
            <button className="ghost-button" type="button" onClick={() => testProviderConnection("gemini")}>Test Gemini</button>
            {providerTest.gemini && <div className={`settings-diag ${providerTest.gemini.status}`}>{providerTest.gemini.message}</div>}
            <ProviderKey label="Grok API key" value={apiKeys.grok} onChange={(value) => setApiKeys((state) => ({ ...state, grok: value }))} />
            <div className="settings-divider" />
            <div className="settings-section-title">Ollama Local</div>
            <label className="settings-field"><span>Base URL</span><input value={ollamaBaseUrl} onChange={(e) => setOllamaBaseUrl(e.target.value)} placeholder="http://localhost:11434" /></label>
            <div className="settings-actions"><button className="ghost-button" type="button" onClick={refreshOllamaModels}>Refresh models</button><button className="ghost-button" type="button" onClick={() => testProviderConnection("ollama")}>Test Ollama</button></div>
            {ollamaModels.length > 0 ? (
              <label className="settings-field"><span>Model</span><select value={ollamaModel} onChange={(e) => setOllamaModel(e.target.value)}>{ollamaModels.map((name) => <option key={name}>{name}</option>)}</select></label>
            ) : (
              <label className="settings-field"><span>Model</span><input value={ollamaModel} onChange={(e) => setOllamaModel(e.target.value)} placeholder="qwen3:8b" /></label>
            )}
            {providerTest.ollama && <div className={`settings-diag ${providerTest.ollama.status}`}>{providerTest.ollama.message}</div>}
            <div className="settings-actions"><button className="ghost-button" onClick={() => setSettingsOpen(false)}>Cancel</button><button className="primary-button" onClick={saveSettings}>Save settings</button></div>
          </section>
        </div>
      )}
      <footer className="footer-note">
        AI-assisted document screening only · Verify material findings against authoritative records and qualified professionals.
      </footer>
    </main>
  );
}

function Metric({ value, label, icon }: { value: number; label: string; icon: ReactNode }) {
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

function ProviderKey({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="settings-field"><span>{label}</span><input type="password" value={value} onChange={(event) => onChange(event.target.value)} placeholder="Paste API key" autoComplete="off" /></label>;
}
