import React, { useRef, useEffect, useState } from 'react';
import { ArrowUp, Square, Paperclip, X } from 'lucide-react';

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
  const fileInputRef = useRef(null);
  const exampleRef = useRef(0);
  const [uploadedFile, setUploadedFile] = useState(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  }, [value]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isProcessing && (value.trim() || uploadedFile)) handleSubmit();
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const allowed = file.type.startsWith('image/') || [
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'text/plain',
    ].includes(file.type) || /\.(pdf|docx|txt)$/i.test(file.name);
    if (!allowed) {
      alert('Please select an image, PDF, DOCX, or TXT file');
      return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      const base64 = event.target.result;
      setUploadedFile({
        name: file.name,
        data: base64,
        type: file.type,
      });
    };
    reader.readAsDataURL(file);
  };

  const removeFile = () => {
    setUploadedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleSubmit = () => {
    if (uploadedFile || value.trim()) {
      const fileToSend = uploadedFile;
      setUploadedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      onSubmit(fileToSend);
    }
  };

  const placeholder = PLACEHOLDER_EXAMPLES[exampleRef.current % PLACEHOLDER_EXAMPLES.length];

  return (
    <div className="flex flex-col gap-3">
      {/* Image preview if uploaded */}
      {uploadedFile && (
        <div className="relative bg-[#0f1018] border border-[#1d1e2c] rounded-lg p-3 flex items-center justify-between">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div className="w-10 h-10 bg-blue-500/10 rounded border border-blue-500/20 flex items-center justify-center shrink-0">
              <Paperclip className="w-4 h-4 text-blue-400" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-slate-300 truncate">{uploadedFile.name}</p>
              <p className="text-[10px] text-slate-500">File uploaded and ready</p>
            </div>
          </div>
          <button
            onClick={removeFile}
            className="p-1 rounded hover:bg-white/5 text-slate-500 hover:text-slate-300 transition-colors shrink-0"
            title="Remove file"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Input area */}
      <div className="flex flex-col sm:flex-row sm:items-end gap-3">
        <div className="flex-1 relative min-w-0">
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
            style={{ minHeight: 44, maxHeight: 120 }}
          />
        </div>

        <div className="flex gap-2 sm:gap-3 flex-shrink-0 w-full sm:w-auto">
          {/* Image upload button */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,.pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
            onChange={handleFileSelect}
            className="hidden"
            aria-label="Upload file"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isProcessing}
            className={`
              flex-1 sm:flex-shrink-0 sm:w-9 h-9 rounded-lg flex items-center justify-center
              transition-all font-medium text-sm
              ${isProcessing
                ? 'bg-slate-700/30 border border-slate-600/30 text-slate-600 cursor-not-allowed'
                : 'bg-[#0f1018] border border-[#1d1e2c] text-slate-500 hover:text-slate-300 hover:border-slate-500/50 hover:bg-white/5'
              }
            `}
            title="Upload image, PDF, DOCX, or TXT (optional)"
          >
            <Paperclip className="w-4 h-4" />
          </button>

          {/* Submit/Stop button */}
          <button
            onClick={isProcessing ? onStop : handleSubmit}
            disabled={!isProcessing && !value.trim() && !uploadedFile}
            className={`
              flex-1 sm:flex-shrink-0 sm:w-9 h-9 rounded-lg flex items-center justify-center
              transition-all font-medium text-sm
              ${isProcessing
                ? 'bg-red-500/20 border border-red-500/30 text-red-400 hover:bg-red-500/30'
                : (value.trim() || uploadedFile)
                  ? 'bg-blue-600 text-white hover:bg-blue-500 shadow-lg shadow-blue-600/20'
                  : 'bg-[#0f1018] border border-[#1d1e2c] text-slate-700 cursor-not-allowed'
              }
            `}
            title={isProcessing ? 'Stop' : 'Compute (Enter)'}
          >
            {isProcessing ? <Square className="w-3.5 h-3.5" /> : <ArrowUp className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}
