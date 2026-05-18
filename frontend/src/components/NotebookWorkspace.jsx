import React from 'react';
import NotebookEntry from './NotebookEntry';

export default function NotebookWorkspace({ entries, onDelete }) {
  return (
    <div className="max-w-4xl mx-auto w-full px-4 py-8 space-y-10">
      {entries.map((entry, idx) => (
        <NotebookEntry
          key={entry.id}
          entry={entry}
          index={idx}
          onDelete={() => onDelete(entry.id)}
        />
      ))}
    </div>
  );
}
