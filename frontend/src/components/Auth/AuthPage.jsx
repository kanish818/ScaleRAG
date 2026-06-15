import React, { useState } from 'react';
import { useAuth } from '../../hooks/useAuth.jsx';
import { googleAuth } from '../../services/api';

function GoogleLogo() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M17.64 9.20459C17.64 8.56641 17.5827 7.95277 17.4764 7.36368H9V10.8451H13.8436C13.635 11.9701 13.0009 12.9233 12.0477 13.5615V15.8197H14.9564C16.6582 14.2528 17.64 11.9455 17.64 9.20459Z" fill="#4285F4"/>
      <path d="M9 18C11.43 18 13.4673 17.1941 14.9564 15.8195L12.0477 13.5614C11.2418 14.1014 10.2109 14.4204 9 14.4204C6.65591 14.4204 4.67182 12.8373 3.96409 10.71H0.957275V13.0418C2.43818 15.9832 5.48182 18 9 18Z" fill="#34A853"/>
      <path d="M3.96409 10.71C3.78409 10.17 3.68182 9.59323 3.68182 9.00005C3.68182 8.40687 3.78409 7.83005 3.96409 7.29005V4.95823H0.957273C0.347727 6.17323 0 7.54778 0 9.00005C0 10.4523 0.347727 11.8268 0.957273 13.0418L3.96409 10.71Z" fill="#FBBC05"/>
      <path d="M9 3.57955C10.3214 3.57955 11.5077 4.03364 12.4405 4.92545L15.0218 2.34409C13.4632 0.891818 11.4259 0 9 0C5.48182 0 2.43818 2.01682 0.957275 4.95818L3.96409 7.29C4.67182 5.16273 6.65591 3.57955 9 3.57955Z" fill="#EA4335"/>
    </svg>
  );
}

function EyeIcon({ open }) {
  return open ? (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
    </svg>
  ) : (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  );
}

export default function AuthPage() {
  const { login, register, error, clearError } = useAuth();
  const [tab, setTab] = useState('login');
  const [formData, setFormData] = useState({ name: '', email: '', password: '' });
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const handleTabSwitch = (t) => { setTab(t); setLocalError(''); clearError(); setFormData({ name: '', email: '', password: '' }); setShowPassword(false); };
  const handleChange = (e) => { setFormData((p) => ({ ...p, [e.target.name]: e.target.value })); setLocalError(''); if (error) clearError(); };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError('');
    const { name, email, password } = formData;
    if (!email.trim() || !email.includes('@')) { setLocalError('Valid email required.'); return; }
    if (!password || password.length < 6) { setLocalError('Password must be at least 6 characters.'); return; }
    if (tab === 'register' && !name.trim()) { setLocalError('Name is required.'); return; }
    setSubmitting(true);
    try {
      if (tab === 'login') await login(email, password);
      else await register(name, email, password);
    } catch (err) { setLocalError(err.message); }
    finally { setSubmitting(false); }
  };

  const displayError = localError || error;

  return (
    <div className="auth-page">
      <div className="auth-bg" aria-hidden="true">
        <div className="auth-bg-orb auth-bg-orb-1" />
        <div className="auth-bg-orb auth-bg-orb-2" />
        <div className="auth-bg-orb auth-bg-orb-3" />
      </div>
      <div className="auth-container">
        <div className="auth-card">
          <div className="auth-logo">
            <div className="auth-logo-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2 17l10 5 10-5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2 12l10 5 10-5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <span className="auth-logo-name">ScaleRAG</span>
          </div>
          <p className="auth-tagline">
            Production-grade document intelligence.<br/>
            PDF, HTML, CSV · 10,000+ documents · Hybrid RAG.
          </p>
          <div className="auth-tabs" role="tablist">
            <button role="tab" aria-selected={tab === 'login'} className={`auth-tab${tab === 'login' ? ' active' : ''}`} onClick={() => handleTabSwitch('login')} type="button">Sign In</button>
            <button role="tab" aria-selected={tab === 'register'} className={`auth-tab${tab === 'register' ? ' active' : ''}`} onClick={() => handleTabSwitch('register')} type="button">Create Account</button>
          </div>
          {displayError && (
            <div className="alert alert-error" role="alert" style={{ marginBottom: '16px' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              {displayError}
            </div>
          )}
          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            {tab === 'register' && (
              <div className="form-group">
                <label className="form-label" htmlFor="auth-name">Full Name</label>
                <input id="auth-name" name="name" type="text" className="form-input" placeholder="Jane Smith" value={formData.name} onChange={handleChange} autoComplete="name" disabled={submitting} />
              </div>
            )}
            <div className="form-group">
              <label className="form-label" htmlFor="auth-email">Email</label>
              <input id="auth-email" name="email" type="email" className="form-input" placeholder="you@example.com" value={formData.email} onChange={handleChange} autoComplete="email" disabled={submitting} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="auth-password">Password</label>
              <div style={{ position: 'relative' }}>
                <input id="auth-password" name="password" type={showPassword ? 'text' : 'password'} className="form-input" placeholder="••••••••" value={formData.password} onChange={handleChange} autoComplete={tab === 'login' ? 'current-password' : 'new-password'} disabled={submitting} style={{ paddingRight: '44px' }} />
                <button type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword((p) => !p)} style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', padding: '4px' }}>
                  <EyeIcon open={showPassword} />
                </button>
              </div>
            </div>
            <button type="submit" className="btn btn-primary auth-submit" disabled={submitting}>
              {submitting ? <><span className="spinner spinner-sm" />{tab === 'login' ? 'Signing in…' : 'Creating account…'}</> : (tab === 'login' ? 'Sign In' : 'Create Account')}
            </button>
          </form>
          <div className="divider" style={{ margin: '20px 0' }}>OR</div>
          <button type="button" className="btn btn-google auth-google" onClick={googleAuth} disabled={submitting}><GoogleLogo />Continue with Google</button>
        </div>
      </div>
    </div>
  );
}
