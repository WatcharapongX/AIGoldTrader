export default function DashboardPage() {
  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-100">Dashboard</h1>
        <span className="px-3 py-1 bg-amber-500/20 text-amber-500 text-xs font-semibold rounded-full border border-amber-500/30">
          Coming in Phase 2+
        </span>
      </div>
      
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-8">
        <h2 className="text-xl font-semibold text-gray-200 mb-4">Overview</h2>
        <p className="text-gray-400">
          Overview of trading activity, market status, and key metrics will be displayed here.
        </p>
      </div>
    </div>
  );
}
