import React, { useState } from 'react';

function CloseIcon() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>; }
function SourcesIcon() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg>; }
function FileIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>; }
function ChevronDownIcon() { return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9"/></svg>; }
function ChevronUpIcon() { return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="18 15 12 9 6 15"/></svg>; }

function SourceCard({ source, index }) {
  const [expanded, setExpanded] = useState(false);
  const hasLong = source.text && source.text.length > 180;
  return (
    <article className="source-card" aria-label={`Source ${index + 1}: ${source.filename}`}>
      <div className="source-card-header">
        <span className="source-card-icon"><FileIcon /></span>
        <div className="source-card-meta">
          <div className="source-card-filename" title={source.filename}>{source.filename}</div>
          <div className="source-card-page">Page {source.page_num}</div>
        </div>
      </div>
      {source.text && (
        <>
          <p className={`source-card-excerpt${expanded ? '' : ' collapsed'}`}>{source.text}</p>
          {hasLong && (
            <button type="button" className="source-card-expand-btn" onClick={() => setExpanded((p) => !p)} aria-expanded={expanded}>
              {expanded ? <><ChevronUpIcon /> Show less</> : <><ChevronDownIcon /> Show more</>}
            </button>
          )}
        </>
      )}
    </article>
  );
}

export default function SourcePanel({ sources, open, onClose }) {
  return (
    <aside className={`source-panel${open ? ' open' : ''}`} aria-label="Sources panel" aria-hidden={!open} role="complementary">
      <div className="source-panel-header">
        <h2 className="source-panel-title"><span className="source-panel-title-icon"><SourcesIcon /></span>Sources</h2>
        <button id="source-panel-close-btn" className="source-panel-close" type="button" onClick={onClose} aria-label="Close sources panel"><CloseIcon /></button>
      </div>
      <div className="source-panel-body">
        {sources?.length > 0 ? (
          <>
            <p className="source-panel-count">{sources.length} source{sources.length !== 1 ? 's' : ''} found</p>
            {sources.map((src, i) => <SourceCard key={i} source={src} index={i} />)}
          </>
        ) : (
          <div className="source-panel-empty">
            <div className="source-panel-empty-icon"><SourcesIcon /></div>
            <p className="source-panel-empty-text">Sources will appear here after ScaleRAG responds with citations from your documents.</p>
          </div>
        )}
      </div>
    </aside>
  );
}
