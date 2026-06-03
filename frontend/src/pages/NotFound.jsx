import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-96 text-center">
      <p className="text-6xl font-bold text-slate-700 mb-4">404</p>
      <p className="text-slate-400 mb-6">Page not found</p>
      <Link to="/" className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg">
        Back to Claims Queue
      </Link>
    </div>
  )
}
