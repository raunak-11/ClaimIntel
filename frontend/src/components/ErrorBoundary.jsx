import { Component } from 'react'
import { AlertTriangle } from 'lucide-react'

export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen bg-canvas flex items-center justify-center px-4">
          <div className="text-center max-w-md bg-surface border border-line rounded-2xl shadow-sm p-10">
            <span className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-danger-50 text-danger-600 mb-5">
              <AlertTriangle className="w-7 h-7" />
            </span>
            <h1 className="text-xl font-semibold tracking-tight text-ink mb-2">Something went wrong</h1>
            <p className="text-muted text-sm mb-6">
              {this.state.error?.message || 'An unexpected error occurred.'}
            </p>
            <button
              onClick={() => {
                this.setState({ error: null })
                window.location.href = '/'
              }}
              className="inline-flex items-center justify-center px-5 py-2.5 bg-brand-500 hover:bg-brand-600 text-white rounded-lg text-sm font-semibold transition-colors"
            >
              Back to Claims Queue
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
