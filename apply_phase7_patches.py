#!/usr/bin/env python3
"""
Phase 7 patches for EXISTING files (small edits, so no full re-sends).
Run from the repo root:  python3 apply_phase7_patches.py
Each patch must match exactly once; if a file differs from what was expected the
script stops with a clear message and changes nothing else in that file.
Re-running is safe: already-applied patches are skipped.
"""
import sys
from pathlib import Path

P = []  # (path, old, new)

# ── api.js: a 401 (expired token) now sends you back to login instead of silently failing ──
P.append(("frontend/src/api.js", "export default api", """api.interceptors.response.use(
  (r) => r,
  (err) => {
    const url = String(err.config?.url || '')
    if (err.response?.status === 401 && !url.includes('/auth/login')) {
      localStorage.removeItem('token')
      window.dispatchEvent(new Event('auth:expired'))
    }
    return Promise.reject(err)
  }
)

export default api"""))

# ── App.jsx: project detail route, logout clears the stored token, auth-expired handling ──
A = "frontend/src/App.jsx"
P.append((A, "import React, { useState } from 'react'", "import React, { useState, useEffect } from 'react'"))
P.append((A, "import AddProject from './pages/AddProject'", "import AddProject from './pages/AddProject'\nimport ProjectDetail from './pages/ProjectDetail'"))
P.append((A, "const title = PAGE_TITLES[location.pathname] || 'Airdrop Agent'",
          "const title = PAGE_TITLES[location.pathname] || (/^\\/projects\\/\\d+$/.test(location.pathname) ? 'Project' : 'Airdrop Agent')"))
P.append((A, '<Route path="/projects/new" element={<AddProject token={token} />} />',
          '<Route path="/projects/new" element={<AddProject token={token} />} />\n            <Route path="/projects/:id" element={<ProjectDetail />} />'))
P.append((A, "const logout = () => setToken(null)",
          "const logout = () => { localStorage.removeItem('token'); setToken(null) }\n"
          "  useEffect(() => {\n"
          "    const h = () => setToken(null)\n"
          "    window.addEventListener('auth:expired', h)\n"
          "    return () => window.removeEventListener('auth:expired', h)\n"
          "  }, [])"))

# ── Dashboard.jsx: stats overview on top ──
D = "frontend/src/pages/Dashboard.jsx"
P.append((D, "import ServerStatus from '../components/ServerStatus'",
          "import ServerStatus from '../components/ServerStatus'\nimport StatsOverview from '../components/StatsOverview'"))
P.append((D, '<div className="grid">', '<StatsOverview />\n\n      <div className="grid">'))

# ── Projects.jsx: project name links to the new detail page ──
P.append(("frontend/src/pages/Projects.jsx", "<td style={{ fontWeight: 600 }}>{p.name}</td>",
          "<td style={{ fontWeight: 600 }}><Link to={`/projects/${p.id}`}>{p.name}</Link></td>"))

# ── Wallets.jsx: Manage button + panel ──
W = "frontend/src/pages/Wallets.jsx"
P.append((W, "import Spinner from '../components/Spinner'", "import Spinner from '../components/Spinner'\nimport WalletManage from '../components/WalletManage'"))
P.append((W, "const [copiedId, setCopiedId] = useState(null)", "const [copiedId, setCopiedId] = useState(null)\n  const [managing, setManaging] = useState(null)"))
P.append((W, "<button className=\"sm danger\" onClick={() => toggleStatus(w.id, 'archived')}>Archive</button>",
          "<button className=\"sm\" onClick={() => setManaging(managing === w.id ? null : w.id)}>Manage</button>\n"
          "                    <button className=\"sm danger\" onClick={() => toggleStatus(w.id, 'archived')}>Archive</button>"))
P.append((W, '<Card title="All wallets">',
          "{managing && <WalletManage wallet={wallets.find(x => x.id === managing)} onChanged={fetchWallets} onClose={() => setManaging(null)} />}\n\n"
          '      <Card title="All wallets">'))

# ── Settings.jsx (Phase 6 version): add system controls ──
S = "frontend/src/pages/Settings.jsx"
P.append((S, "import AutonomyPanel from '../components/AutonomyPanel'",
          "import AutonomyPanel from '../components/AutonomyPanel'\nimport SystemPanel from '../components/SystemPanel'"))
P.append((S, "<AutonomyPanel />", "<SystemPanel />\n      <AutonomyPanel />"))

# ── Snapshot.jsx: /projects -> /projects/ (avoids a redirect that can drop the auth header) ──
P.append(("frontend/src/pages/Snapshot.jsx", "${API_BASE}/projects`", "${API_BASE}/projects/`"))

# ── Sybil.jsx: endpoint returns {suspicious_pairs,...}, not a list; also /wallets/ ──
Y = "frontend/src/pages/Sybil.jsx"
P.append((Y, "setPairs(Array.isArray(s) ? s : [])", "setPairs(Array.isArray(s) ? s : (s.suspicious_pairs || []))"))
P.append((Y, "${API_BASE}/wallets`", "${API_BASE}/wallets/`"))

# ── vite.config.js: dev proxy for the new routes ──
P.append(("frontend/vite.config.js", "'/reports': 'http://localhost:8002',",
          "'/reports': 'http://localhost:8002',\n      '/ops': 'http://localhost:8002',\n      '/stats': 'http://localhost:8002',\n      '/proxies': 'http://localhost:8002',\n      '/autonomy': 'http://localhost:8002',"))


def main():
    cache, failed = {}, False
    for path, old, new in P:
        f = Path(path)
        if not f.exists():
            print(f"MISSING  {path}"); failed = True; continue
        text = cache.get(path, f.read_text())
        if new in text and old not in text.replace(new, ""):
            print(f"skip     {path}  ({old[:40]!r} already applied)")
            cache[path] = text
            continue
        if text.count(old) != 1:
            print(f"NO MATCH {path}  expected exactly one {old[:60]!r}, found {text.count(old)}")
            failed = True; continue
        cache[path] = text.replace(old, new)
        print(f"patched  {path}  ({old[:40]!r})")
    if failed:
        print("\nSome patches failed. Nothing was written. Fix or send me that file, then re-run.")
        sys.exit(1)
    for path, text in cache.items():
        Path(path).write_text(text)
    print("\nAll patches written.")


if __name__ == "__main__":
    main()
