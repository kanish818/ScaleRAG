import React, { useState } from 'react';

function BotIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/></svg>; }
function UserIcon() { return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>; }
function BookOpenIcon() { return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg>; }
function ChevronDownIcon() { return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9"/></svg>; }
function ChevronUpIcon() { return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="18 15 12 9 6 15"/></svg>; }

function formatTime(iso) {
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); } catch { return ''; }
}

function MessageContent({ content }) {
  if (!content) return null;
  const parts = [];
  const codeBlockRegex = /```[\w]*\n?([\s\S]*?)```/g;
  let lastIndex = 0, match;
  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match.index > lastIndex) parts.push({ type: 'text', value: content.slice(lastIndex, match.index) });
    parts.push({ type: 'codeblock', value: match[1] });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < content.length) parts.push({ type: 'text', value: content.slice(lastIndex) });
  return (
    <div className="message-content">
      {parts.map((part, i) => {
        if (part.type === 'codeblock') return <pre key={i}><code>{part.value.trim()}</code></pre>;
        const inline = part.value.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
        return (
          <p key={i}>
            {inline.map((seg, j) => {
              if (seg.startsWith('`') && seg.endsWith('`')) return <code key={j}>{seg.slice(1, -1)}</code>;
              if (seg.startsWith('**') && seg.endsWith('**')) return <strong key={j}>{seg.slice(2, -2)}</strong>;
              return seg.split('\n').map((line, k, arr) => <React.Fragment key={k}>{line}{k < arr.length - 1 && <br />}</React.Fragment>);
            })}
          </p>
        );
      })}
    </div>
  );
}

function HallucinationBadge({ score }) {
  if (score === null || score === undefined) return null;
  const color = score <= 20 ? 'var(--success)' : score <= 55 ? 'var(--warning)' : 'var(--error)';
  const label = score <= 20 ? 'Grounded' : score <= 55 ? 'Partially grounded' : 'Ungrounded';
  return (
    <span style={{ fontSize: '0.7rem', color, fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '4px', marginTop: '6px', opacity: 0.8 }}>
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      {label} (score: {score})
    </span>
  );
}

function InlineSources({ sources }) {
  const [expanded, setExpanded] = useState(false);
  if (!sources?.length) return null;
  return (
    <div style={{ marginTop: '10px' }}>
      <button type="button" className="message-sources-toggle" onClick={() => setExpanded((p) => !p)} aria-expanded={expanded}>
        <BookOpenIcon />{sources.length} Source{sources.length !== 1 ? 's' : ''}{expanded ? <ChevronUpIcon /> : <ChevronDownIcon />}
      </button>
      {expanded && (
        <div className="message-sources-list" role="list">
          {sources.map((src, i) => (
            <div key={i} className="message-source-chip" role="listitem">
              <div className="message-source-header">
                <span className="message-source-filename">{src.filename}</span>
                <span className="message-source-page">p. {src.page_num}</span>
              </div>
              {src.text && <p className="message-source-text">{src.text}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function MessageBubble({ message, isStreaming = false, streamingContent = '' }) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';
  const displayContent = isStreaming ? streamingContent : message.content;

  return (
    <div className="message-group" aria-label={`${isUser ? 'Your' : 'ScaleRAG'} message`}>
      <div className={`message-row ${message.role}`}>
        {isAssistant && <div className="message-avatar assistant" aria-hidden="true"><BotIcon /></div>}
        <div className={`message-bubble-wrapper ${message.role}`}>
          <div className={`message-bubble ${message.role}`}>
            {isStreaming ? (
              <div className="message-content"><p>{displayContent}<span className="streaming-cursor" aria-hidden="true"/></p></div>
            ) : (
              <MessageContent content={displayContent} />
            )}
            {isAssistant && !isStreaming && (
              <>
                <InlineSources sources={message.sources} />
                <HallucinationBadge score={message.hallucination_score} />
              </>
            )}
          </div>
          {!isStreaming && message.created_at && (
            <div className="message-meta">
              <time className="message-time" dateTime={message.created_at}>{formatTime(message.created_at)}</time>
            </div>
          )}
        </div>
        {isUser && <div className="message-avatar user" aria-hidden="true"><UserIcon /></div>}
      </div>
    </div>
  );
}
