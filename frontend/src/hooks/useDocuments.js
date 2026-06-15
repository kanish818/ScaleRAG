import { useState, useCallback, useRef, useEffect } from 'react';
import { getDocuments as apiGet, uploadDocuments as apiUpload, deleteDocument as apiDelete } from '../services/api';

const POLL_MS = 1500;

export function useDocuments() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);
  const mountedRef = useRef(true);

  useEffect(() => { mountedRef.current = true; return () => { mountedRef.current = false; clearTimeout(pollRef.current); }; }, []);

  const fetchDocuments = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    try {
      const docs = await apiGet();
      if (mountedRef.current) setDocuments(docs);
      return docs;
    } catch (err) {
      if (mountedRef.current) setError(err.response?.data?.detail || 'Failed to load documents.');
      return [];
    } finally {
      if (mountedRef.current && !silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const processing = documents.some((d) => ['queued', 'processing'].includes(d.status));
    if (processing) {
      pollRef.current = setTimeout(() => mountedRef.current && fetchDocuments({ silent: true }), POLL_MS);
    }
    return () => clearTimeout(pollRef.current);
  }, [documents, fetchDocuments]);

  const uploadFiles = useCallback(async (files) => {
    if (!files?.length) return [];
    setUploading(true);
    setUploadProgress(0);
    setError(null);
    try {
      const uploaded = await apiUpload(files, (pct) => mountedRef.current && setUploadProgress(pct));
      if (mountedRef.current) {
        setDocuments((prev) => {
          const ids = new Set(prev.map((d) => d.id));
          return [...uploaded.filter((d) => !ids.has(d.id)), ...prev];
        });
        setUploadProgress(100);
      }
      await fetchDocuments({ silent: true });
      return uploaded;
    } catch (err) {
      if (mountedRef.current) setError(err.response?.data?.detail || 'Upload failed.');
      return [];
    } finally {
      if (mountedRef.current) {
        setUploading(false);
        setTimeout(() => mountedRef.current && setUploadProgress(0), 1500);
      }
    }
  }, [fetchDocuments]);

  const deleteDocument = useCallback(async (id) => {
    setDocuments((prev) => prev.filter((d) => d.id !== id));
    try { await apiDelete(id); } catch { if (mountedRef.current) fetchDocuments({ silent: true }); }
  }, [fetchDocuments]);

  return { documents, loading, uploading, uploadProgress, error, fetchDocuments, uploadFiles, deleteDocument, clearError: () => setError(null) };
}

export default useDocuments;
