import React from 'react';
import { motion } from 'motion/react';
import { X, Trash2, Clock } from 'lucide-react';

function timeAgo(ts) {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function NotebookSidebar({ history, onLoad, onClose, deleteHistoryItem, onRefresh }) {
  return (
    <motion.div
      initial={{ x: 320, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 320, opacity: 0 }}
      transition={{ type: 'spring', damping: 25, stiffness: 200 }}
      className="w-72 border-l border-[#1d1e2c] bg-[#09090f] flex flex-col shrink-0"
    >
      <div className="flex items-center justify-between p-4 border-b border-[#1d1e2c]">
        <span className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-500">
          History
        </span>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-white/5 text-slate-600 hover:text-slate-300 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {history.length === 0 ? (
          <div className="p-6 text-center text-slate-700 text-xs font-mono">
            No history yet.
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {history.map(item => (
              <div
                key={item.id}
                className="group flex items-start gap-2 p-2.5 rounded-lg hover:bg-white/5 cursor-pointer transition-colors"
                onClick={() => onLoad(item)}
              >
                <Clock className="w-3 h-3 text-slate-700 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-slate-400 truncate leading-relaxed">
                    {item.input || item.title}
                  </div>
                  <div className="flex items-center gap-1.5 mt-1">
                    {item.topic && (
                      <span className="text-[9px] font-mono text-blue-400/60 uppercase tracking-wider">
                        {item.topic}
                      </span>
                    )}
                    <span className="text-[9px] text-slate-700">·</span>
                    <span className="text-[9px] text-slate-700">{timeAgo(item.timestamp)}</span>
                  </div>
                </div>
                <button
                  onClick={async (e) => {
                    e.stopPropagation();
                    await deleteHistoryItem(item.id);
                    onRefresh();
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-white/10 text-slate-600 hover:text-red-400 transition-all shrink-0"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}
