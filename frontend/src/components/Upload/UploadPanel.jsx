import React, { useState, useCallback } from 'react';

function DocumentIcon({ size = 40 }) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>; }
function UploadIcon({ size = 28 }) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3"/></svg>; }
function FileIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>; }
function XIcon() { return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>; }
function TrashIcon() { return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>; }
function ChatIcon() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>; }
function CheckIcon() { return <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>; }

function formatBytes(b) {
  if (!b) return '0 B';
  const k = 1024, sizes = ['B','KB','MB','GB'];
  const i = Math.floor(Math.log(b) / Math.log(k));
  return `${(b / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function StatusBadge({ status }) {
  if (status === 'ready') return <span className="badge badge-success">Ready</span>;
  if (['processing','pending','queued'].includes(status)) return <span className="badge badge-warning"><span className="spinner spinner-sm" style={{ borderTopColor: 'var(--warning)', borderColor: 'rgba(245,158,11,0.2)', width: '10px', height: '10px' }}/>Processing</span>;
  if (['error','failed'].includes(status)) return <span className="badge badge-error">Failed</span>;
  return <span className="badge badge-accent">{status}</span>;
}

function fileTypeLabel(ft) {
  if (!ft) return 'PDF';
  return ft.toUpperCase();
}

const ALLOWED = ['.pdf', '.html', '.htm', '.csv'];

export default function UploadPanel({ documents, documentsLoading, uploading, uploadProgress, onUpload, onDeleteDocument, onStartChat }) {
  const [pendingFiles, setPendingFiles] = useState([]);
  const [dragActive, setDragActive] = useState(false);
  const [selectedDocIds, setSelectedDocIds] = useState([]);

  const addFiles = useCallback((files) => {
    const allowed = Array.from(files).filter((f) => ALLOWED.some((ext) => f.name.toLowerCase().endsWith(ext)));
    if (allowed.length > 0) setPendingFiles((p) => [...p, ...allowed]);
  }, []);

  const handleDragOver = useCallback((e) => { e.preventDefault(); setDragActive(true); }, []);
  const handleDragLeave = useCallback((e) => { e.preventDefault(); setDragActive(false); }, []);
  const handleDrop = useCallback((e) => { e.preventDefault(); setDragActive(false); addFiles(e.dataTransfer.files); }, [addFiles]);
  const handleFileInput = useCallback((e) => { addFiles(e.target.files); e.target.value = ''; }, [addFiles]);
  const removePending = useCallback((i) => setPendingFiles((p) => p.filter((_, j) => j !== i)), []);

  const handleUpload = useCallback(async () => {
    if (!pendingFiles.length) return;
    const uploaded = await onUpload(pendingFiles);
    if (uploaded?.length > 0) setPendingFiles([]);
  }, [pendingFiles, onUpload]);

  const toggleDoc = useCallback((id) => setSelectedDocIds((p) => p.includes(id) ? p.filter((d) => d !== id) : [...p, id]), []);
  const handleStartChat = useCallback(() => { if (selectedDocIds.length) onStartChat(selectedDocIds); }, [selectedDocIds, onStartChat]);

  return (
    <div className="upload-panel">
      <div className="upload-panel-inner">
        <div className="upload-hero">
          <div className="upload-hero-icon" aria-hidden="true"><DocumentIcon size={40} /></div>
          <h1 className="upload-hero-title">ScaleRAG Document Intelligence</h1>
          <p className="upload-hero-subtitle">Upload PDF, HTML, or CSV files. Ask anything across your entire document library with hybrid RAG retrieval.</p>
          <div className="feature-list">
            <div className="feature-item"><span className="feature-dot"/>10,000+ document support · PDF, HTML, CSV</div>
            <div className="feature-item"><span className="feature-dot"/>Hybrid retrieval: vector + BM25 + Cohere reranker</div>
            <div className="feature-item"><span className="feature-dot"/>Groq streaming · Source citations · Hallucination detection</div>
          </div>
        </div>

        <div id="upload-drop-zone" className={`drop-zone${dragActive ? ' drag-active' : ''}`} onDragOver={handleDragOver} onDragEnter={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop} role="button" aria-label="Drop files here or click to browse" tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); document.getElementById('upload-file-input').click(); } }}>
          <input id="upload-file-input" type="file" accept=".pdf,.html,.htm,.csv" multiple className="drop-zone-input" onChange={handleFileInput} aria-hidden="true" tabIndex={-1} />
          <div className="drop-zone-icon" aria-hidden="true"><UploadIcon size={42} /></div>
          <p className="drop-zone-text">Drag & drop files here, or <strong onClick={() => document.getElementById('upload-file-input').click()}>browse</strong></p>
          <p className="drop-zone-hint">Supports PDF, HTML, CSV · up to 50MB each</p>
        </div>

        {pendingFiles.length > 0 && (
          <div className="file-queue">
            <div className="file-queue-header"><span>{pendingFiles.length} file{pendingFiles.length !== 1 ? 's' : ''} selected</span><button className="btn btn-ghost btn-sm" type="button" onClick={() => setPendingFiles([])}>Clear all</button></div>
            {pendingFiles.map((f, i) => (
              <div key={`${f.name}-${i}`} className="file-queue-item">
                <span className="file-queue-icon"><FileIcon /></span>
                <div className="file-queue-info"><div className="file-queue-name">{f.name}</div><div className="file-queue-size">{formatBytes(f.size)}</div></div>
                <button className="file-queue-remove" type="button" onClick={() => removePending(i)} aria-label={`Remove ${f.name}`}><XIcon /></button>
              </div>
            ))}
          </div>
        )}

        {uploading && (
          <div className="upload-progress" role="status" aria-live="polite">
            <div className="upload-progress-bar-track"><div className="upload-progress-bar-fill" style={{ width: `${uploadProgress}%` }} /></div>
            <p className="upload-progress-text">{uploadProgress < 100 ? `Uploading… ${uploadProgress}%` : 'Processing documents…'}</p>
          </div>
        )}

        {pendingFiles.length > 0 && !uploading && (
          <button id="upload-submit-btn" className="btn btn-primary upload-btn" type="button" onClick={handleUpload} disabled={uploading}>
            <UploadIcon size={16} /> Upload {pendingFiles.length} File{pendingFiles.length !== 1 ? 's' : ''}
          </button>
        )}

        <div className="docs-library">
          <div className="docs-library-header">
            <span className="docs-library-title">Your Documents{documents.length > 0 ? ` (${documents.length})` : ''}</span>
            {selectedDocIds.length > 0 && <span style={{ fontSize: '0.78rem', color: 'var(--text-accent)', fontWeight: 600 }}>{selectedDocIds.length} selected</span>}
          </div>
          {documentsLoading ? (
            <><div className="skeleton" style={{ height: 56, borderRadius: 8 }}/><div className="skeleton" style={{ height: 56, borderRadius: 8 }}/><div className="skeleton" style={{ height: 56, borderRadius: 8 }}/></>
          ) : documents.length > 0 ? (
            <>
              {documents.map((doc) => {
                const isSelected = selectedDocIds.includes(doc.id);
                const isReady = doc.status === 'ready';
                return (
                  <div key={doc.id} className="doc-item" onClick={() => isReady && toggleDoc(doc.id)} style={{ cursor: isReady ? 'pointer' : 'default' }} role={isReady ? 'checkbox' : undefined} aria-checked={isReady ? isSelected : undefined} tabIndex={isReady ? 0 : undefined} onKeyDown={(e) => { if (isReady && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); toggleDoc(doc.id); } }}>
                    {isReady && <div className={`doc-item-checkbox${isSelected ? ' checked' : ''}`} aria-hidden="true">{isSelected && <CheckIcon />}</div>}
                    <span className="doc-item-icon"><FileIcon /></span>
                    <div className="doc-item-info">
                      <div className="doc-item-name">{doc.filename}</div>
                      <div className="doc-item-meta">
                        <span className="doc-item-meta-text">{formatBytes(doc.file_size)}</span>
                        {doc.page_count && <span className="doc-item-meta-text">· {doc.page_count} pages</span>}
                        {doc.chunk_count && <span className="doc-item-meta-text">· {doc.chunk_count} chunks</span>}
                        <span className="doc-item-meta-text" style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>[{fileTypeLabel(doc.file_type)}]</span>
                        <StatusBadge status={doc.status} />
                      </div>
                      {doc.processing_error && <div className="doc-item-meta-text" style={{ color: 'var(--error)', fontSize: '0.75rem' }}>{doc.processing_error}</div>}
                    </div>
                    <button className="doc-item-delete" type="button" onClick={(e) => { e.stopPropagation(); onDeleteDocument(doc.id); }} aria-label={`Delete ${doc.filename}`}><TrashIcon /></button>
                  </div>
                );
              })}
              {selectedDocIds.length > 0 && (
                <button id="start-chat-btn" className="btn btn-primary start-chat-btn" type="button" onClick={handleStartChat}>
                  <ChatIcon /> Chat with {selectedDocIds.length} Document{selectedDocIds.length !== 1 ? 's' : ''}
                </button>
              )}
            </>
          ) : (
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textAlign: 'center', padding: '16px 0' }}>No documents yet. Upload files above to get started.</p>
          )}
        </div>
      </div>
    </div>
  );
}
