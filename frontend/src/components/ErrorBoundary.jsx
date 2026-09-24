import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
          <div className="card" style={{ maxWidth: 440, textAlign: 'center' }}>
            <div style={{ fontSize: 28, marginBottom: 10 }}>⚠</div>
            <h2 style={{ fontSize: 17, marginBottom: 8 }}>Something went wrong</h2>
            <p style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 18 }}>
              {this.state.error?.message || 'An unexpected error occurred while rendering this view.'}
            </p>
            <button className="primary" onClick={() => this.setState({ hasError: false })}>Try again</button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
