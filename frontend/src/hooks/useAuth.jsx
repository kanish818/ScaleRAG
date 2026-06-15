import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { login as apiLogin, register as apiRegister, getMe } from '../services/api';
import axios from 'axios';

const AuthContext = createContext(null);
const BACKEND_URL = (import.meta.env.VITE_API_ORIGIN || '').replace(/\/+$/, '') || '';

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('scalerag_token'));
  const [loading, setLoading] = useState(true);
  const [wakingUp, setWakingUp] = useState(false);
  const [error, setError] = useState(null);

  const persistToken = useCallback((t) => {
    t ? localStorage.setItem('scalerag_token', t) : localStorage.removeItem('scalerag_token');
    setToken(t);
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem('scalerag_token');
    (async () => {
      try {
        const pingUrl = BACKEND_URL ? `${BACKEND_URL}/` : '/api/auth/me';
        const timer = setTimeout(() => setWakingUp(true), 3000);
        await axios.get(pingUrl, { timeout: 60000 });
        clearTimeout(timer);
        setWakingUp(false);
      } catch { setWakingUp(false); }

      if (!stored) { setLoading(false); return; }
      try {
        const me = await getMe();
        setUser(me);
      } catch {
        persistToken(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []); // eslint-disable-line

  const handleGoogleCallback = useCallback(async () => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get('token');
    if (!t) return false;
    persistToken(t);
    window.history.replaceState({}, '', window.location.pathname);
    try {
      const me = await getMe();
      setUser(me);
      return true;
    } catch {
      persistToken(null);
      setError('Google sign-in failed.');
      return false;
    }
  }, [persistToken]);

  const login = useCallback(async (email, password) => {
    setError(null);
    try {
      const data = await apiLogin(email, password);
      persistToken(data.access_token);
      setUser(data.user);
      return data;
    } catch (err) {
      const msg = err.response?.data?.detail || 'Login failed.';
      setError(msg);
      throw new Error(msg);
    }
  }, [persistToken]);

  const register = useCallback(async (name, email, password) => {
    setError(null);
    try {
      const data = await apiRegister(name, email, password);
      persistToken(data.access_token);
      setUser(data.user);
      return data;
    } catch (err) {
      const msg = err.response?.data?.detail || 'Registration failed.';
      setError(msg);
      throw new Error(msg);
    }
  }, [persistToken]);

  const logout = useCallback(() => { persistToken(null); setUser(null); setError(null); }, [persistToken]);
  const clearError = useCallback(() => setError(null), []);

  return (
    <AuthContext.Provider value={{
      user, token, loading, wakingUp, error, login, register, logout,
      handleGoogleCallback, clearError, isAuthenticated: !!user,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside <AuthProvider>');
  return ctx;
}

export default useAuth;
