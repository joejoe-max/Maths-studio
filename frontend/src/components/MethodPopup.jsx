import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Zap, X, CheckCircle2, ArrowRight } from 'lucide-react';

export default function MethodPopup({
  isOpen, methods, domain, problemDescription,
  onSelect, onAutoSelect, onCancel,
}) {
  const [selected, setSelected] = useState(null);

  if (!isOpen) return null;

  const handleContinue = () => {
    if (!selected) return;
    const m = selected;
    setSelected(null);
    onSelect(m.id || m.label);
  };

  const handleAuto = () => {
    setSelected(null);
    onAutoSelect();
  };

  const handleCancel = () => {
    setSelected(null);
    onCancel();
  };

  const domainColor = {
    algebra:    'text-violet-400  border-violet-500/30 bg-violet-500/5',
    calculus:   'text-indigo-400  border-indigo-500/30 bg-indigo-500/5',
    structural: 'text-amber-400   border-amber-500/30  bg-amber-500/5',
    mechanics:  'text-orange-400  border-orange-500/30 bg-orange-500/5',
    circuits:   'text-green-400   border-green-500/30  bg-green-500/5',
    thermo:     'text-red-400     border-red-500/30    bg-red-500/5',
    fluids:     'text-blue-400    border-blue-500/30   bg-blue-500/5',
    statistics: 'text-cyan-400    border-cyan-500/30   bg-cyan-500/5',
  }[domain] || 'text-slate-400 border-slate-500/30 bg-slate-500/5';

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) handleCancel(); }}
    >
      <motion.div
        initial={{ scale: 0.94, opacity: 0, y: 12 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.94, opacity: 0, y: 12 }}
        transition={{ type: 'spring', stiffness: 420, damping: 32 }}
        className="bg-[#0f1018] border border-[#1d1e2c] rounded-xl max-w-lg w-full shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-[#1d1e2c] bg-[#0a0b14]">
          <div className="flex items-start gap-3 flex-1">
            <div className="w-8 h-8 rounded-lg bg-blue-600/10 border border-blue-500/20 flex items-center justify-center shrink-0 mt-0.5">
              <Zap className="w-4 h-4 text-blue-400" />
            </div>
            <div>
              <h2 className="text-sm font-black uppercase tracking-tight text-slate-100">
                Select Solution Method
              </h2>
              <p className="text-[10px] mt-0.5 text-slate-500 font-mono">
                Choose a method — execution pauses until confirmed
              </p>
            </div>
          </div>
          <button
            onClick={handleCancel}
            className="p-1.5 rounded hover:bg-white/5 text-slate-600 hover:text-slate-300 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Problem description */}
        {problemDescription && (
          <div className="px-5 pt-4">
            <div className={`p-3 rounded-lg border text-[11px] font-mono leading-relaxed ${domainColor}`}>
              <span className="text-slate-500">Problem: </span>{problemDescription}
            </div>
          </div>
        )}

        {/* Methods grid */}
        <div className="px-5 py-4 space-y-2 max-h-[50vh] overflow-y-auto">
          <div className="text-[9px] font-black uppercase tracking-[0.3em] text-slate-600 mb-3">
            Available Methods
          </div>
          <AnimatePresence initial={false}>
            {(methods || []).map((method, idx) => {
              const methodId = method.id || method;
              const methodLabel = method.label || method;
              const methodDesc = method.desc || method.description || '';
              const isSelected = selected?.id === methodId || selected === method;

              return (
                <motion.button
                  key={methodId}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.03 }}
                  onClick={() => setSelected(method)}
                  className={`
                    w-full flex items-start gap-3 p-3.5 rounded-lg text-left transition-all border
                    ${isSelected
                      ? 'border-blue-500/40 bg-blue-500/8 shadow-sm'
                      : 'border-[#1d1e2c] bg-[#0c0d16] hover:border-[#2a2b3c] hover:bg-[#0e0f1c]'
                    }
                  `}
                >
                  {/* Index number */}
                  <div className={`
                    w-5 h-5 rounded shrink-0 mt-0.5 flex items-center justify-center text-[10px] font-black
                    ${isSelected ? 'bg-blue-600 text-white' : 'bg-white/5 text-slate-600'}
                  `}>
                    {isSelected ? <CheckCircle2 className="w-3 h-3" /> : idx + 1}
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className={`text-xs font-bold leading-tight ${isSelected ? 'text-slate-100' : 'text-slate-300'}`}>
                      {methodLabel}
                    </p>
                    {methodDesc && (
                      <p className="text-[10px] text-slate-600 mt-0.5 leading-snug font-mono">
                        {methodDesc}
                      </p>
                    )}
                  </div>

                  {idx === 0 && !isSelected && (
                    <span className="text-[9px] font-black uppercase tracking-wider text-blue-400/50 shrink-0 mt-0.5">
                      Recommended
                    </span>
                  )}
                </motion.button>
              );
            })}
          </AnimatePresence>
        </div>

        {/* Footer actions */}
        <div className="px-5 py-4 border-t border-[#1d1e2c] bg-[#0a0b14] flex gap-2">
          <button
            onClick={handleCancel}
            className="px-3.5 py-2 rounded-lg font-bold text-xs uppercase tracking-wider bg-white/5 hover:bg-white/8 border border-white/8 text-slate-500 hover:text-slate-300 transition-all"
          >
            Cancel
          </button>
          <button
            onClick={handleAuto}
            className="flex-1 flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg font-bold text-xs uppercase tracking-wider bg-white/5 hover:bg-white/8 border border-white/8 text-slate-400 hover:text-slate-200 transition-all"
          >
            <Zap className="w-3.5 h-3.5" />
            Auto Select
          </button>
          <button
            onClick={handleContinue}
            disabled={!selected}
            className={`
              flex-1 flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg font-bold text-xs uppercase tracking-wider transition-all
              ${selected
                ? 'bg-blue-600 text-white hover:bg-blue-500 shadow-lg shadow-blue-600/20'
                : 'bg-white/5 text-slate-700 cursor-not-allowed border border-white/5'
              }
            `}
          >
            Solve <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
