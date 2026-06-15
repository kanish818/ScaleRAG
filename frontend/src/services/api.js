import axios from 'axios';

const runtimeOrigin = window.__SCALERAG_CONFIG__?.API_ORIGIN || '';
const apiOrigin = (runtimeOrigin || import.meta.env.VITE_API_ORIGIN || '').replace(/\/+$/, '');
const API_BASE_URL = apiOrigin ? `${apiOrigin}/api` : '/api';

const api = axios.create({ baseURL: API_BASE_URL, headers: { 'Content-Type': 'application/json' } });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('scalerag_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('scalerag_token');
      window.location.href = '/';
    }
    return Promise.reject(error);
  }
);

// Auth
export const login = async (email, password) => (await api.post('/auth/login', { email, password })).data;
export const register = async (name, email, password) => (await api.post('/auth/register', { name, email, password })).data;
export const getMe = async () => (await api.get('/auth/me')).data;
export const googleAuth = () => { window.location.href = `${API_BASE_URL}/auth/google`; };

// Documents
export const getDocuments = async () => (await api.get('/documents/')).data;
export const uploadDocuments = async (files, onProgress) => {
  const form = new FormData();
  Array.from(files).forEach((f) => form.append('files', f));
  return (await api.post('/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => onProgress && e.total && onProgress(Math.round((e.loaded * 100) / e.total)),
  })).data;
};
export const deleteDocument = async (id) => (await api.delete(`/documents/${id}`)).data;

// Conversations
export const getConversations = async () => (await api.get('/chat/conversations')).data;
export const createConversation = async (title, documentIds) =>
  (await api.post('/chat/conversations', { title, document_ids: documentIds })).data;
export const deleteConversation = async (id) => (await api.delete(`/chat/conversations/${id}`)).data;
export const getMessages = async (id) => (await api.get(`/chat/conversations/${id}/messages`)).data;

export const streamChat = async (conversationId, question, documentIds, signal) => {
  const token = localStorage.getItem('scalerag_token');
  const resp = await fetch(`${API_BASE_URL}/chat/conversations/${conversationId}/stream`, {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ question, document_ids: documentIds }),
  });
  if (!resp.ok) {
    if (resp.status === 401) { localStorage.removeItem('scalerag_token'); window.location.href = '/'; }
    let detail = `Stream failed: ${resp.status}`;
    try {
      const payload = await resp.json();
      detail = payload.detail || detail;
    } catch {
      // Preserve the status-based fallback for non-JSON responses.
    }
    throw new Error(detail);
  }
  return resp;
};

export default api;
