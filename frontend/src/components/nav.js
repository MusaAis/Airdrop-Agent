// Single source of truth for navigation (sidebar + phone bottom bar + "More" sheet + page titles).
export const NAV_GROUPS = [
  {
    label: 'Operate',
    items: [
      { to: '/',         label: 'Dashboard', icon: 'dashboard' },
      { to: '/wallets',  label: 'Wallets',   icon: 'wallets' },
      { to: '/balances', label: 'Balances',  icon: 'balances' },
      { to: '/projects', label: 'Projects',  icon: 'projects' },
      { to: '/tasks',    label: 'Tasks',     icon: 'tasks' },
      { to: '/chains',   label: 'Chains',    icon: 'chains' },
      { to: '/faucets',  label: 'Faucets',   icon: 'faucets' },
      { to: '/proxies',  label: 'Proxies',   icon: 'proxies' },
    ],
  },
  {
    label: 'Monitor',
    items: [
      { to: '/notifications', label: 'Alerts',    icon: 'notifications', badge: 'alerts' },
      { to: '/logs',          label: 'Logs',      icon: 'logs' },
      { to: '/reports',       label: 'Reports',   icon: 'reports' },
      { to: '/ai-log',        label: 'AI Log',    icon: 'ailog' },
      { to: '/sybil',         label: 'Sybil',     icon: 'sybil' },
      { to: '/snapshot',      label: 'Snapshots', icon: 'snapshot' },
      { to: '/claims',        label: 'Claims',    icon: 'claims' },
    ],
  },
  {
    label: 'System',
    items: [{ to: '/settings', label: 'Settings', icon: 'settings' }],
  },
]

export const ALL_ITEMS = NAV_GROUPS.flatMap(g => g.items)

// The four tabs pinned to the phone bottom bar (5th is "More").
export const PINNED = ['/', '/wallets', '/projects', '/notifications']

export const PAGE_TITLES = {
  '/': 'Dashboard', '/wallets': 'Wallets', '/balances': 'Balances', '/chains': 'Chains',
  '/tasks': 'Tasks', '/projects': 'Projects', '/projects/new': 'Add project',
  '/logs': 'Activity log', '/reports': 'Reports', '/faucets': 'Faucets', '/proxies': 'Proxies',
  '/settings': 'Settings', '/claims': 'Claims', '/ai-log': 'AI validation log',
  '/sybil': 'Sybil risk', '/snapshot': 'Snapshot calendar', '/notifications': 'Alerts',
}
