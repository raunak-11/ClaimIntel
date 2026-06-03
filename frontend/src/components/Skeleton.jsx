export function SkeletonBar({ w = 'w-full', h = 'h-4' }) {
  return <div className={`${w} ${h} bg-slate-700/60 rounded animate-pulse`} />
}

export function SkeletonCard({ rows = 3 }) {
  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-700 p-5 space-y-3">
      <SkeletonBar w="w-1/3" h="h-3" />
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonBar key={i} w={i % 2 === 0 ? 'w-full' : 'w-3/4'} />
      ))}
    </div>
  )
}

export function SkeletonTableRows({ rows = 5 }) {
  return Array.from({ length: rows }).map((_, i) => (
    <tr key={i} className="border-b border-slate-700/60">
      {[32, 24, 36, 20, 20, 16, 16].map((w, j) => (
        <td key={j} className="px-4 py-3">
          <div className={`h-4 bg-slate-700/60 rounded animate-pulse`} style={{ width: `${w * 4}px` }} />
        </td>
      ))}
    </tr>
  ))
}

export function SkeletonDashboard() {
  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <SkeletonBar w="w-24" h="h-3" />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <SkeletonCard rows={5} />
        <SkeletonCard rows={6} />
        <SkeletonCard rows={4} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SkeletonCard rows={3} />
        <SkeletonCard rows={4} />
      </div>
    </div>
  )
}
