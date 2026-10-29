import { Alert, Anchor, Badge, Button, Card, Group, Loader, SimpleGrid, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { IconAlertTriangle, IconCircleCheck, IconCircleX, IconRefresh } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { PageHeader } from '../components/common'
import { InfoTip, Stat } from '../components/ui'
import { useApiMutation } from '../hooks'

type State = 'ok' | 'degraded' | 'failed'

interface Check {
  name: string
  label: string
  status: State
  message: string
}

interface Status {
  status: State
  version: string
  checked_at: string
  started_at: string
  uptime_seconds: number
  checks: Check[]
  http?: { requests: number; client_errors: number; server_errors: number; average_ms: number | null }
  records?: Record<string, number>
  users?: { enabled: number; active_24h: number; active_7d: number }
  email?: Record<string, number | string>
  forms?: { accepted: number; pending: number; spam: number; error: number; last_24h: number }
  database?: { size_bytes: number; connections: number; max_connections: number; version: string }
  backups?: {
    count: number
    total_bytes: number
    last_file: string | null
    last_at: string | null
    age_seconds: number | null
    disk_free_bytes: number | null
    disk_total_bytes: number | null
    recent: { file: string; bytes: number; at: string }[]
  } | null
  recent?: {
    mail_failures: { at: string; purpose: string; error: string; sender: string | null; to: string | null }[]
    campaign_failures: { email: string; reason: string | null; at: string | null; campaign: string }[]
    paused_campaigns: { id: number; name: string; error: string | null }[]
    imports: { id: number; entity: string; filename: string; total: number; created: number; updated: number; skipped: number; errors: number; at: string }[]
    logins: { name: string; email: string; role: string; at: string }[]
  }
  tables?: { table: string; rows: number; bytes: number }[]
}

const COLORS: Record<State, string> = { ok: 'green', degraded: 'orange', failed: 'red' }
const ICONS: Record<State, typeof IconCircleCheck> = { ok: IconCircleCheck, degraded: IconAlertTriangle, failed: IconCircleX }
const LABELS: Record<State, string> = { ok: 'Healthy', degraded: 'Needs attention', failed: 'Failing' }
const RECORDS: Record<string, string> = {
  accounts: 'Accounts',
  contacts: 'Contacts',
  opportunities: 'Opportunities',
  open_opportunities: 'Open opportunities',
  quotes: 'Quotes',
  licences: 'Licences',
  activities: 'Activities',
  campaigns: 'Campaigns',
  lists: 'Lists',
  users: 'Users',
}

const n = (v: number | null | undefined) => (v ?? 0).toLocaleString('en-US')
const when = (d: string | null | undefined) =>
  d ? new Date(d).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'

function bytes(v: number | null | undefined) {
  if (v == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let x = v
  while (x >= 1024 && i < units.length - 1) {
    x /= 1024
    i++
  }
  return `${x.toFixed(i && x < 10 ? 1 : 0)} ${units[i]}`
}

function duration(seconds: number | null | undefined) {
  if (seconds == null) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return d ? `${d} d ${h} h` : h ? `${h} h ${m} min` : `${m} min`
}

function Section({ title, info, children }: { title: string; info?: ReactNode; children: ReactNode }) {
  return (
    <Card withBorder>
      <Group gap={6} mb="sm">
        <Title order={5}>{title}</Title>
        <InfoTip info={info} />
      </Group>
      {children}
    </Card>
  )
}

function TestEmail() {
  const [to, setTo] = useState('')
  const send = useApiMutation(() => api('/mail/test', { method: 'POST', body: { to } }), { invalidate: [['system-status']], success: 'Test email sent' })
  return (
    <Group align="flex-end" gap="xs">
      <TextInput size="xs" label="Send a test email to" placeholder="you@metricshub.com" value={to} onChange={(e) => setTo(e.target.value)} w={260} />
      <Button size="xs" variant="default" disabled={!to.includes('@')} loading={send.isPending} onClick={() => send.mutate(undefined)}>
        Send test
      </Button>
    </Group>
  )
}

/** Admin page: health checks and usage statistics, the same data MetricsHub reads from /api/monitoring/status. */
export default function SystemStatus() {
  const { isAdmin } = useAuth()
  const { data: s, isFetching, refetch, error } = useQuery({
    queryKey: ['system-status'],
    queryFn: () => api<Status>('/monitoring/status'),
    refetchInterval: 30_000,
    enabled: isAdmin,
  })
  if (!isAdmin) return <Navigate to="/" replace />
  const Icon = s ? ICONS[s.status] : IconCircleCheck
  const e = s?.email
  const b = s?.backups
  const r = s?.recent

  return (
    <>
      <PageHeader
        title="System status"
        subtitle="Health checks and usage statistics. MetricsHub and Prometheus read the same figures: see Monitoring in the README."
        actions={
          <Button variant="default" leftSection={<IconRefresh size={16} />} loading={isFetching} onClick={() => refetch()}>
            Refresh
          </Button>
        }
      />
      {error && <Alert color="red">{(error as Error).message}</Alert>}
      {!s && !error && <Loader />}
      {s && (
        <Stack>
          <Alert color={COLORS[s.status]} variant="light" icon={<Icon />} title={LABELS[s.status]}>
            <Text size="sm">
              Version {s.version} · running for {duration(s.uptime_seconds)} (since {when(s.started_at)}) · checked {when(s.checked_at)}
            </Text>
          </Alert>

          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
            {s.checks.map((c) => {
              const CIcon = ICONS[c.status]
              return (
                <Card key={c.name} withBorder padding="md">
                  <Group justify="space-between" wrap="nowrap">
                    <Group gap={8} wrap="nowrap">
                      <CIcon size={20} color={`var(--mantine-color-${COLORS[c.status]}-6)`} />
                      <Text fw={600}>{c.label}</Text>
                    </Group>
                    <Badge color={COLORS[c.status]} variant="light">
                      {c.status}
                    </Badge>
                  </Group>
                  <Text size="sm" c="dimmed" mt={6} style={{ overflowWrap: 'anywhere' }}>
                    {c.message}
                  </Text>
                </Card>
              )
            })}
          </SimpleGrid>

          {s.http && s.users && s.database && (
            <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }}>
              <Stat label="API requests" value={n(s.http.requests)} hint="since the API started" info="Requests answered by the API, not counting health checks and monitoring. Starts again from zero when the API restarts." />
              <Stat
                label="Errors"
                value={`${n(s.http.server_errors)} / ${n(s.http.client_errors)}`}
                hint="server (5xx) / client (4xx)"
                info="Server errors are bugs or outages and worth a look. Client errors are mostly normal: expired sign-ins, validation messages, pages not found."
              />
              <Stat label="Average response" value={s.http.average_ms == null ? '—' : `${s.http.average_ms} ms`} info="Average time the API took to answer, since it started. Imports and exports raise it." />
              <Stat label="Users signed in" value={n(s.users.active_24h)} hint={`last 24 h · ${n(s.users.active_7d)} in 7 days · ${n(s.users.enabled)} enabled`} info="Users whose last sign-in was in the last 24 hours, the last 7 days, and the number of enabled accounts." />
              <Stat label="Database" value={bytes(s.database.size_bytes)} hint={`${s.database.connections} / ${s.database.max_connections} connections`} info="Size of the PostgreSQL database, and open connections against the server's limit." />
              <Stat
                label="Last backup"
                value={b ? duration(b.age_seconds) + ' ago' : '—'}
                hint={b ? `${bytes(b.disk_free_bytes)} free on the backup disk` : 'Backup folder not mounted'}
                info="Age of the newest nightly dump in the backups folder. Over 26 hours is degraded, over 50 hours failed."
              />
            </SimpleGrid>
          )}

          {e && (
            <Section title="Email">
              <SimpleGrid cols={{ base: 2, sm: 4 }} mb="md">
                <Stat label="Sent" value={n(Number(e.transactional_sent) + Number(e.bulk_sent))} hint="since the API started" info="Quotes, emails written in the CRM, notices and campaign emails accepted by the mail server." />
                <Stat label="Failed" value={n(Number(e.transactional_failed) + Number(e.bulk_failed))} hint="since the API started" info="Sends the mail server refused, or that could not start because email is not set up. The table below lists the last ones." />
                <Stat label="Campaign queue" value={n(Number(e.recipients_queued))} hint={`${n(Number(e.campaigns_sending))} sending · ${n(Number(e.campaigns_paused))} paused`} info="Campaign recipients waiting to be sent. A campaign pauses when the mail server refuses it, and the reason shows below." />
                <Stat label="Campaign recipients" value={n(Number(e.recipients_sent))} hint={`${n(Number(e.recipients_failed))} failed · ${n(Number(e.recipients_skipped))} skipped`} info="All campaign emails ever sent, with those refused and those skipped (no address, unsubscribed, no consent)." />
              </SimpleGrid>
              <Text size="sm" c="dimmed" mb="xs">
                Backend: {String(e.backend)}
                {e.bulk_backend !== e.backend ? ` · campaigns: ${String(e.bulk_backend)}` : ''}
              </Text>
              <TestEmail />
              {r && r.paused_campaigns.length > 0 && (
                <Alert color="orange" variant="light" mt="md" title="Paused campaigns">
                  {r.paused_campaigns.map((c) => (
                    <Text size="sm" key={c.id}>
                      <Anchor component={Link} to={`/email/campaigns/${c.id}`}>
                        {c.name}
                      </Anchor>
                      : {c.error ?? 'no reason recorded'}
                    </Text>
                  ))}
                </Alert>
              )}
              {r && r.mail_failures.length > 0 && (
                <Table fz="sm" mt="md" striped>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>When</Table.Th>
                      <Table.Th>Kind</Table.Th>
                      <Table.Th>From → to</Table.Th>
                      <Table.Th>Error</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {r.mail_failures.map((f, i) => (
                      <Table.Tr key={i}>
                        <Table.Td style={{ whiteSpace: 'nowrap' }}>{when(f.at)}</Table.Td>
                        <Table.Td>{f.purpose === 'bulk' ? 'Campaign' : 'Email'}</Table.Td>
                        <Table.Td>{f.sender ? `${f.sender} → ${f.to}` : '—'}</Table.Td>
                        <Table.Td style={{ overflowWrap: 'anywhere' }}>{f.error}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Section>
          )}

          <SimpleGrid cols={{ base: 1, lg: 2 }}>
            {s.records && (
              <Section title="Records">
                <Table fz="sm">
                  <Table.Tbody>
                    {Object.entries(s.records).map(([k, v]) => (
                      <Table.Tr key={k}>
                        <Table.Td>{RECORDS[k] ?? k}</Table.Td>
                        <Table.Td ta="right">{n(v)}</Table.Td>
                      </Table.Tr>
                    ))}
                    {s.forms && (
                      <Table.Tr>
                        <Table.Td>Website form submissions</Table.Td>
                        <Table.Td ta="right">
                          {n(s.forms.accepted)} ({n(s.forms.last_24h)} in 24 h, {n(s.forms.spam)} spam)
                        </Table.Td>
                      </Table.Tr>
                    )}
                  </Table.Tbody>
                </Table>
              </Section>
            )}
            {s.tables && s.database && (
              <Section title={`Largest tables · PostgreSQL ${s.database.version}`} info="Size on disk includes indexes. Row counts are PostgreSQL's estimates.">
                <Table fz="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Table</Table.Th>
                      <Table.Th ta="right">Rows</Table.Th>
                      <Table.Th ta="right">Size</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {s.tables.map((t) => (
                      <Table.Tr key={t.table}>
                        <Table.Td>{t.table}</Table.Td>
                        <Table.Td ta="right">{n(t.rows)}</Table.Td>
                        <Table.Td ta="right">{bytes(t.bytes)}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Section>
            )}
            {b && (
              <Section title={`Backups · ${b.count} kept, ${bytes(b.total_bytes)}`}>
                <Table fz="sm">
                  <Table.Tbody>
                    {b.recent.map((f) => (
                      <Table.Tr key={f.file}>
                        <Table.Td>{f.file}</Table.Td>
                        <Table.Td>{when(f.at)}</Table.Td>
                        <Table.Td ta="right">{bytes(f.bytes)}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Section>
            )}
            {r && (
              <Section title="Recent sign-ins">
                <Table fz="sm">
                  <Table.Tbody>
                    {r.logins.map((u) => (
                      <Table.Tr key={u.email}>
                        <Table.Td>{u.name}</Table.Td>
                        <Table.Td c="dimmed">{u.role}</Table.Td>
                        <Table.Td ta="right">{when(u.at)}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Section>
            )}
            {r && r.imports.length > 0 && (
              <Section title="Recent imports">
                <Table fz="sm">
                  <Table.Tbody>
                    {r.imports.map((j) => (
                      <Table.Tr key={j.id}>
                        <Table.Td>
                          {j.filename}
                          <Text size="xs" c="dimmed">
                            {j.entity} · {when(j.at)}
                          </Text>
                        </Table.Td>
                        <Table.Td ta="right">
                          {n(j.created)} created · {n(j.updated)} updated
                          {j.errors > 0 && (
                            <Text size="xs" c="red">
                              {j.errors} errors
                            </Text>
                          )}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Section>
            )}
            {r && r.campaign_failures.length > 0 && (
              <Section title="Recent campaign failures">
                <Table fz="sm">
                  <Table.Tbody>
                    {r.campaign_failures.map((f, i) => (
                      <Table.Tr key={i}>
                        <Table.Td>
                          {f.email}
                          <Text size="xs" c="dimmed">
                            {f.campaign}
                          </Text>
                        </Table.Td>
                        <Table.Td style={{ overflowWrap: 'anywhere' }}>{f.reason ?? '—'}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Section>
            )}
          </SimpleGrid>
        </Stack>
      )}
    </>
  )
}
