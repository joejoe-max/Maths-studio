import React, { useEffect, useRef, useState } from 'react';

/**
 * Normalises diagram data so every chart component receives
 * { x: number[], y: number[], ... } regardless of whether the
 * backend emitted an array-of-objects [{ x, y }] or parallel arrays.
 */
function normaliseXY(data, xKey = 'x', yKey = 'y') {
  if (!data) return { x: [], y: [] };
  if (Array.isArray(data)) {
    const x = data.map(p => p[xKey] ?? p.x ?? 0);
    const y = data.map(p => p[yKey] ?? p.y ?? 0);
    return { x, y };
  }
  return data;
}

function PlotlyChart({ data, layout, title }) {
  const ref = useRef(null);
  const [Plotly, setPlotly] = useState(null);

  useEffect(() => {
    import('plotly.js-dist-min').then(p => setPlotly(p.default || p));
  }, []);

  useEffect(() => {
    if (!Plotly || !ref.current) return;
    const fullLayout = {
      paper_bgcolor: 'transparent',
      plot_bgcolor: '#0a0b14',
      font: { color: '#94a3b8', size: 11, family: 'JetBrains Mono, monospace' },
      margin: { t: 30, r: 20, b: 50, l: 60 },
      xaxis: {
        gridcolor: '#1d1e2c',
        linecolor: '#1d1e2c',
        tickfont: { size: 10 },
        zeroline: true,
        zerolinecolor: '#2d2e3c',
        ...layout?.xaxis,
      },
      yaxis: {
        gridcolor: '#1d1e2c',
        linecolor: '#1d1e2c',
        tickfont: { size: 10 },
        zeroline: true,
        zerolinecolor: '#2d2e3c',
        ...layout?.yaxis,
      },
      ...layout,
    };
    Plotly.react(ref.current, data, fullLayout, { responsive: true, displayModeBar: false });
  }, [Plotly, data, layout]);

  return (
    <div className="rounded-lg border border-[#1d1e2c] overflow-hidden bg-[#090a12] my-4">
      {title && (
        <div className="px-4 py-2.5 border-b border-[#1d1e2c]">
          <span className="text-[9px] font-black uppercase tracking-[0.25em] text-slate-600">{title}</span>
        </div>
      )}
      <div ref={ref} style={{ height: 'clamp(160px, 40vw, 240px)', width: '100%' }} />
    </div>
  );
}

function ImagePlot({ data, title }) {
  const { image, caption } = data;
  if (!image) return null;
  return (
    <div className="rounded-lg border border-[#1d1e2c] overflow-hidden bg-[#090a12] my-4">
      {title && (
        <div className="px-4 py-2.5 border-b border-[#1d1e2c]">
          <span className="text-[9px] font-black uppercase tracking-[0.25em] text-slate-600">{title}</span>
        </div>
      )}
      <div className="p-3">
        <img
          src={image}
          alt={caption || title || 'Diagram'}
          className="w-full h-auto rounded"
          style={{ maxHeight: 420, objectFit: 'contain' }}
        />
        {caption && (
          <p className="text-[10px] text-slate-500 font-mono mt-2 text-center">{caption}</p>
        )}
      </div>
    </div>
  );
}

function BeamSchematic({ data, title }) {
  const { span = 6, support_type = 'simply_supported', loads = [] } = data;
  const W = 500;
  const H = 140;
  const beam_y = 80;
  const beam_x0 = 50;
  const beam_x1 = W - 50;
  const beam_len = beam_x1 - beam_x0;

  return (
    <div className="rounded-lg border border-[#1d1e2c] overflow-hidden bg-[#090a12] my-4">
      {title && (
        <div className="px-4 py-2.5 border-b border-[#1d1e2c]">
          <span className="text-[9px] font-black uppercase tracking-[0.25em] text-slate-600">{title}</span>
        </div>
      )}
      <div className="px-4 py-2">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 160 }}>
          <rect x={beam_x0} y={beam_y - 5} width={beam_len} height={10} fill="#3b82f6" rx={2} opacity={0.8} />

          {support_type === 'simply_supported' && (
            <>
              <polygon points={`${beam_x0},${beam_y + 5} ${beam_x0 - 12},${beam_y + 25} ${beam_x0 + 12},${beam_y + 25}`} fill="#475569" />
              <line x1={beam_x0 - 16} y1={beam_y + 28} x2={beam_x0 + 16} y2={beam_y + 28} stroke="#475569" strokeWidth={2} />
              <polygon points={`${beam_x1},${beam_y + 5} ${beam_x1 - 12},${beam_y + 25} ${beam_x1 + 12},${beam_y + 25}`} fill="#475569" />
              <line x1={beam_x1 - 16} y1={beam_y + 28} x2={beam_x1 + 16} y2={beam_y + 28} stroke="#475569" strokeWidth={2} />
              <text x={beam_x0} y={beam_y + 42} textAnchor="middle" fontSize={9} fill="#64748b" fontFamily="monospace">A</text>
              <text x={beam_x1} y={beam_y + 42} textAnchor="middle" fontSize={9} fill="#64748b" fontFamily="monospace">B</text>
            </>
          )}
          {support_type === 'cantilever' && (
            <>
              <rect x={beam_x0 - 16} y={beam_y - 28} width={14} height={56} fill="#475569" rx={2} />
              <text x={beam_x0 - 22} y={beam_y + 3} textAnchor="middle" fontSize={9} fill="#64748b" fontFamily="monospace">A</text>
              <text x={beam_x1 + 8} y={beam_y + 3} textAnchor="start" fontSize={9} fill="#64748b" fontFamily="monospace">Free</text>
            </>
          )}

          {loads.map((load, i) => {
            if (load.type === 'point_load') {
              const lx = beam_x0 + (load.position / span) * beam_len;
              const mag = load.magnitude > 0 ? 1 : -1;
              const arrow_y0 = mag > 0 ? beam_y - 35 : beam_y + 5;
              const arrow_y1 = mag > 0 ? beam_y - 5 : beam_y + 35;
              return (
                <g key={i}>
                  <line x1={lx} y1={arrow_y0} x2={lx} y2={arrow_y1} stroke="#f59e0b" strokeWidth={2} markerEnd="url(#arrow)" />
                  <text x={lx + 4} y={arrow_y0 + 3} fontSize={9} fill="#f59e0b" fontFamily="monospace">
                    {load.magnitude >= 1000 ? `${(load.magnitude/1000).toFixed(1)}kN` : `${load.magnitude.toFixed(0)}N`}
                  </text>
                </g>
              );
            }
            if (load.type === 'udl' || load.type === 'factored_udl') {
              const x0 = beam_x0 + (load.start / span) * beam_len;
              const x1 = beam_x0 + (load.end / span) * beam_len;
              const y_top = beam_y - 30;
              const arrows = [];
              const n = Math.floor((x1 - x0) / 20);
              for (let j = 0; j <= n; j++) {
                const ax = x0 + j * (x1 - x0) / n;
                arrows.push(
                  <line key={j} x1={ax} y1={y_top} x2={ax} y2={beam_y - 5} stroke="#fb7185" strokeWidth={1.2} />
                );
              }
              const rate = load.type === 'factored_udl' ? `${Number(load.intensity).toFixed(2)} kN/m` : (load.intensity >= 1000 ? `${(load.intensity/1000).toFixed(1)} kN/m` : `${load.intensity} N/m`);
              return (
                <g key={i}>
                  <line x1={x0} y1={y_top} x2={x1} y2={y_top} stroke="#fb7185" strokeWidth={1.5} />
                  {arrows}
                  <text x={(x0 + x1) / 2} y={y_top - 5} textAnchor="middle" fontSize={9} fill="#fb7185" fontFamily="monospace">
                    {load.type === 'factored_udl' ? 'wu' : 'w'} = {rate}
                  </text>
                </g>
              );
            }
            return null;
          })}

          <line x1={beam_x0} y1={H - 10} x2={beam_x1} y2={H - 10} stroke="#334155" strokeWidth={1} />
          <text x={(beam_x0 + beam_x1) / 2} y={H - 2} textAnchor="middle" fontSize={9} fill="#475569" fontFamily="monospace">
            L = {span} m
          </text>

          <defs>
            <marker id="arrow" markerWidth={6} markerHeight={6} refX={3} refY={3} orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="#f59e0b" />
            </marker>
          </defs>
        </svg>
      </div>
    </div>
  );
}

function ShearForceDiagram({ data, title }) {
  const norm = normaliseXY(data, 'x', Array.isArray(data) ? 'y' : (data.V ? 'V' : 'y'));
  const xArr = norm.x ?? data.x;
  const yArr = norm.y ?? data.V ?? data.y;
  if (!xArr || !yArr) return null;

  const traces = [{
    x: xArr, y: yArr,
    type: 'scatter',
    mode: 'lines',
    fill: 'tozeroy',
    line: { color: '#3b82f6', width: 1.5 },
    fillcolor: 'rgba(59,130,246,0.07)',
    name: 'V(x)',
  }];

  return (
    <PlotlyChart
      title={title || 'Shear Force Diagram'}
      data={traces}
      layout={{
        xaxis: { title: { text: data.x_label || 'Position (m)', font: { size: 10 } } },
        yaxis: { title: { text: data.y_label || 'Shear Force V (N)', font: { size: 10 } } },
      }}
    />
  );
}

function BendingMomentDiagram({ data, title }) {
  const norm = normaliseXY(data, 'x', Array.isArray(data) ? 'y' : (data.M ? 'M' : 'y'));
  const xArr = norm.x ?? data.x;
  const yArr = norm.y ?? data.M ?? data.y;
  if (!xArr || !yArr) return null;

  const traces = [{
    x: xArr, y: yArr,
    type: 'scatter',
    mode: 'lines',
    fill: 'tozeroy',
    line: { color: '#a78bfa', width: 1.5 },
    fillcolor: 'rgba(167,139,250,0.07)',
    name: 'M(x)',
  }];

  return (
    <PlotlyChart
      title={title || 'Bending Moment Diagram'}
      data={traces}
      layout={{
        xaxis: { title: { text: data.x_label || 'Position (m)', font: { size: 10 } } },
        yaxis: { title: { text: data.y_label || 'Bending Moment M (N·m)', font: { size: 10 } } },
      }}
    />
  );
}

function TimeSeriesDiagram({ data, title }) {
  const norm = normaliseXY(data);
  const xArr = norm.x ?? data.x;
  const yArr = norm.y ?? data.y;
  if (!xArr || !yArr) return null;

  const traces = [{
    x: xArr, y: yArr,
    type: 'scatter',
    mode: 'lines',
    line: { color: '#10b981', width: 1.5 },
    name: data.y_label || 'Value',
  }];

  return (
    <PlotlyChart
      title={title}
      data={traces}
      layout={{
        xaxis: { title: { text: data.x_label || 'Time', font: { size: 10 } } },
        yaxis: { title: { text: data.y_label || 'Value', font: { size: 10 } } },
      }}
    />
  );
}

function TrajectoryDiagram({ data, title }) {
  const norm = normaliseXY(data);
  const xArr = norm.x ?? data.x;
  const yArr = norm.y ?? data.y;
  if (!xArr || !yArr) return null;

  const traces = [{
    x: xArr, y: yArr,
    type: 'scatter',
    mode: 'lines',
    line: { color: '#f59e0b', width: 2 },
    name: 'Trajectory',
  }];

  if (data.peak) {
    traces.push({
      x: [data.peak.x], y: [data.peak.y],
      type: 'scatter',
      mode: 'markers',
      marker: { color: '#fb7185', size: 8, symbol: 'circle' },
      name: `Peak (${data.peak.y?.toFixed(2)} m)`,
    });
  }

  return (
    <PlotlyChart
      title={title || 'Projectile Trajectory'}
      data={traces}
      layout={{
        xaxis: { title: { text: 'Horizontal distance (m)', font: { size: 10 } } },
        yaxis: { title: { text: 'Height (m)', font: { size: 10 } } },
      }}
    />
  );
}

function FrequencySweep({ data, title }) {
  const norm = normaliseXY(data);
  const xArr = norm.x ?? data.x;
  const yArr = norm.y ?? data.y;
  if (!xArr || !yArr) return null;

  const traces = [{
    x: xArr, y: yArr,
    type: 'scatter',
    mode: 'lines',
    line: { color: '#38bdf8', width: 1.5 },
    name: '|Z(f)|',
  }];

  if (data.resonant_frequency) {
    traces.push({
      x: [data.resonant_frequency],
      y: [Math.min(...yArr)],
      type: 'scatter',
      mode: 'markers',
      marker: { color: '#f59e0b', size: 8 },
      name: `f₀ = ${data.resonant_frequency.toFixed(2)} Hz`,
    });
  }

  return (
    <PlotlyChart
      title={title || 'Impedance vs Frequency'}
      data={traces}
      layout={{
        xaxis: {
          title: { text: 'Frequency (Hz)', font: { size: 10 } },
          type: 'log',
        },
        yaxis: { title: { text: '|Z| (Ω)', font: { size: 10 } } },
      }}
    />
  );
}

function PVDiagram({ data, title }) {
  const { V, P, current_point } = data;
  if (!V || !P) return null;

  const traces = [{
    x: V, y: P,
    type: 'scatter',
    mode: 'lines',
    line: { color: '#f97316', width: 1.5 },
    name: 'Isothermal',
  }];

  if (current_point) {
    traces.push({
      x: [current_point.V], y: [current_point.P],
      type: 'scatter',
      mode: 'markers',
      marker: { color: '#fb7185', size: 8 },
      name: 'State',
    });
  }

  return (
    <PlotlyChart
      title={title || 'P-V Diagram'}
      data={traces}
      layout={{
        xaxis: { title: { text: 'Volume V (m³)', font: { size: 10 } } },
        yaxis: { title: { text: 'Pressure P (Pa)', font: { size: 10 } } },
      }}
    />
  );
}

function BodePlot({ data, title }) {
  const { w, mag, phase } = data;
  if (!w || !mag || !phase) return null;

  const magTrace = {
    x: w, y: mag,
    type: 'scatter', mode: 'lines',
    line: { color: '#3b82f6', width: 1.5 },
    name: 'Magnitude (dB)',
    xaxis: 'x', yaxis: 'y',
  };
  const phaseTrace = {
    x: w, y: phase,
    type: 'scatter', mode: 'lines',
    line: { color: '#f59e0b', width: 1.5 },
    name: 'Phase (°)',
    xaxis: 'x', yaxis: 'y2',
  };

  return (
    <PlotlyChart
      title={title || 'Bode Plot'}
      data={[magTrace, phaseTrace]}
      layout={{
        xaxis: { title: { text: 'Frequency ω (rad/s)', font: { size: 10 } }, type: 'log' },
        yaxis: { title: { text: 'Magnitude (dB)', font: { size: 10 } } },
        yaxis2: {
          title: { text: 'Phase (°)', font: { size: 10 } },
          overlaying: 'y',
          side: 'right',
          gridcolor: '#1d1e2c',
          tickfont: { size: 10 },
          zeroline: true,
          zerolinecolor: '#2d2e3c',
        },
      }}
    />
  );
}

export default function DiagramRenderer({ diagram }) {
  const { diagram_type, data, title } = diagram;

  if (!data) return null;

  switch (diagram_type) {
    case 'plot':
      return <ImagePlot data={data} title={title} />;
    case 'beam_schematic':
      return <BeamSchematic data={data} title={title} />;
    case 'shear_force':
      return <ShearForceDiagram data={data} title={title} />;
    case 'bending_moment':
      return <BendingMomentDiagram data={data} title={title} />;
    case 'time_series':
      return <TimeSeriesDiagram data={data} title={title} />;
    case 'trajectory':
      return <TrajectoryDiagram data={data} title={title} />;
    case 'frequency_sweep':
      return <FrequencySweep data={data} title={title} />;
    case 'pv_diagram':
      return <PVDiagram data={data} title={title} />;
    case 'bode_plot':
      return <BodePlot data={data} title={title} />;
    default: {
      // Handle array-of-objects format [{ x, y }]
      if (Array.isArray(data) && data.length > 0 && 'x' in data[0]) {
        const norm = normaliseXY(data);
        return (
          <PlotlyChart
            title={title || diagram_type}
            data={[{ x: norm.x, y: norm.y, type: 'scatter', mode: 'lines', line: { color: '#3b82f6', width: 1.5 } }]}
            layout={{
              xaxis: { title: { text: 'x', font: { size: 10 } } },
              yaxis: { title: { text: 'y', font: { size: 10 } } },
            }}
          />
        );
      }
      // Parallel-array format { x, y | V | M }
      if (data.x && (data.y || data.V || data.M)) {
        const yData = data.y || data.V || data.M;
        return (
          <PlotlyChart
            title={title || diagram_type}
            data={[{ x: data.x, y: yData, type: 'scatter', mode: 'lines', line: { color: '#3b82f6', width: 1.5 } }]}
            layout={{
              xaxis: { title: { text: data.x_label || 'x', font: { size: 10 } } },
              yaxis: { title: { text: data.y_label || 'y', font: { size: 10 } } },
            }}
          />
        );
      }
      // Base64 image fallback
      if (data.image) {
        return <ImagePlot data={data} title={title} />;
      }
      return null;
    }
  }
}
