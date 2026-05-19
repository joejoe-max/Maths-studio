import React from 'react';
import NotebookEntry from './NotebookEntry';

export default function NotebookWorkspace({ entries, onDelete }) {
  return (
    <div className="max-w-4xl mx-auto w-full px-4 pt-8 pb-4 space-y-10">
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
