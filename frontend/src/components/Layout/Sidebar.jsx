import React from 'react';
import { useAuth } from '../../hooks/useAuth.jsx';

function PlusIcon() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>; }
function ChatBubbleIcon() { return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>; }
function TrashIcon() { return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>; }
function LogOutIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>; }

function ScaleRagIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M2 17l10 5 10-5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M2 12l10 5 10-5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

export default function Sidebar({ conversations, currentConversation, onSelectConversation, onNewConversation, onDeleteConversation, conversationsLoading }) {
  const { user, logout } = useAuth();
  const avatarLetter = (user?.name || user?.email || 'U').charAt(0).toUpperCase();
  const displayName = user?.name || user?.email?.split('@')[0] || 'User';

  return (
    <nav className="sidebar" aria-label="Main navigation">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon" aria-hidden="true"><ScaleRagIcon /></div>
          <span className="sidebar-logo-name">ScaleRAG</span>
        </div>
        <button id="sidebar-new-conversation-btn" className="btn btn-primary sidebar-new-btn" onClick={onNewConversation} type="button">
          <PlusIcon /> New Conversation
        </button>
      </div>
      <div className="sidebar-body">
        <div className="sidebar-section-label">Conversations</div>
        {conversationsLoading ? (
          <><div className="skeleton" style={{ height: 40, margin: '4px 0', borderRadius: 8 }}/><div className="skeleton" style={{ height: 40, margin: '4px 0', borderRadius: 8 }}/><div className="skeleton" style={{ height: 40, margin: '4px 0', borderRadius: 8 }}/></>
        ) : conversations.length === 0 ? (
          <div className="sidebar-conversations-empty"><p style={{ marginTop: '8px', lineHeight: 1.5 }}>No conversations yet.<br />Upload documents and start chatting!</p></div>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0 }} role="listbox">
            {conversations.map((conv) => {
              const isActive = currentConversation?.id === conv.id;
              return (
                <li key={conv.id}>
                  <div role="option" aria-selected={isActive} className={`conversation-item${isActive ? ' active' : ''}`} onClick={() => onSelectConversation(conv)} tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectConversation(conv); } }}>
                    <span className="conversation-item-icon" aria-hidden="true"><ChatBubbleIcon /></span>
                    <span className="conversation-item-title">{conv.title || 'Untitled'}</span>
                    <button className="conversation-item-delete" onClick={(e) => { e.stopPropagation(); onDeleteConversation(conv.id); }} aria-label={`Delete ${conv.title}`} type="button"><TrashIcon /></button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <div className="sidebar-footer">
        <div className="sidebar-user">
          <div className="sidebar-avatar" aria-hidden="true">{avatarLetter}</div>
          <div className="sidebar-user-info">
            <div className="sidebar-user-name">{displayName}</div>
            <div className="sidebar-user-email">{user?.email || ''}</div>
          </div>
          <button id="sidebar-logout-btn" className="sidebar-logout-btn" onClick={logout} title="Sign out" aria-label="Sign out" type="button"><LogOutIcon /></button>
        </div>
      </div>
    </nav>
  );
}
