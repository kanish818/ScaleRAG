import React, { useEffect, useState, useCallback } from 'react';
import { AuthProvider, useAuth } from './hooks/useAuth.jsx';
import { useDocuments } from './hooks/useDocuments';
import { useChat } from './hooks/useChat';

import AuthPage from './components/Auth/AuthPage';
import Sidebar from './components/Layout/Sidebar';
import UploadPanel from './components/Upload/UploadPanel';
import ChatInterface from './components/Chat/ChatInterface';
import SourcePanel from './components/Sources/SourcePanel';

function ScaleRagIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
      <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M2 17l10 5 10-5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M2 12l10 5 10-5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function AppContent() {
  const { loading: authLoading, wakingUp, isAuthenticated, handleGoogleCallback } = useAuth();
  const [sourcePanelOpen, setSourcePanelOpen] = useState(false);

  const { documents, loading: docsLoading, uploading, uploadProgress, fetchDocuments, uploadFiles, deleteDocument } = useDocuments();
  const { conversations, currentConversation, messages, streaming, streamingContent, sources, loading: convsLoading, messagesLoading, fetchConversations, createConversation, selectConversation, sendMessage, deleteConversation, clearSources } = useChat();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has('token')) handleGoogleCallback();
  }, []); // eslint-disable-line

  useEffect(() => {
    if (isAuthenticated) { fetchDocuments(); fetchConversations(); }
  }, [isAuthenticated]); // eslint-disable-line

  const handleStartChat = useCallback(async (docIds) => {
    const selected = documents.filter((d) => docIds.includes(d.id));
    const title = selected.length === 1 ? selected[0].filename.replace(/\.(pdf|html?|csv)$/i, '') : `${selected.length} documents`;
    try { await createConversation(title, docIds); } catch { /* handled */ }
  }, [documents, createConversation]);

  const handleNewConversation = useCallback(() => { selectConversation(null); clearSources(); setSourcePanelOpen(false); }, [selectConversation, clearSources]);
  const handleSelectConversation = useCallback((conv) => { clearSources(); setSourcePanelOpen(false); selectConversation(conv); }, [selectConversation, clearSources]);

  useEffect(() => { if (sources?.length > 0) setSourcePanelOpen(true); }, [sources]);

  if (authLoading) {
    return (
      <div style={{ width: '100vw', height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-primary)', flexDirection: 'column', gap: '16px' }}>
        <div style={{ width: 48, height: 48, background: 'var(--gradient)', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: 'var(--shadow-accent)' }}>
          <ScaleRagIcon />
        </div>
        <span className="spinner spinner-lg spinner-accent" aria-label="Loading…" />
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          {wakingUp ? '☕ Server waking up, please wait…' : 'Loading ScaleRAG…'}
        </p>
        {wakingUp && <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem', maxWidth: 280, textAlign: 'center' }}>This may take up to 60 seconds on first load.</p>}
      </div>
    );
  }

  if (!isAuthenticated) return <AuthPage />;

  return (
    <div className="app-layout">
      <Sidebar conversations={conversations} currentConversation={currentConversation} onSelectConversation={handleSelectConversation} onNewConversation={handleNewConversation} onDeleteConversation={deleteConversation} conversationsLoading={convsLoading} />
      <div className="main-content">
        <div className="content-area">
          {currentConversation ? (
            <ChatInterface conversation={currentConversation} messages={messages} messagesLoading={messagesLoading} streaming={streaming} streamingContent={streamingContent} sources={sources} onSendMessage={sendMessage} onShowSources={() => setSourcePanelOpen(true)} documents={documents} />
          ) : (
            <UploadPanel documents={documents} documentsLoading={docsLoading} uploading={uploading} uploadProgress={uploadProgress} onUpload={uploadFiles} onDeleteDocument={deleteDocument} onStartChat={handleStartChat} />
          )}
        </div>
        <SourcePanel sources={sources} open={sourcePanelOpen} onClose={() => setSourcePanelOpen(false)} />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
