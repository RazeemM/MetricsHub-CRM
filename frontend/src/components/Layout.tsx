import {
  ActionIcon,
  AppShell,
  Autocomplete,
  Avatar,
  Burger,
  Group,
  Menu,
  NavLink,
  Text,
  useMantineColorScheme,
} from '@mantine/core'
import { useDebouncedValue, useDisclosure } from '@mantine/hooks'
import {
  IconAddressBook,
  IconBuilding,
  IconFileImport,
  IconFileInvoice,
  IconLayoutDashboard,
  IconLayoutKanban,
  IconListDetails,
  IconMail,
  IconMailCog,
  IconLogout,
  IconMoon,
  IconPackage,
  IconSearch,
  IconSun,
  IconTargetArrow,
  IconUsers,
} from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { fmtDate } from '../labels'
import { NotificationsBell } from './Licences'
import { Logo } from './Logo'

const NAV = [
  { to: '/', label: 'Dashboard', icon: IconLayoutDashboard },
  { to: '/pipeline', label: 'Pipeline', icon: IconLayoutKanban },
  { to: '/opportunities', label: 'Opportunities', icon: IconTargetArrow },
  { to: '/accounts', label: 'Accounts', icon: IconBuilding },
  { to: '/contacts', label: 'Contacts', icon: IconAddressBook },
  { to: '/products', label: 'Products & pricing', icon: IconPackage },
  { to: '/quote-templates', label: 'Quote templates', icon: IconFileInvoice },
  { to: '/email/campaigns', label: 'Campaigns', icon: IconMail },
  { to: '/email/templates', label: 'Email templates', icon: IconMailCog },
  { to: '/email/lists', label: 'Mailing lists', icon: IconListDetails },
  { to: '/import', label: 'Import / export', icon: IconFileImport },
]

interface SearchResult {
  accounts: {
    id: number
    name: string
    licences: { products: { product: string; quantity: string; renewal_date: string | null; status: string }[]; next_renewal: string | null; lapsed: number } | null
  }[]
  contacts: { id: number; name: string; email: string }[]
  opportunities: { id: number; name: string }[]
}

function GlobalSearch() {
  const [q, setQ] = useState('')
  const [debounced] = useDebouncedValue(q, 250)
  const nav = useNavigate()
  const { data } = useQuery({
    queryKey: ['search', debounced],
    queryFn: () => api<SearchResult>('/search', { params: { q: debounced } }),
    enabled: debounced.trim().length >= 2,
  })
  const groups = data
    ? [
        { group: 'Opportunities', items: data.opportunities.map((o) => ({ value: `/opportunities/${o.id}`, label: o.name })) },
        {
          group: 'Accounts',
          items: data.accounts.map((a) => ({
            value: a.licences ? `/accounts/${a.id}?tab=licences` : `/accounts/${a.id}`,
            label: a.licences
              ? `${a.name} · ${a.licences.products.length} product${a.licences.products.length === 1 ? '' : 's'}` +
                (a.licences.next_renewal ? ` · renews ${fmtDate(a.licences.next_renewal)}` : '') +
                (a.licences.lapsed ? ` · ${a.licences.lapsed} lapsed` : '')
              : a.name,
          })),
        },
        {
          group: 'Contacts',
          items: data.contacts.map((c) => ({ value: `/contacts/${c.id}`, label: `${c.name}${c.email ? ` · ${c.email}` : ''}` })),
        },
      ].filter((g) => g.items.length)
    : []
  return (
    <Autocomplete
      placeholder="Search accounts, contacts, deals…"
      leftSection={<IconSearch size={16} />}
      w={{ base: 180, sm: 360 }}
      value={q}
      onChange={setQ}
      data={groups}
      filter={({ options }) => options}
      onOptionSubmit={(v) => {
        setQ('')
        nav(v)
      }}
    />
  )
}

export default function Layout() {
  const [opened, { toggle, close }] = useDisclosure()
  const { user, logout, isAdmin } = useAuth()
  const loc = useLocation()
  const nav = useNavigate()
  const { colorScheme, toggleColorScheme } = useMantineColorScheme()
  const items = isAdmin ? [...NAV, { to: '/users', label: 'Users', icon: IconUsers }] : NAV
  const active = (to: string) => (to === '/' ? loc.pathname === '/' : loc.pathname.startsWith(to))

  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 230, breakpoint: 'sm', collapsed: { mobile: !opened } }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Logo size={28} />
            <Text fw={700} visibleFrom="sm">
              CRM
            </Text>
          </Group>
          <GlobalSearch />
          <Group gap="xs" wrap="nowrap">
            <NotificationsBell />
            <ActionIcon variant="subtle" onClick={toggleColorScheme} aria-label="Toggle color scheme">
              {colorScheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
            </ActionIcon>
            <Menu position="bottom-end">
              <Menu.Target>
                <Avatar radius="xl" color="violet" style={{ cursor: 'pointer' }}>
                  {user?.full_name
                    .split(' ')
                    .map((p) => p[0])
                    .slice(0, 2)
                    .join('')}
                </Avatar>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>
                  {user?.full_name} · {user?.role}
                </Menu.Label>
                <Menu.Item leftSection={<IconLogout size={16} />} onClick={logout}>
                  Sign out
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs">
        {items.map((it) => (
          <NavLink
            key={it.to}
            label={it.label}
            leftSection={<it.icon size={18} />}
            active={active(it.to)}
            onClick={() => {
              nav(it.to)
              close()
            }}
            style={{ borderRadius: 8 }}
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  )
}
