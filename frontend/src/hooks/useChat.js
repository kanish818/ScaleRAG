import { useState, useCallback, useRef, useEffect } from 'react';
import { getConversations as apiGetConvs, createConversation as apiCreate, deleteConversation as apiDelete, getMessages as apiGetMsgs, streamChat as apiStream } from '../services/api';

export function useChat() {
  const [conversations, setConversations] = useState([]);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [sources, setSources] = useState([]);
  const [hallucinationInfo, setHallucinationInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);
  const abortRef = useRef(null);

  useEffect(() => { mountedRef.current = true; return () => { mountedRef.current = false; abortRef.current?.abort(); }; }, []);

  const fetchConversations = useCallback(async () => {
    setLoading(true);
    try {
      const convs = await apiGetConvs();
      if (mountedRef.current) setConversations(convs);
      return convs;
    } catch (err) {
      if (mountedRef.current) setError(err.response?.data?.detail || 'Failed to load conversations.');
      return [];
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  const selectConversation = useCallback(async (conv) => {
    if (!conv) { setCurrentConversation(null); setMessages([]); setSources([]); return; }
    setCurrentConversation(conv);
    setSources([]);
    setStreamingContent('');
    setHallucinationInfo(null);
    setMessagesLoading(true);
    try {
      const msgs = await apiGetMsgs(conv.id);
      if (mountedRef.current) setMessages(msgs);
    } catch { if (mountedRef.current) setMessages([]); }
    finally { if (mountedRef.current) setMessagesLoading(false); }
  }, []);

  const createConversation = useCallback(async (title, docIds) => {
    try {
      const conv = await apiCreate(title, docIds);
      if (mountedRef.current) { setConversations((p) => [conv, ...p]); setCurrentConversation(conv); setMessages([]); setSources([]); }
      return conv;
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to create conversation.';
      if (mountedRef.current) setError(msg);
      throw new Error(msg);
    }
  }, []);

  const deleteConversation = useCallback(async (id) => {
    setConversations((p) => p.filter((c) => c.id !== id));
    if (currentConversation?.id === id) { setCurrentConversation(null); setMessages([]); setSources([]); }
    try { await apiDelete(id); } catch { if (mountedRef.current) fetchConversations(); }
  }, [currentConversation, fetchConversations]);

  const sendMessage = useCallback(async (question, docIds = []) => {
    if (!currentConversation || streaming) return;

    const userMsg = { id: `u-${Date.now()}`, role: 'user', content: question, sources: [], created_at: new Date().toISOString() };
    setMessages((p) => [...p, userMsg]);
    setStreaming(true);
    setStreamingContent('');
    setSources([]);
    setHallucinationInfo(null);
    setError(null);
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    let accumulated = '';
    let finalSources = [];
    let finalHallucination = null;

    try {
      const resp = await apiStream(currentConversation.id, question, docIds, abortRef.current.signal);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop();
        for (const line of lines) {
          const t = line.trim();
          if (!t.startsWith('data:')) continue;
          const raw = t.slice(5).trim();
          if (raw === '[DONE]') continue;
          try {
            const ev = JSON.parse(raw);
            if (ev.type === 'chunk') { accumulated += ev.content || ''; if (mountedRef.current) setStreamingContent(accumulated); }
            else if (ev.type === 'sources') { finalSources = ev.sources || []; if (mountedRef.current) setSources(finalSources); }
            else if (ev.type === 'hallucination') {
              finalHallucination = { score: ev.score, label: ev.label };
              if (mountedRef.current) setHallucinationInfo(finalHallucination);
            }
          } catch { /* skip */ }
        }
      }

      if (mountedRef.current) {
        setMessages((p) => [...p, {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: accumulated,
          sources: finalSources,
          hallucination_score: finalHallucination?.score ?? null,
          created_at: new Date().toISOString(),
        }]);
        setStreamingContent('');
      }
    } catch (err) {
      if (err.name === 'AbortError') return;
      if (mountedRef.current) { setError('Response failed. Please try again.'); setStreamingContent(''); }
    } finally {
      if (mountedRef.current) setStreaming(false);
    }
  }, [currentConversation, streaming]);

  const clearSources = useCallback(() => { setSources([]); setHallucinationInfo(null); }, []);

  return {
    conversations, currentConversation, messages, streaming, streamingContent,
    sources, hallucinationInfo, loading, messagesLoading, error,
    fetchConversations, createConversation, selectConversation, sendMessage,
    deleteConversation, clearSources, clearError: () => setError(null),
  };
}

export default useChat;
