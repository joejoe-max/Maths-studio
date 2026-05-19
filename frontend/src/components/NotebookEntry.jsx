import React, { useState } from 'react';
import { motion } from 'motion/react';
import { Trash2, AlertCircle, CheckCircle2, XCircle, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import DerivationBlock from './DerivationBlock';
import DiagramRenderer from './DiagramRenderer';

// ── Markdown components: equation-first, minimal prose ─────────────────────

const RESULT_MD = {
  h1: ({ children }) => (
    <h1 className="text-sm font-black tracking-tight text-slate-100 mt-4 mb-2 uppercase border-b border-[#1d1e2c] pb-1">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-xs font-black tracking-tight text-slate-200 mt-3 mb-1.5 uppercase">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-[10px] font-black uppercase tracking-[0.3em] text-blue-400/80 mt-3 mb-2">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="text-xs text-slate-400 leading-relaxed mb-2">{children}</p>
  ),
  ul: ({ children }) => <ul className="space-y-1 mb-3 ml-1">{children}</ul>,
  ol: ({ children }) => <ol className="space-y-1 mb-3 list-decimal ml-4">{children}</ol>,
  li: ({ children }) => <li className="text-xs text-slate-400 leading-relaxed pl-1">{children}</li>,
  strong: ({ children }) => <strong className="font-bold text-slate-100">{children}</strong>,
  em: ({ children }) => <em className="text-slate-300 not-italic">{children}</em>,
  code: ({ children }) => (
    <code className="bg-white/5 px-1.5 py-0.5 rounded text-xs font-mono text-blue-300 border border-white/5">{children}</code>
  ),
  hr: () => <div className="my-3 border-t border-white/5" />,
  blockquote: ({ children }) => (
    <div className="border-l-2 border-blue-500/40 pl-3 my-2 text-xs text-slate-400">{children}</div>
  ),
};

// ── Sub-components ──────────────────────────────────────────────────────────

function DomainBadge({ domain }) {
  const colorMap = {
    algebra:     'bg-violet-500/10 text-violet-400 border-violet-500/20',
    calculus:    'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
    structural:  'bg-amber-500/10  text-amber-400  border-amber-500/20',
    mechanics:   'bg-orange-500/10 text-orange-400 border-orange-500/20',
    thermo:      'bg-red-500/10    text-red-400    border-red-500/20',
    circuits:    'bg-green-500/10  text-green-400  border-green-500/20',
    fluids:      'bg-blue-500/10   text-blue-400   border-blue-500/20',
    statistics:  'bg-cyan-500/10   text-cyan-400   border-cyan-500/20',
    matrix:      'bg-purple-500/10 text-purple-400 border-purple-500/20',
    data_viz:    'bg-teal-500/10   text-teal-400   border-teal-500/20',
  };
  const cls = colorMap[domain?.toLowerCase?.()] || 'bg-slate-500/10 text-slate-400 border-slate-500/20';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-wider border ${cls}`}>
      {domain}
    </span>
  );
}

function MethodBadge({ method }) {
  if (!method) return null;
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider border border-blue-500/20 bg-blue-500/5 text-blue-400/80 ml-1.5">
      {method}
    </span>
  );
}

function SectionHeader({ title }) {
  return (
    <div className="flex items-center gap-3 my-4">
      <div className="h-px flex-1 bg-[#1d1e2c]" />
      <span className="text-[9px] font-black uppercase tracking-[0.3em] text-slate-600">{title}</span>
      <div className="h-px flex-1 bg-[#1d1e2c]" />
    </div>
  );
}

function EquationState({ evt }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      className="my-2.5 flex items-start gap-3"
    >
      <div className="w-1 h-1 rounded-full bg-blue-500/50 mt-3 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="px-4 py-2.5 rounded-md bg-[#0d0e18] border border-[#1d1e2c] font-mono text-sm overflow-x-auto">
          <ReactMarkdown
            remarkPlugins={[remarkMath]}
            rehypePlugins={[rehypeKatex]}
            components={{ p: ({ children }) => <span className="text-slate-200">{children}</span> }}
          >
            {`$${evt.latex}$`}
          </ReactMarkdown>
        </div>
        {evt.label && (
          <div className="text-[10px] text-slate-600 font-mono mt-1 ml-1">{evt.label}</div>
        )}
      </div>
    </motion.div>
  );
}

function VerificationPanel({ data }) {
  const allPassed = data.checks?.every(c => c.passed) !== false && data.passed !== false;
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-lg border p-3 mt-3 ${allPassed ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-amber-500/20 bg-amber-500/5'}`}
    >
      <div className="flex items-center gap-2 mb-2">
        {allPassed
          ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          : <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
        }
        <span className={`text-[10px] font-black uppercase tracking-widest ${allPassed ? 'text-emerald-400' : 'text-amber-400'}`}>
          {allPassed ? 'Verified ✓' : 'Verification warning'}
        </span>
      </div>
      {data.checks?.length > 0 && (
        <div className="space-y-1 mt-1">
          {data.checks.map((check, i) => (
            <div key={i} className="flex items-start gap-2">
              <span className={`text-[10px] mt-0.5 font-mono ${check.passed ? 'text-emerald-400' : 'text-amber-400'}`}>
                {check.passed ? '✓' : '!'}
              </span>
              <span className="text-[11px] text-slate-400 font-mono leading-relaxed">{check.detail}</span>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

function SummaryBox({ summary }) {
  if (!summary || summary.length === 0) return null;
  return (
    <div className="mt-4 p-3.5 rounded-lg bg-[#0f1018] border border-blue-500/20">
      <div className="text-[9px] font-black uppercase tracking-[0.3em] text-blue-400 mb-3">Key Results</div>
      <div className="flex flex-wrap gap-5">
        {summary.map((item, i) => (
          <div key={i} className="min-w-[72px]">
            <div className="text-[10px] text-slate-500 font-mono mb-0.5">{item.label}</div>
            <div className="text-sm font-mono font-bold text-slate-100">
              {item.value}
              {item.unit && <span className="text-xs text-slate-500 ml-1">{item.unit}</span>}
            </div>
            {item.decimal !== undefined && item.decimal !== null && String(item.decimal) !== item.value && (
              <div className="text-[10px] text-slate-600 font-mono">≈ {parseFloat(item.decimal).toPrecision(6)}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ResultBlock({ text }) {
  if (!text) return null;
  const [expanded, setExpanded] = useState(false);
  const isLong = text.length > 800;
  const displayText = isLong && !expanded ? text.slice(0, 800) + '…' : text;

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-4 rounded-lg border border-[#1d1e2c] bg-[#0b0c15] overflow-hidden"
    >
      <div className="flex items-center gap-2 px-4 py-2 border-b border-[#1d1e2c] bg-[#0a0b14]">
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        <span className="text-[9px] font-black uppercase tracking-[0.3em] text-emerald-400/70">Result</span>
      </div>
      <div className="px-4 py-3">
        <ReactMarkdown
          remarkPlugins={[remarkMath]}
          rehypePlugins={[rehypeKatex]}
          components={RESULT_MD}
        >
          {displayText}
        </ReactMarkdown>
        {isLong && (
          <button
            onClick={() => setExpanded(v => !v)}
            className="mt-1 flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-300 transition-colors font-mono"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? 'Collapse' : 'Show full result'}
          </button>
        )}
      </div>
    </motion.div>
  );
}

function LegacySteps({ steps }) {
  if (!steps || steps.length === 0) return null;
  const visible = steps.filter(s => s && s.trim() && !s.startsWith('Initializing ') && s.length > 10);
  if (visible.length === 0) return null;
  return (
    <div className="space-y-2 mt-3">
      {visible.map((step, i) => (
        <div key={i} className="flex gap-3 items-start">
          <div className="w-1 h-1 rounded-full bg-slate-600 mt-2 shrink-0" />
          <div className="text-xs font-mono text-slate-400 leading-relaxed">
            <ReactMarkdown
              remarkPlugins={[remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={{
                p: ({ children }) => <span>{children}</span>,
                strong: ({ children }) => <strong className="text-slate-300">{children}</strong>,
              }}
            >
              {step}
            </ReactMarkdown>
          </div>
        </div>
      ))}
    </div>
  );
}

function ErrorBlock({ error }) {
  if (!error) return null;
  return (
    <div className="flex items-start gap-2.5 p-3 rounded-lg bg-red-500/5 border border-red-500/20">
      <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0 mt-0.5" />
      <div>
        <div className="text-[9px] font-black uppercase tracking-widest text-red-400 mb-1">Error</div>
        <span className="text-xs text-red-300/80 leading-relaxed">{error}</span>
      </div>
    </div>
  );
}

// ── Main component ──────────────────────────────────────────────────────────

export default function NotebookEntry({ entry, index, onDelete }) {
  const { query, domain, events, diagrams, final, summary, steps, method, isProcessing, error } = entry;

  const renderPipeline = () => {
    const elements = [];

    // ── LAYER 0: Diagrams first (visual grounding) ──────────────────────────
    if (diagrams && diagrams.length > 0) {
      elements.push(
        <div key="diagrams" className="mb-1">
          {diagrams.map((diagram, i) => (
            <DiagramRenderer key={`diag_${i}_${diagram.diagram_type}`} diagram={diagram} />
          ))}
        </div>
      );
    }

    // ── LAYER 1+2: Derivations and equations (in event order) ───────────────
    const derivationElements = [];
    const verificationElements = [];

    if (events && events.length > 0) {
      for (let i = 0; i < events.length; i++) {
        const evt = events[i];

        if (evt.type === 'section') {
          derivationElements.push(<SectionHeader key={`sec_${i}`} title={evt.title} />);
        } else if (evt.type === 'derivation_step') {
          derivationElements.push(<DerivationBlock key={`deriv_${i}`} step={evt} />);
        } else if (evt.type === 'equation_state') {
          derivationElements.push(<EquationState key={`eq_${i}`} evt={evt} />);
        } else if (evt.type === 'verification') {
          verificationElements.push(<VerificationPanel key={`verify_${i}`} data={evt} />);
        }
        // problem_parsed: shown in header as domain badge — skip here
      }
    }

    if (derivationElements.length > 0) {
      elements.push(
        <div key="derivations" className="space-y-0.5">
          {derivationElements}
        </div>
      );
    }

    // Legacy steps fallback
    if (!events?.length && steps?.length > 0) {
      elements.push(<LegacySteps key="legacy" steps={steps} />);
    }

    // ── LAYER 3: Verification ───────────────────────────────────────────────
    if (verificationElements.length > 0) {
      elements.push(
        <div key="verifications" className="space-y-2">
          {verificationElements}
        </div>
      );
    }

    // ── LAYER 4: Key results summary ────────────────────────────────────────
    if (summary?.length > 0) {
      elements.push(<SummaryBox key="summary" summary={summary} />);
    }

    // ── LAYER 5: Result block (equation-first, minimal prose) ───────────────
    if (final) {
      elements.push(<ResultBlock key="result" text={final} />);
    }

    return elements;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative"
    >
      {/* Entry separator */}
      <div className="flex items-center gap-3 mb-4">
        <div className="text-[9px] font-mono text-slate-700 w-5 text-right shrink-0">
          [{String(index + 1).padStart(2, '0')}]
        </div>
        <div className="h-px flex-1 bg-[#1a1b27]" />
      </div>

      {/* Input line (Jupyter-style In[n]:) */}
      <div className="flex items-start gap-3 mb-4">
        <div className="w-5 shrink-0 flex justify-end pt-0.5">
          <span className="text-[10px] font-mono text-blue-400/50">In:</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-mono text-sm text-slate-200 leading-relaxed">{query}</div>
          <div className="flex items-center flex-wrap gap-1.5 mt-1.5">
            {domain && <DomainBadge domain={domain} />}
            {method && <MethodBadge method={method} />}
          </div>
        </div>
        <button
          onClick={onDelete}
          className="p-1 rounded hover:bg-white/5 text-slate-700 hover:text-slate-400 transition-colors shrink-0 mt-0.5"
          title="Remove entry"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>

      {/* Output area (Out:) */}
      <div className="flex gap-3">
        <div className="w-5 shrink-0 flex justify-end pt-0.5">
          <span className="text-[10px] font-mono text-emerald-500/50">Out:</span>
        </div>
        <div className="flex-1 min-w-0">

          {/* Computing indicator */}
          {isProcessing && (
            <div className="flex items-center gap-2 py-2">
              <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />
              <span className="text-[10px] font-mono text-slate-600 uppercase tracking-widest">Computing…</span>
            </div>
          )}

          {/* Error block */}
          {error && <ErrorBlock error={error} />}

          {/* Structured render pipeline */}
          {renderPipeline()}

        </div>
      </div>
    </motion.div>
  );
}
