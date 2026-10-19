import { BarChart } from '@mantine/charts'
import { Alert, Anchor, Badge, Card, Group, NumberInput, SegmentedControl, Select, SimpleGrid, Stack, Table, Tabs, Text, Title, Tooltip, useComputedColorScheme } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { PageHeader } from '../components/common'
import { fmtDate, money } from '../labels'

const usd = (v: string | number) => money(Number(v), 'USD')
const num = (v: string | number) => Number(v)
const SERIES = { light: '#2a78d6', dark: '#3987e5' }

function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: string }) {
  return (
    <Card withBorder padding="sm">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text fw={700} size="xl" c={tone}>
        {value}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      )}
    </Card>
  )
}

/** A simple sortable table: click a header to sort by it. */
function DataTable<T>({ rows, cols, initial, maxHeight = 560, empty = 'Nothing to show.' }: {
  rows: T[]
  cols: { key: string; label: string; render: (r: T) => ReactNode; sort?: (r: T) => number | string; align?: 'right' }[]
  initial?: string
  maxHeight?: number
  empty?: string
}) {
  const [sort, setSort] = useState<{ key: string; desc: boolean } | null>(initial ? { key: initial, desc: true } : null)
  const sorted = useMemo(() => {
    const col = cols.find((c) => c.key === sort?.key)
    if (!col?.sort) return rows
    const f = col.sort
    return [...rows].sort((a, b) => {
      const x = f(a), y = f(b)
      const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
      return sort!.desc ? -c : c
    })
  }, [rows, cols, sort])
  if (!rows.length)
    return (
      <Text size="sm" c="dimmed">
        {empty}
      </Text>
    )
  return (
    <Table.ScrollContainer minWidth={760} mah={maxHeight}>
      <Table fz="sm" verticalSpacing={6} stickyHeader highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            {cols.map((c) => (
              <Table.Th
                key={c.key}
                ta={c.align}
                style={{ cursor: c.sort ? 'pointer' : undefined, whiteSpace: 'nowrap' }}
                onClick={() => c.sort && setSort({ key: c.key, desc: sort?.key === c.key ? !sort.desc : true })}
              >
                {c.label}
                {sort?.key === c.key ? (sort.desc ? ' ↓' : ' ↑') : ''}
              </Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {sorted.map((r, i) => (
            <Table.Tr key={i}>
              {cols.map((c) => (
                <Table.Td key={c.key} ta={c.align}>
                  {c.render(r)}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  )
}

const AccountLink = ({ id, name }: { id: number; name: string }) => (
  <Anchor component={Link} to={`/accounts/${id}?tab=licences`} size="sm">
    {name}
  </Anchor>
)

// ---------------------------------------------------------------- renewals at risk
interface Renewal {
  account_id: number
  account: string
  product: string
  quantity: string
  renewal_date: string
  days: number
  annual_value: string
  region: string
  reseller: string
  owner: string | null
  last_activity: string | null
  flags: string[]
}

function RenewalsTab() {
  const [months, setMonths] = useState<number | string>(6)
  const [only, setOnly] = useState('all')
  const { data } = useQuery({ queryKey: ['insights-renewals', months], queryFn: () => api<Renewal[]>('/insights/renewals', { params: { months: Number(months) || 6 } }) })
  if (!data) return null
  const rows = only === 'all' ? data : data.filter((r) => r.flags.length > 0)
  const total = data.reduce((n, r) => n + num(r.annual_value), 0)
  const atRisk = data.filter((r) => r.flags.includes('no renewal deal'))
  return (
    <Stack>
      <Group justify="space-between">
        <Group gap="xs">
          <Text size="sm">Renewing within</Text>
          <NumberInput size="xs" w={70} min={1} max={24} value={months} onChange={setMonths} />
          <Text size="sm">months</Text>
        </Group>
        <SegmentedControl size="xs" value={only} onChange={setOnly} data={[{ value: 'all', label: 'All' }, { value: 'flagged', label: 'Needs action' }]} />
      </Group>
      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <Stat label="Up for renewal" value={data.length} hint="licences (instalments excluded)" />
        <Stat label="Annual value" value={usd(total)} hint="at the current price" />
        <Stat label="No renewal deal yet" value={atRisk.length} hint={usd(atRisk.reduce((n, r) => n + num(r.annual_value), 0))} tone={atRisk.length ? 'orange' : undefined} />
        <Stat label="No activity in 90 days" value={data.filter((r) => r.flags.includes('no activity in 90 days')).length} />
      </SimpleGrid>
      <Card withBorder>
        <DataTable
          rows={rows}
          initial="value"
          empty="No licences renew in this window."
          cols={[
            { key: 'account', label: 'Customer', render: (r) => <AccountLink id={r.account_id} name={r.account} />, sort: (r) => r.account },
            { key: 'product', label: 'Product', render: (r) => <Text size="sm">{r.product}</Text>, sort: (r) => r.product },
            { key: 'date', label: 'Renews', render: (r) => <Text size="sm" style={{ whiteSpace: 'nowrap' }}>{fmtDate(r.renewal_date)} <Text span size="xs" c="dimmed">({r.days} d)</Text></Text>, sort: (r) => -r.days },
            { key: 'value', label: 'Annual value', align: 'right', render: (r) => usd(r.annual_value), sort: (r) => num(r.annual_value) },
            { key: 'reseller', label: 'Via', render: (r) => <Text size="xs">{r.reseller}</Text>, sort: (r) => r.reseller },
            { key: 'owner', label: 'Owner', render: (r) => r.owner ?? <Text size="xs" c="dimmed">—</Text>, sort: (r) => r.owner ?? '' },
            {
              key: 'flags',
              label: 'To do',
              render: (r) => (
                <Group gap={4}>
                  {r.flags.map((f) => (
                    <Badge key={f} size="xs" variant="light" color={f === 'no renewal deal' ? 'orange' : 'gray'}>
                      {f}
                    </Badge>
                  ))}
                </Group>
              ),
              sort: (r) => r.flags.length,
            },
          ]}
        />
      </Card>
    </Stack>
  )
}

// ---------------------------------------------------------------- retention
interface Retention {
  year: number
  previous_year: number
  partial_year: boolean
  data_from: string | null
  incomplete_base: boolean
  start_revenue: string
  retained_revenue: string
  nrr: number | null
  grr: number | null
  movement: { kind: string; customers: number; before: string; after: string }[]
  new_customers: number
  new_revenue: string
  by_region: Breakdown[]
  by_product: Breakdown[]
  by_reseller: Breakdown[]
  customers: { account_id: number; account: string; region: string; reseller: string; before: string; after: string; change: string; status: string }[]
}
interface Breakdown {
  name: string
  before: string
  after: string
  nrr: number | null
  churned: string
}

const MOVE_COLOR: Record<string, string> = { expanded: 'teal', retained: 'gray', contracted: 'orange', churned: 'red' }

function RetentionTab() {
  const thisYear = new Date().getFullYear()
  const [year, setYear] = useState(String(thisYear - 1))
  const [dim, setDim] = useState('region')
  const { data } = useQuery({ queryKey: ['insights-retention', year], queryFn: () => api<Retention>('/insights/retention', { params: { year } }) })
  if (!data) return null
  const mv = Object.fromEntries(data.movement.map((m) => [m.kind, m]))
  const breakdown = dim === 'region' ? data.by_region : dim === 'product' ? data.by_product : data.by_reseller
  return (
    <Stack>
      <Group gap="xs">
        <Text size="sm">Compare</Text>
        <Select size="xs" w={90} allowDeselect={false} value={year} onChange={(v) => setYear(v ?? year)} data={[0, 1, 2].map((i) => String(thisYear - i))} />
        <Text size="sm">with {data.previous_year}</Text>
      </Group>
      {data.incomplete_base && (
        <Alert color="orange" variant="light" p="xs">
          The imported reports start on {fmtDate(data.data_from)}, so {data.previous_year} revenue is incomplete and these ratios are overstated. Import older MarketZone reports (Detail .xlsx) to fix it.
        </Alert>
      )}
      {data.partial_year && (
        <Text size="xs" c="dimmed">
          {data.year} is not over: it counts what customers are already invoiced for this year. Quarterly-billed customers whose next instalment is not invoiced yet look smaller than they are.
        </Text>
      )}
      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <Stat label="Net revenue retention" value={data.nrr !== null ? `${data.nrr}%` : '—'} hint={`${usd(data.retained_revenue)} of ${usd(data.start_revenue)}`} />
        <Stat label="Gross revenue retention" value={data.grr !== null ? `${data.grr}%` : '—'} hint="without expansion" />
        <Stat label="Churned customers" value={mv.churned?.customers ?? 0} hint={usd(mv.churned?.before ?? 0)} tone={mv.churned?.customers ? 'red' : undefined} />
        <Stat label="New customers" value={data.new_customers} hint={usd(data.new_revenue)} />
      </SimpleGrid>
      <Group gap="xs">
        {data.movement.map((m) => (
          <Badge key={m.kind} variant="light" color={MOVE_COLOR[m.kind]} size="lg" tt="none">
            {m.kind}: {m.customers} · {usd(num(m.after) - num(m.before))}
          </Badge>
        ))}
      </Group>
      <Card withBorder>
        <Group justify="space-between" mb="xs">
          <Title order={5}>Where revenue is kept or lost</Title>
          <SegmentedControl size="xs" value={dim} onChange={setDim} data={[{ value: 'region', label: 'Region' }, { value: 'product', label: 'Product family' }, { value: 'reseller', label: 'Reseller' }]} />
        </Group>
        <DataTable
          rows={breakdown}
          initial="before"
          maxHeight={380}
          cols={[
            { key: 'name', label: dim === 'region' ? 'Region' : dim === 'product' ? 'Product family' : 'Reseller', render: (r) => r.name, sort: (r) => r.name },
            { key: 'before', label: String(data.previous_year), align: 'right', render: (r) => usd(r.before), sort: (r) => num(r.before) },
            { key: 'after', label: `Same customers, ${data.year}`, align: 'right', render: (r) => usd(r.after), sort: (r) => num(r.after) },
            { key: 'nrr', label: 'NRR', align: 'right', render: (r) => (r.nrr === null ? '—' : <Text size="sm" c={r.nrr < 90 ? 'red' : undefined} fw={r.nrr < 90 ? 600 : undefined}>{r.nrr}%</Text>), sort: (r) => r.nrr ?? 0 },
            { key: 'churned', label: 'Lost (churn)', align: 'right', render: (r) => usd(r.churned), sort: (r) => num(r.churned) },
          ]}
        />
      </Card>
      <Card withBorder>
        <Title order={5} mb="xs">
          Customers ({data.previous_year} → {data.year})
        </Title>
        <DataTable
          rows={data.customers}
          maxHeight={420}
          cols={[
            { key: 'account', label: 'Customer', render: (r) => <AccountLink id={r.account_id} name={r.account} />, sort: (r) => r.account },
            { key: 'status', label: 'Movement', render: (r) => <Badge size="sm" variant="light" color={MOVE_COLOR[r.status]}>{r.status}</Badge>, sort: (r) => r.status },
            { key: 'before', label: String(data.previous_year), align: 'right', render: (r) => usd(r.before), sort: (r) => num(r.before) },
            { key: 'after', label: String(data.year), align: 'right', render: (r) => usd(r.after), sort: (r) => num(r.after) },
            { key: 'change', label: 'Change', align: 'right', render: (r) => <Text size="sm" c={num(r.change) < 0 ? 'red' : 'teal'}>{usd(r.change)}</Text>, sort: (r) => num(r.change) },
            { key: 'region', label: 'Region', render: (r) => r.region, sort: (r) => r.region },
            { key: 'reseller', label: 'Via', render: (r) => <Text size="xs">{r.reseller}</Text>, sort: (r) => r.reseller },
          ]}
        />
      </Card>
    </Stack>
  )
}

// ---------------------------------------------------------------- resellers
interface Reseller {
  reseller: string
  revenue_12m: string
  revenue_prev_12m: string
  growth: number | null
  new: boolean
  active_customers: number
  invoices: number
  avg_invoice: string
  renewals_due: number
  renewed: number
  renewal_rate: number | null
  lapsed: number
  credits: string
  last_invoice: string | null
  quiet: boolean
}

function ResellersTab() {
  const { data } = useQuery({ queryKey: ['insights-resellers'], queryFn: () => api<Reseller[]>('/insights/resellers') })
  if (!data) return null
  const quiet = data.filter((r) => r.quiet && num(r.revenue_prev_12m) > 0)
  return (
    <Stack>
      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <Stat label="Resellers" value={data.filter((r) => r.reseller !== 'Direct (no reseller)').length} hint="billing companies in the reports" />
        <Stat label="Gone quiet" value={quiet.length} hint="no invoice in 6 months" tone={quiet.length ? 'orange' : undefined} />
        <Stat label="With lapsed licences" value={data.filter((r) => r.lapsed > 0).length} />
        <Stat
          label="Renewal rate (all)"
          value={(() => {
            const due = data.reduce((n, r) => n + r.renewals_due, 0)
            return due ? `${Math.round((100 * data.reduce((n, r) => n + r.renewed, 0)) / due)}%` : '—'
          })()}
          hint="paid periods ended in 12 months that were renewed"
        />
      </SimpleGrid>
      <Card withBorder>
        <DataTable
          rows={data}
          initial="rev"
          cols={[
            { key: 'name', label: 'Reseller', render: (r) => <Group gap={6} wrap="nowrap"><Text size="sm">{r.reseller}</Text>{r.quiet && <Badge size="xs" color="orange" variant="light">quiet</Badge>}</Group>, sort: (r) => r.reseller },
            { key: 'rev', label: 'Revenue 12 m', align: 'right', render: (r) => usd(r.revenue_12m), sort: (r) => num(r.revenue_12m) },
            { key: 'growth', label: 'vs prior 12 m', align: 'right', render: (r) => (r.new ? <Badge size="xs" variant="light">new</Badge> : r.growth === null ? '—' : <Text size="sm" c={r.growth < 0 ? 'red' : 'teal'}>{r.growth > 0 ? '+' : ''}{r.growth}%</Text>), sort: (r) => r.growth ?? -1e9 },
            { key: 'cust', label: 'Customers', align: 'right', render: (r) => r.active_customers, sort: (r) => r.active_customers },
            { key: 'avg', label: 'Avg invoice', align: 'right', render: (r) => usd(r.avg_invoice), sort: (r) => num(r.avg_invoice) },
            {
              key: 'renew',
              label: 'Renewal rate',
              align: 'right',
              render: (r) =>
                r.renewal_rate === null ? (
                  '—'
                ) : (
                  <Tooltip label={`${r.renewed} of ${r.renewals_due} renewed`}>
                    <Text size="sm" c={r.renewal_rate < 60 ? 'red' : undefined}>
                      {r.renewal_rate}%
                    </Text>
                  </Tooltip>
                ),
              sort: (r) => r.renewal_rate ?? -1,
            },
            { key: 'lapsed', label: 'Lapsed', align: 'right', render: (r) => (r.lapsed ? <Text size="sm" c="red">{r.lapsed}</Text> : 0), sort: (r) => r.lapsed },
            { key: 'credits', label: 'Credited', align: 'right', render: (r) => (num(r.credits) ? usd(r.credits) : '—'), sort: (r) => num(r.credits) },
            { key: 'last', label: 'Last invoice', render: (r) => fmtDate(r.last_invoice), sort: (r) => r.last_invoice ?? '' },
          ]}
        />
      </Card>
    </Stack>
  )
}

// ---------------------------------------------------------------- credits
interface Credits {
  quarters: { quarter: string; invoiced: string; credited: string; share: number | null }[]
  total_invoiced: string
  total_credited: string
  share: number | null
  by_customer: { account_id: number; account: string; region: string; credited: string; credit_lines: number }[]
  by_reseller: { reseller: string; credited: string }[]
  rebilled: { account_id: number; account: string; product: string; credit_lines: number; invoice_lines: number; credited: string }[]
  lines: { date: string; document: string | null; account_id: number; account: string; product: string; quantity: string; amount: string; reseller: string; report: string }[]
}

function CreditsTab() {
  const scheme = useComputedColorScheme('light') === 'dark' ? 'dark' : 'light'
  const [view, setView] = useState('customers')
  const { data } = useQuery({ queryKey: ['insights-credits'], queryFn: () => api<Credits>('/insights/credits') })
  if (!data) return null
  return (
    <Stack>
      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <Stat label="Credited" value={usd(data.total_credited)} hint={`${data.share ?? 0}% of ${usd(data.total_invoiced)} invoiced`} />
        <Stat label="Credit memo lines" value={data.lines.length} />
        <Stat label="Customers credited" value={data.by_customer.length} />
        <Stat label="Credited and re-billed" value={data.rebilled.length} hint="licences credited 2+ times" tone={data.rebilled.length ? 'orange' : undefined} />
      </SimpleGrid>
      <Card withBorder>
        <Title order={5}>Credited per quarter</Title>
        <Text size="xs" c="dimmed" mb="xs">
          Amount reversed by credit memos; hover a bar for its share of that quarter's invoicing
        </Text>
        <BarChart
          h={220}
          data={data.quarters.map((q) => ({ quarter: q.quarter, credited: num(q.credited), share: q.share }))}
          dataKey="quarter"
          series={[{ name: 'credited', label: 'Credited', color: SERIES[scheme] }]}
          valueFormatter={(v) => usd(v)}
          tickLine="none"
          gridAxis="y"
          barProps={{ radius: [4, 4, 0, 0] }}
          maxBarWidth={36}
          tooltipProps={{
            content: ({ payload }) => {
              const p = payload?.[0]?.payload as { quarter: string; credited: number; share: number | null } | undefined
              return p ? (
                <Card withBorder padding="xs" shadow="sm">
                  <Text size="sm" fw={600}>
                    {p.quarter}
                  </Text>
                  <Text size="sm">
                    {usd(p.credited)} credited · {p.share ?? 0}% of invoicing
                  </Text>
                </Card>
              ) : null
            },
          }}
        />
      </Card>
      <Card withBorder>
        <Group justify="space-between" mb="xs">
          <Title order={5}>Details</Title>
          <SegmentedControl
            size="xs"
            value={view}
            onChange={setView}
            data={[
              { value: 'customers', label: 'Customers' },
              { value: 'rebilled', label: 'Re-billed' },
              { value: 'resellers', label: 'Resellers' },
              { value: 'lines', label: 'All credit lines' },
            ]}
          />
        </Group>
        {view === 'customers' && (
          <DataTable rows={data.by_customer} initial="cr" cols={[
            { key: 'a', label: 'Customer', render: (r) => <AccountLink id={r.account_id} name={r.account} />, sort: (r) => r.account },
            { key: 'reg', label: 'Region', render: (r) => r.region, sort: (r) => r.region },
            { key: 'n', label: 'Credit lines', align: 'right', render: (r) => r.credit_lines, sort: (r) => r.credit_lines },
            { key: 'cr', label: 'Credited', align: 'right', render: (r) => usd(r.credited), sort: (r) => num(r.credited) },
          ]} />
        )}
        {view === 'rebilled' && (
          <DataTable rows={data.rebilled} empty="No licence was credited more than once." cols={[
            { key: 'a', label: 'Customer', render: (r) => <AccountLink id={r.account_id} name={r.account} />, sort: (r) => r.account },
            { key: 'p', label: 'Product', render: (r) => r.product, sort: (r) => r.product },
            { key: 'c', label: 'Credit lines', align: 'right', render: (r) => r.credit_lines, sort: (r) => r.credit_lines },
            { key: 'i', label: 'Invoice lines', align: 'right', render: (r) => r.invoice_lines, sort: (r) => r.invoice_lines },
            { key: 'cr', label: 'Credited', align: 'right', render: (r) => usd(r.credited), sort: (r) => num(r.credited) },
          ]} />
        )}
        {view === 'resellers' && (
          <DataTable rows={data.by_reseller} initial="cr" cols={[
            { key: 'r', label: 'Reseller', render: (r) => r.reseller, sort: (r) => r.reseller },
            { key: 'cr', label: 'Credited', align: 'right', render: (r) => usd(r.credited), sort: (r) => num(r.credited) },
          ]} />
        )}
        {view === 'lines' && (
          <DataTable rows={data.lines} cols={[
            { key: 'd', label: 'Date', render: (r) => fmtDate(r.date), sort: (r) => r.date },
            { key: 'doc', label: 'Document', render: (r) => <Text size="xs">{r.document}</Text>, sort: (r) => r.document ?? '' },
            { key: 'a', label: 'Customer', render: (r) => <AccountLink id={r.account_id} name={r.account} />, sort: (r) => r.account },
            { key: 'p', label: 'Product', render: (r) => <Text size="xs">{r.product}</Text>, sort: (r) => r.product },
            { key: 'q', label: 'Qty', align: 'right', render: (r) => num(r.quantity), sort: (r) => num(r.quantity) },
            { key: 'amt', label: 'Credited', align: 'right', render: (r) => usd(r.amount), sort: (r) => num(r.amount) },
            { key: 'rep', label: 'Report', render: (r) => <Text size="xs" c="dimmed">{r.report}</Text>, sort: (r) => r.report },
          ]} />
        )}
      </Card>
    </Stack>
  )
}

// ---------------------------------------------------------------- whitespace
interface Whitespace {
  families: { family: string; customers: number }[]
  rules: { has: string; suggest: string; confidence: number; support: number }[]
  suggestions: { account_id: number; account: string; region: string; owner: string | null; reseller: string; owns: string[]; suggest: { family: string; because: string; confidence: number }[] }[]
  matrix: { account_id: number; account: string; owns: string[] }[]
}

function WhitespaceTab() {
  const [conf, setConf] = useState('40')
  const [fam, setFam] = useState<string | null>(null)
  const { data } = useQuery({ queryKey: ['insights-whitespace', conf], queryFn: () => api<Whitespace>('/insights/whitespace', { params: { min_confidence: conf } }) })
  if (!data) return null
  const rows = fam ? data.suggestions.filter((s) => s.suggest.some((x) => x.family === fam)) : data.suggestions
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Products are grouped into families (TrueSight, BMC Helix and OnPrem versions together). A suggestion means: most customers who own family A also own B, and this customer has A but not B.
      </Text>
      <Group gap="xs">
        <Text size="sm">Suggest when at least</Text>
        <Select size="xs" w={80} allowDeselect={false} value={conf} onChange={(v) => setConf(v ?? '40')} data={['30', '40', '50', '60', '70']} />
        <Text size="sm">% of owners of A also own B · family</Text>
        <Select size="xs" w={280} clearable placeholder="All families" value={fam} onChange={setFam} data={data.families.map((f) => f.family)} />
      </Group>
      <SimpleGrid cols={{ base: 1, md: 3 }}>
        <Stat label="Customers with a suggestion" value={rows.length} />
        <Stat label="Suggestions" value={rows.reduce((n, s) => n + s.suggest.length, 0)} />
        <Stat label="Strongest pattern" value={data.rules[0] ? `${data.rules[0].confidence}%` : '—'} hint={data.rules[0] ? `${data.rules[0].has} → ${data.rules[0].suggest}` : undefined} />
      </SimpleGrid>
      <Card withBorder>
        <Title order={5} mb="xs">
          Cross-sell list
        </Title>
        <DataTable
          rows={rows}
          cols={[
            { key: 'a', label: 'Customer', render: (r) => <AccountLink id={r.account_id} name={r.account} />, sort: (r) => r.account },
            { key: 'owns', label: 'Owns', render: (r) => <Text size="xs">{r.owns.join(', ')}</Text> },
            {
              key: 's',
              label: 'Suggest',
              render: (r) => (
                <Group gap={4}>
                  {r.suggest.map((s) => (
                    <Tooltip key={s.family} label={`${s.confidence}% of ${s.because} customers also own it`}>
                      <Badge size="sm" variant="light" tt="none">
                        {s.family}
                      </Badge>
                    </Tooltip>
                  ))}
                </Group>
              ),
              sort: (r) => Math.max(...r.suggest.map((s) => s.confidence)),
            },
            { key: 'o', label: 'Owner', render: (r) => r.owner ?? <Text size="xs" c="dimmed">—</Text>, sort: (r) => r.owner ?? '' },
            { key: 'v', label: 'Via', render: (r) => <Text size="xs">{r.reseller}</Text>, sort: (r) => r.reseller },
          ]}
        />
      </Card>
      <Card withBorder>
        <Title order={5} mb="xs">
          Patterns
        </Title>
        <DataTable
          rows={data.rules}
          initial="c"
          maxHeight={300}
          cols={[
            { key: 'h', label: 'Customers who own', render: (r) => r.has, sort: (r) => r.has },
            { key: 's', label: 'also own', render: (r) => r.suggest, sort: (r) => r.suggest },
            { key: 'c', label: 'How often', align: 'right', render: (r) => `${r.confidence}%`, sort: (r) => r.confidence },
            { key: 'n', label: 'Customers', align: 'right', render: (r) => r.support, sort: (r) => r.support },
          ]}
        />
      </Card>
    </Stack>
  )
}

const TABS = [
  { value: 'renewals', label: 'Renewals at risk', el: <RenewalsTab /> },
  { value: 'retention', label: 'Retention', el: <RetentionTab /> },
  { value: 'resellers', label: 'Resellers', el: <ResellersTab /> },
  { value: 'credits', label: 'Credit memos', el: <CreditsTab /> },
  { value: 'whitespace', label: 'Cross-sell', el: <WhitespaceTab /> },
]

export default function Insights() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'renewals'
  return (
    <>
      <PageHeader title="Insights" subtitle="Licences from the BMC MarketZone reports: where to focus" />
      <Tabs value={tab} onChange={(v) => setParams(v ? { tab: v } : {}, { replace: true })} keepMounted={false}>
        <Tabs.List mb="md">
          {TABS.map((t) => (
            <Tabs.Tab key={t.value} value={t.value}>
              {t.label}
            </Tabs.Tab>
          ))}
        </Tabs.List>
        {TABS.map((t) => (
          <Tabs.Panel key={t.value} value={t.value}>
            {t.el}
          </Tabs.Panel>
        ))}
      </Tabs>
    </>
  )
}
