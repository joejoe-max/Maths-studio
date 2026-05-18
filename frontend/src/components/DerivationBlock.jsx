import React from 'react';
import { motion } from 'motion/react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

function Eq({ latex, dimmed = false }) {
  if (!latex) return null;
  return (
    <div className={`font-mono text-sm overflow-x-auto leading-relaxed ${dimmed ? 'text-slate-500' : 'text-slate-100'}`}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{ p: ({ children }) => <span>{children}</span> }}
      >
        {`$${latex}$`}
      </ReactMarkdown>
    </div>
  );
}

const OPERATION_LABELS = {
  expand: 'Expand',
  factor: 'Factorise',
  simplify: 'Simplify',
  differentiate: 'Differentiate',
  integrate: 'Integrate',
  moment_equilibrium_about_A: 'ΣM_A = 0',
  solve_R_B: 'Solve R_B',
  solve_R_A: 'Solve R_A',
  midspan_deflection: 'Max Deflection',
  tip_deflection: 'Tip Deflection',
  characteristic_polynomial: 'Char. Polynomial',
  elimination: 'Elimination',
  subtract_equations: 'Subtract Equations',
  back_substitution: 'Back-substitution',
  natural_frequency: 'Natural Frequency',
  carnot_efficiency: 'Carnot Efficiency',
  time_constant: 'Time Constant τ',
  total_impedance: 'Total Impedance',
};

export default function DerivationBlock({ step }) {
  const { operation, operation_label, from_latex, to_latex, note } = step;
  const displayLabel = operation_label || OPERATION_LABELS[operation] || operation?.replace(/_/g, ' ');

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="my-3 rounded-lg border border-[#1d1e2c] bg-[#0c0d16] overflow-hidden"
    >
      {/* Operation label header */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-[#1d1e2c] bg-[#0a0b14]">
        <div className="w-1.5 h-1.5 rounded-full bg-blue-500/60" />
        <span className="text-[10px] font-black uppercase tracking-widest text-blue-400/70">
          {displayLabel}
        </span>
      </div>

      {/* Before → After equations */}
      <div className="p-4">
        {from_latex && (
          <div className="mb-3">
            <div className="text-[9px] font-mono uppercase tracking-widest text-slate-700 mb-1.5">Before</div>
            <div className="pl-3 border-l border-slate-700/40">
              <Eq latex={from_latex} dimmed />
            </div>
          </div>
        )}

        {from_latex && to_latex && (
          <div className="flex items-center gap-2 my-2 ml-3">
            <div className="h-px w-4 bg-blue-500/30" />
            <svg className="w-3 h-3 text-blue-400/50" viewBox="0 0 12 12" fill="none">
              <path d="M2 6h8M7 3l3 3-3 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        )}

        {to_latex && (
          <div>
            <div className="text-[9px] font-mono uppercase tracking-widest text-slate-700 mb-1.5">After</div>
            <div className="pl-3 border-l border-blue-500/40">
              <Eq latex={to_latex} />
            </div>
          </div>
        )}

        {note && (
          <div className="mt-3 pt-3 border-t border-[#1d1e2c]">
            <span className="text-[11px] text-slate-500 italic leading-relaxed">{note}</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}
