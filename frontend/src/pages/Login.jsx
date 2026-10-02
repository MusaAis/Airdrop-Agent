import React, { useState } from 'react'
import api from '../api'
import Spinner from '../components/Spinner'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [rememberDevice, setRememberDevice] = useState(true)
  const [needsTotp, setNeedsTotp] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const attemptLogin = async (payload) => {
    const res = await api.post('/auth/login', payload)
    localStorage.setItem('token', res.data.access_token)
    onLogin(res.data.access_token)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await attemptLogin({
        username,
        password,
        totp_code: needsTotp ? totpCode : undefined,
        remember_device: rememberDevice,
      })
    } catch (err) {
      const detail = err.response?.data?.detail
      if (detail === 'totp_required') {
        setNeedsTotp(true)
        setError('Enter the 6-digit code from your authenticator app.')
      } else if (detail) {
        setError(detail)
      } else if (err.message === 'Network Error') {
        setError('Cannot connect to server. Check your internet and API URL.')
      } else {
        setError('Invalid credentials')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="login-wrap"
      style={{
        backgroundImage:
          'radial-gradient(circle at 20% 20%, rgba(94,234,212,0.08), transparent 45%), radial-gradient(circle at 80% 80%, rgba(167,139,250,0.07), transparent 45%)',
      }}
    >
      <div className="fade-in" style={{ width: '100%', maxWidth: 400 }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, marginBottom: 28 }}>
          <div style={{
            width: 48, height: 48, borderRadius: 12,
            background: 'linear-gradient(135deg, var(--signal), var(--violet))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 22, color: '#06151A',
            boxShadow: '0 0 32px rgba(94,234,212,0.25)',
          }}>
            A
          </div>
          <div style={{ textAlign: 'center' }}>
            <h1 style={{ fontSize: 20 }}>Airdrop Agent</h1>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-dim)' }}>Autonomous on-chain operations</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-faint)', marginBottom: 2 }}>
            <span className="pulse-dot" />
            Master access required
          </div>

          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-dim)', fontWeight: 600 }}>Username</span>
            <input
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="admin"
              autoComplete="username"
              disabled={needsTotp}
              required
            />
          </label>

          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-dim)', fontWeight: 600 }}>Master Password</span>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••••"
              autoComplete="current-password"
              disabled={needsTotp}
              required
            />
          </label>

          {needsTotp && (
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-dim)', fontWeight: 600 }}>Authenticator code</span>
              <input
                value={totpCode}
                onChange={e => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="123456"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]*"
                maxLength={6}
                autoFocus
                required
              />
            </label>
          )}

          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-dim)' }}>
            <input
              type="checkbox"
              checked={rememberDevice}
              onChange={e => setRememberDevice(e.target.checked)}
              style={{ width: 'auto' }}
            />
            Remember this device
          </label>

          <button type="submit" className="primary" disabled={loading} style={{ marginTop: 6, width: '100%', padding: '11px 16px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            {loading ? <Spinner inline /> : needsTotp ? 'Verify code' : 'Sign in'}
          </button>

          {error && <p className="error" style={{ margin: 0 }}>{error}</p>}
        </form>

        <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--text-faint)', marginTop: 18 }}>
          Single-operator control panel · Keep your master password private
        </p>
      </div>
    </div>
  )
}
