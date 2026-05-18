import React, { useRef, useEffect } from 'react';
import { ArrowUp, Square } from 'lucide-react';

const PLACEHOLDER_EXAMPLES = [
  'Solve: 2x + 3y = 12, x - y = 1',
  'Differentiate x³ sin(x) with respect to x',
  'Simply supported beam L=5m, P=20kN at midspan',
  'RC circuit: R=1kΩ, C=10μF, V₀=5V',
  'Projectile: u=50m/s, θ=45°',
  'Carnot engine: T_H=600K, T_C=300K',
  'Eigenvalues of [[2,1],[1,2]]',
];

export default function EngineeringInput({ value, onChange, onSubmit, onStop, isProcessing }) {
  const textareaRef = useRef(null);
  const exampleRef = useRef(0);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 160) + 'px';
    }
  }, [value]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isProcessing && value.trim()) onSubmit();
    }
  };

  const placeholder = PLACEHOLDER_EXAMPLES[exampleRef.current % PLACEHOLDER_EXAMPLES.length];

  return (
    <div className="flex items-end gap-3">
      <div className="flex-1 relative">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={`e.g. ${placeholder}`}
          disabled={isProcessing}
          rows={1}
          className={`
            w-full resize-none bg-[#0f1018] border border-[#1d1e2c] rounded-lg
            px-4 py-3 text-sm text-slate-200 font-mono placeholder-slate-700
            focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20
            transition-all leading-relaxed
            ${isProcessing ? 'opacity-60 cursor-not-allowed' : ''}
          `}
          style={{ minHeight: 44, maxHeight: 160 }}
        />
        <div className="absolute bottom-2.5 right-2.5 flex items-center gap-1.5">
          <span className="text-[9px] font-mono text-slate-700 hidden sm:block">
            Shift+Enter for newline
          </span>
        </div>
      </div>

      <button
        onClick={isProcessing ? onStop : onSubmit}
        disabled={!isProcessing && !value.trim()}
        className={`
          flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center
          transition-all font-medium text-sm
          ${isProcessing
            ? 'bg-red-500/20 border border-red-500/30 text-red-400 hover:bg-red-500/30'
            : value.trim()
              ? 'bg-blue-600 text-white hover:bg-blue-500 shadow-lg shadow-blue-600/20'
              : 'bg-[#0f1018] border border-[#1d1e2c] text-slate-700 cursor-not-allowed'
          }
        `}
        title={isProcessing ? 'Stop' : 'Compute (Enter)'}
      >
        {isProcessing ? <Square className="w-3.5 h-3.5" /> : <ArrowUp className="w-4 h-4" />}
      </button>
    </div>
  );
}
