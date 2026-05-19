import React, { useState, useEffect, useRef } from 'react';
import { History, Trash2 } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import {
  saveComputation, getHistory, deleteHistoryItem,
  saveCurrentSession, loadCurrentSession, clearCurrentSession
} from './lib/db';
import NotebookWorkspace from './components/NotebookWorkspace';
import EngineeringInput from './components/EngineeringInput';
import NotebookSidebar from './components/NotebookSidebar';
import MethodPopup from './components/MethodPopup';
import { detectDomain, getMethodsForDomain, shouldShowMethodPopup } from './lib/methodDetector';

export default function App() {
  const [entries, setEntries] = useState([]);
  const [history, setHistory] = useState([]);
  const [inputText, setInputText] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [methodPopup, setMethodPopup] = useState({
    isOpen: false, methods: [], domain: null, problemDescription: '',
  });

  const abortRef = useRef(null);
  const scrollRef = useRef(null);
  const methodResolveRef = useRef(null);

  useEffect(() => {
    loadHistory();
    loadSession();
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
    if (entries.length > 0) saveCurrentSession(entries);
  }, [entries]);

  const loadSession = async () => {
    const saved = await loadCurrentSession();
    if (saved && Array.isArray(saved)) setEntries(saved);
  };

  const loadHistory = async () => {
    const data = await getHistory();
    setHistory(data.sort((a, b) => b.timestamp - a.timestamp));
  };

  // ── Method popup control ────────────────────────────────────────────────────

  const askForMethod = (domain, query) => {
    const methods = getMethodsForDomain(domain);
    if (!methods.length || !shouldShowMethodPopup(domain)) {
      return Promise.resolve(null);
    }
    return new Promise((resolve) => {
      methodResolveRef.current = resolve;
      setMethodPopup({
        isOpen: true,
        methods,
        domain,
        problemDescription: query.length > 120 ? query.slice(0, 120) + '…' : query,
      });
    });
  };

  const handleMethodSelect = (method) => {
    methodResolveRef.current?.(method);
    methodResolveRef.current = null;
    setMethodPopup(s => ({ ...s, isOpen: false }));
  };

  const handleMethodAutoSelect = () => {
    methodResolveRef.current?.(null);
    methodResolveRef.current = null;
    setMethodPopup(s => ({ ...s, isOpen: false }));
  };

  const handleMethodCancel = () => {
    methodResolveRef.current?.(false);
    methodResolveRef.current = null;
    setMethodPopup(s => ({ ...s, isOpen: false }));
  };

  // ── Compute ─────────────────────────────────────────────────────────────────

  const handleCompute = async () => {
    if (!inputText.trim() || isProcessing) return;
    const query = inputText.trim();
    setInputText('');

    // Detect domain → optionally pause for method selection
    const domain = detectDomain(query);
    let preferredMethod = null;

    if (domain) {
      const choice = await askForMethod(domain, query);
      if (choice === false) {
        // User cancelled — restore input
        setInputText(query);
        return;
      }
      preferredMethod = choice; // null = auto, string = specific method id
    }

    const ts = Date.now();
    const entryId = ts.toString();

    const newEntry = {
      id: entryId,
      query,
      domain: null,
      capabilities: [],
      events: [],
      diagrams: [],
      final: null,
      summary: [],
      steps: [],
      method: preferredMethod,
      isProcessing: true,
      error: null,
      timestamp: ts,
    };

    setEntries(prev => [...prev, newEntry]);
    setIsProcessing(true);
    abortRef.current = new AbortController();

    const supplemental = {};
    if (preferredMethod) supplemental.method = preferredMethod;

    const payload = {
      type: 'text',
      input: query,
      supplemental_params: supplemental,
      history: [],
    };

    try {
      const endpoint = `${import.meta.env.VITE_BACKEND_URL}/api/compute/solve`;
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
        body: JSON.stringify(payload),
        signal: abortRef.current.signal,
      });

      if (!response.ok || !response.body) {
        setEntries(prev => prev.map(e =>
          e.id === entryId
            ? { ...e, error: `Engine unavailable (HTTP ${response.status}).`, isProcessing: false }
            : e
        ));
        setIsProcessing(false);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();

        for (const part of parts) {
          if (!part.startsWith('data: ')) continue;
          let data;
          try { data = JSON.parse(part.slice(6)); } catch { continue; }

          setEntries(prev => prev.map(e => {
            if (e.id !== entryId) return e;

            // Rich structured event types
            if (
              data.type === 'derivation_step' ||
              data.type === 'equation_state' ||
              data.type === 'section' ||
              data.type === 'verification'
            ) {
              return { ...e, events: [...(e.events || []), data] };
            }

            if (data.type === 'problem_parsed') {
              return {
                ...e,
                domain: data.domain,
                capabilities: data.capabilities || [],
                events: [...(e.events || []), data],
              };
            }

            if (data.type === 'diagram') {
              return { ...e, diagrams: [...(e.diagrams || []), data] };
            }

            if (data.type === 'final') {
              return {
                ...e,
                final: (e.final ? e.final + '\n\n' : '') + data.answer,
                summary: data.summary || e.summary,
              };
            }

            // Legacy step type
            if (data.type === 'step') {
              return { ...e, steps: [...(e.steps || []), data.content] };
            }

            // Structured error from backend
            if (data.type === 'error') {
              const msg = data.reason || data.message || 'Unknown error';
              const stage = data.stage ? `[${data.stage}] ` : '';
              return { ...e, error: stage + msg, isProcessing: false };
            }

            // Needs params
            if (data.type === 'needs_parameters') {
              return { ...e, error: data.message, isProcessing: false };
            }

            return e;
          }));
        }
      }

      setEntries(prev => {
        const finalEntries = prev.map(e =>
          e.id === entryId ? { ...e, isProcessing: false } : e
        );
        const finalEntry = finalEntries.find(e => e.id === entryId);
        if (finalEntry) {
          saveComputation({
            type: 'Computation',
            title: query.substring(0, 60),
            topic: finalEntry.domain || domain || 'Engineering',
            input: query,
            result: finalEntry.final,
            final: finalEntry.final,
            steps: finalEntry.steps || [],
            diagrams: finalEntry.diagrams || [],
            events: finalEntry.events || [],
            timestamp: Date.now(),
          }).then(() => loadHistory());
        }
        return finalEntries;
      });

    } catch (err) {
      if (err?.name === 'AbortError') return;
      setEntries(prev => prev.map(e =>
        e.id === entryId
          ? { ...e, error: err.message || 'Connection error.', isProcessing: false }
          : e
      ));
    } finally {
      setIsProcessing(false);
    }
  };

  const stopProcessing = () => {
    abortRef.current?.abort();
    setIsProcessing(false);
    setEntries(prev => prev.map(e =>
      e.isProcessing ? { ...e, isProcessing: false } : e
    ));
  };

  const clearAll = async () => {
    if (window.confirm('Clear this session?')) {
      setEntries([]);
      await clearCurrentSession();
    }
  };

  const deleteEntry = (id) => {
    setEntries(prev => prev.filter(e => String(e.id) !== String(id)));
  };

  const loadFromHistory = (item) => {
    if (item.events || item.final) {
      setEntries(prev => [...prev, {
        id: `hist_${Date.now()}`,
        query: item.input,
        domain: item.topic,
        events: item.events || [],
        diagrams: item.diagrams || [],
        final: item.final,
        summary: [],
        steps: item.steps || [],
        isProcessing: false,
        error: null,
        timestamp: item.timestamp,
      }]);
    }
    setShowHistory(false);
  };

  const EXAMPLE_QUERIES = [
    { label: 'Simultaneous equations', query: 'Solve: 3x + 2y = 12, x - y = 1', domain: 'Algebra' },
    { label: 'Beam analysis', query: 'Simply supported beam, L = 6m, UDL w = 10 kN/m', domain: 'Structural' },
    { label: 'Differentiate', query: 'Differentiate x³·sin(x) with respect to x', domain: 'Calculus' },
    { label: 'RC circuit', query: 'RC circuit: R = 2kΩ, C = 100μF, V₀ = 12V', domain: 'Circuits' },
    { label: 'Projectile motion', query: 'Projectile launched at 30° with u = 40 m/s', domain: 'Mechanics' },
    { label: 'Carnot engine', query: 'Carnot engine: T_H = 800K, T_C = 300K, Q_H = 5000J', domain: 'Thermo' },
  ];

  return (
    <div className="h-screen bg-[#08080f] text-slate-200 flex flex-col font-sans overflow-hidden">

      {/* Sticky header */}
      <header className="h-14 flex items-center justify-between px-6 border-b border-[#1d1e2c] bg-[#0a0a12]/90 backdrop-blur-md z-50 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-7 h-7 rounded bg-blue-600 text-white font-black text-xs">E</div>
          <div>
            <span className="text-[11px] font-black tracking-[0.2em] uppercase text-slate-100">Engineering</span>
            <span className="text-[11px] font-black tracking-[0.2em] uppercase text-blue-400"> Studio</span>
          </div>
          <div className="hidden sm:block h-4 w-px bg-white/10 mx-2" />
          <span className="hidden sm:block text-[10px] text-slate-500 font-mono uppercase tracking-widest">Derivation-first · Notebook mode</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={clearAll} className="p-2 rounded hover:bg-white/5 text-slate-500 hover:text-slate-300 transition-colors" title="Clear session">
            <Trash2 className="w-4 h-4" />
          </button>
          <button onClick={() => setShowHistory(!showHistory)} className="p-2 rounded hover:bg-white/5 text-slate-500 hover:text-slate-300 transition-colors" title="History">
            <History className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Scrollable workspace */}
      <div className="flex flex-1 overflow-hidden">
        <main ref={scrollRef} className="flex-1 overflow-y-auto pb-36">
          {entries.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-6 py-16 min-h-full">
              <div className="max-w-2xl w-full">
                <div className="mb-10 text-center">
                  <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-blue-600/10 border border-blue-500/20 mb-5">
                    <span className="text-2xl font-black text-blue-400">∑</span>
                  </div>
                  <h1 className="text-2xl font-black tracking-tight text-slate-100 mb-2">
                    Engineering Computation Studio
                  </h1>
                  <p className="text-sm text-slate-500 font-mono">
                    Symbolic derivations · Step-by-step solutions · Multi-method verification
                  </p>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-8">
                  {EXAMPLE_QUERIES.map(ex => (
                    <button
                      key={ex.label}
                      onClick={() => setInputText(ex.query)}
                      className="text-left p-3.5 rounded-lg bg-[#0f101a] border border-[#1d1e2c] hover:border-blue-500/40 hover:bg-[#111222] transition-all group"
                    >
                      <div className="text-[9px] font-black uppercase tracking-widest text-blue-400/60 mb-1.5 group-hover:text-blue-400 transition-colors">
                        {ex.domain}
                      </div>
                      <div className="text-xs text-slate-400 group-hover:text-slate-200 transition-colors leading-relaxed">
                        {ex.label}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <NotebookWorkspace entries={entries} onDelete={deleteEntry} />
          )}
        </main>

        {/* History sidebar */}
        <AnimatePresence>
          {showHistory && (
            <NotebookSidebar
              history={history}
              onLoad={loadFromHistory}
              onClose={() => setShowHistory(false)}
              deleteHistoryItem={deleteHistoryItem}
              onRefresh={loadHistory}
            />
          )}
        </AnimatePresence>
      </div>

      {/* Fixed input bar */}
      <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-[#1d1e2c] bg-[#09090f]/96 backdrop-blur-md px-4 py-3">
        <div className="max-w-4xl mx-auto">
          <EngineeringInput
            value={inputText}
            onChange={setInputText}
            onSubmit={handleCompute}
            onStop={stopProcessing}
            isProcessing={isProcessing}
          />
        </div>
      </div>

      {/* Method selection popup — pauses execution */}
      <AnimatePresence>
        {methodPopup.isOpen && (
          <MethodPopup
            isOpen={methodPopup.isOpen}
            methods={methodPopup.methods}
            domain={methodPopup.domain}
            problemDescription={methodPopup.problemDescription}
            onSelect={handleMethodSelect}
            onAutoSelect={handleMethodAutoSelect}
            onCancel={handleMethodCancel}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
