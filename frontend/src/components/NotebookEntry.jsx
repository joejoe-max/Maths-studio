import React from 'react';
import { motion } from 'motion/react';
import { Trash2, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import DerivationBlock from './DerivationBlock';
import DiagramRenderer from './DiagramRenderer';

const MD_COMPONENTS = {
  h1: ({ children }) => <h1 className="text-xl font-black tracking-tight text-slate-100 mt-6 mb-3 uppercase">{children}</h1>,
  h2: ({ children }) => <h2 className="text-base font-black tracking-tight text-slate-100 mt-5 mb-2 uppercase">{children}</h2>,
  h3: ({ children }) => <h3 className="text-[10px] font-black uppercase tracking-[0.3em] text-blue-400 mt-5 mb-3">{children}</h3>,
  p: ({ children }) => <p className="text-sm text-slate-300 leading-relaxed mb-3">{children}</p>,
  ul: ({ children }) => <ul className="space-y-1.5 mb-4 ml-1">{children}</ul>,
  ol: ({ children }) => <ol className="space-y-1.5 mb-4 list-decimal ml-4">{children}</ol>,
  li: ({ children }) => <li className="text-sm text-slate-300 leading-relaxed pl-1">{children}</li>,
  strong: ({ children }) => <strong className="font-bold text-slate-100">{children}</strong>,
  code: ({ children }) => <code className="bg-white/5 px-1.5 py-0.5 rounded text-xs font-mono text-blue-300 border border-white/5">{children}</code>,
  hr: () => <div className="my-5 border-t border-white/5" />,
};

function DomainBadge({ domain }) {
  const colorMap = {
    algebra: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
    calculus: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
    structural: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    mechanics: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    thermo: 'bg-red-500/10 text-red-400 border-red-500/20',
    circuits: 'bg-green-500/10 text-green-400 border-green-500/20',
    fluids: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    calculus_engine: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
  };
  const cls = colorMap[domain?.toLowerCase?.()] || 'bg-slate-500/10 text-slate-400 border-slate-500/20';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-wider border ${cls}`}>
      {domain}
    </span>
  );
}

function SectionHeader({ title }) {
  return (
    <div className="flex items-center gap-3 my-5">
      <div className="h-px flex-1 bg-[#1d1e2c]" />
      <span className="text-[9px] font-black uppercase tracking-[0.3em] text-slate-600">{title}</span>
      <div className="h-px flex-1 bg-[#1d1e2c]" />
    </div>
  );
}

function VerificationPanel({ data }) {
  const allPassed = data.checks?.every(c => c.passed) && data.passed;
  return (
    <div className={`rounded-lg border p-3.5 mt-3 ${allPassed ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-red-500/20 bg-red-500/5'}`}>
      <div className="flex items-center gap-2 mb-2">
        {allPassed ? (
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
        ) : (
          <AlertCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />
        )}
        <span className={`text-[10px] font-black uppercase tracking-widest ${allPassed ? 'text-emerald-400' : 'text-red-400'}`}>
          {allPassed ? 'Solution verified' : 'Verification failed'}
        </span>
      </div>
      <div className="space-y-1">
        {data.checks?.map((check, i) => (
          <div key={i} className="flex items-start gap-2">
            <span className={`text-[10px] mt-0.5 ${check.passed ? 'text-emerald-400' : 'text-red-400'}`}>
              {check.passed ? '✓' : '✗'}
            </span>
            <span className="text-[11px] text-slate-400 font-mono leading-relaxed">{check.detail}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SummaryBox({ summary }) {
  if (!summary || summary.length === 0) return null;
  return (
    <div className="mt-5 p-4 rounded-lg bg-[#0f1018] border border-blue-500/20">
      <div className="text-[9px] font-black uppercase tracking-[0.3em] text-blue-400 mb-3">Result Summary</div>
      <div className="flex flex-wrap gap-4">
        {summary.map((item, i) => (
          <div key={i} className="min-w-[80px]">
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

function FinalAnswer({ text }) {
  if (!text) return null;
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="mt-5 pt-5 border-t border-[#1d1e2c]"
    >
      <div className="flex items-center gap-2 mb-4">
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        <span className="text-[9px] font-black uppercase tracking-[0.3em] text-emerald-400/70">
          Complete Solution
        </span>
      </div>
      <div className="prose prose-sm max-w-none">
        <ReactMarkdown
          remarkPlugins={[remarkMath]}
          rehypePlugins={[rehypeKatex]}
          components={MD_COMPONENTS}
        >
          {text}
        </ReactMarkdown>
      </div>
    </motion.div>
  );
}

function LegacySteps({ steps }) {
  if (!steps || steps.length === 0) return null;
  const visible = steps.filter(s => s && s.trim() && !s.startsWith('Initializing '));
  if (visible.length === 0) return null;
  return (
    <div className="space-y-2 mt-4">
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

export default function NotebookEntry({ entry, index, onDelete }) {
  const { query, domain, events, diagrams, final, summary, steps, isProcessing, error } = entry;

  // Group events in order for rendering
  const renderContent = () => {
    const elements = [];
    let diagramIdx = 0;

    if (events && events.length > 0) {
      for (let i = 0; i < events.length; i++) {
        const evt = events[i];

        if (evt.type === 'section') {
          elements.push(<SectionHeader key={`sec_${i}`} title={evt.title} />);
        } else if (evt.type === 'derivation_step') {
          elements.push(
            <DerivationBlock key={`deriv_${i}`} step={evt} />
          );
        } else if (evt.type === 'equation_state') {
          elements.push(
            <motion.div
              key={`eq_${i}`}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              className="my-3 flex items-start gap-3"
            >
              <div className="w-1 h-1 rounded-full bg-blue-500/60 mt-3 shrink-0" />
              <div>
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
        } else if (evt.type === 'verification') {
          elements.push(<VerificationPanel key={`verify_${i}`} data={evt} />);
        }
        // problem_parsed: rendered as domain badge in header, skip here
      }
    }

    // Interleave diagrams
    if (diagrams && diagrams.length > 0) {
      for (const diagram of diagrams) {
        elements.push(
          <DiagramRenderer key={`diagram_${diagramIdx++}_${diagram.diagram_type}`} diagram={diagram} />
        );
      }
    }

    return elements;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative"
    >
      {/* Entry number */}
      <div className="flex items-center gap-3 mb-4">
        <div className="text-[9px] font-mono text-slate-700 w-5 text-right shrink-0">
          [{String(index + 1).padStart(2, '0')}]
        </div>
        <div className="h-px flex-1 bg-[#1a1b27]" />
      </div>

      {/* Query line */}
      <div className="flex items-start gap-3 mb-5">
        <div className="w-5 shrink-0 flex justify-end">
          <span className="text-[10px] font-mono text-blue-400/60 mt-0.5">In:</span>
        </div>
        <div className="flex-1">
          <div className="font-mono text-sm text-slate-300 leading-relaxed">{query}</div>
          {domain && (
            <div className="mt-1.5">
              <DomainBadge domain={domain} />
            </div>
          )}
        </div>
        <button
          onClick={onDelete}
          className="p-1 rounded hover:bg-white/5 text-slate-700 hover:text-slate-400 transition-colors shrink-0"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>

      {/* Output area */}
      <div className="flex gap-3">
        <div className="w-5 shrink-0 flex justify-end">
          <span className="text-[10px] font-mono text-emerald-500/60 mt-0.5">Out:</span>
        </div>
        <div className="flex-1 min-w-0">

          {/* Processing indicator */}
          {isProcessing && (
            <div className="flex items-center gap-2 py-2">
              <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />
              <span className="text-[10px] font-mono text-slate-600 uppercase tracking-widest">Computing…</span>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-red-500/5 border border-red-500/20">
              <AlertCircle className="w-3.5 h-3.5 text-red-400 shrink-0 mt-0.5" />
              <span className="text-xs text-red-400">{error}</span>
            </div>
          )}

          {/* Rich derivation events */}
          {renderContent()}

          {/* Legacy steps (fallback for domains not yet upgraded) */}
          {(!events || events.length === 0) && steps && steps.length > 0 && (
            <LegacySteps steps={steps} />
          )}

          {/* Summary box */}
          <SummaryBox summary={summary} />

          {/* Final answer */}
          <FinalAnswer text={final} />
        </div>
      </div>
    </motion.div>
  );
}
