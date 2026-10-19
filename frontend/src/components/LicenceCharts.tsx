import { BarChart, DonutChart } from '@mantine/charts'
import { Alert, Box, Card, Grid, Group, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, Title, useComputedColorScheme } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { api } from '../api'
import { money } from '../labels'
import { LapsedLicencesCard } from './Licences'

interface Analytics {
  period: string
  granularity: 'year' | 'quarter'
  years: number[]
  quarters: string[]
  currency: string
  products: { product: string; customers: number; revenue: string }[]
  revenue_by_region: { name: string; amount: string }[]
  revenue_by_country: { name: string; amount: string }[]
  regions: string[]
  active_customers: ({ label: string; total: number } & Record<string, number>)[]
  invoiced_vs_fee: { year: number; invoiced: string; fee: string }[]
  lines_missing_fee: number
  fees_excluded: { report: string; invoice: string | null; date: string; product: string; invoiced: string; fee: string }[]
}

// Categorical palette, fixed order (validated light + dark, adjacent pairs). Identity follows the entity, never rank.
const SERIES = {
  light: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4'],
  dark: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181'],
}
const OTHER = { light: '#a3a29b', dark: '#6f6e68' } // neutral: "Other" is not a category of its own

const usePalette = () => {
  const scheme = useComputedColorScheme('light') === 'dark' ? 'dark' : 'light'
  return { series: SERIES[scheme], other: OTHER[scheme] }
}

const compact = (v: number) => (Math.abs(v) >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e3 ? `$${Math.round(v / 1e3)}k` : `$${Math.round(v)}`)
const pct = (v: number, total: number) => (total ? `${((100 * v) / total).toFixed(v / total < 0.1 ? 1 : 0)}%` : '—')

/** Top 5 + "Other": a pie stays readable at six slices or fewer. Colours follow the name, so a filter never repaints. */
function slices(rows: { name: string; value: number }[], palette: { series: string[]; other: string }) {
  const positive = rows.filter((r) => r.value > 0).sort((a, b) => b.value - a.value)
  const top = positive.slice(0, 5)
  const rest = positive.slice(5).reduce((n, r) => n + r.value, 0)
  const out = top.map((r, i) => ({ ...r, color: palette.series[i] }))
  if (rest > 0) out.push({ name: `Other (${positive.length - 5})`, value: rest, color: palette.other })
  return out
}

/** A chart card with a Chart / Table switch: the table is the accessible, exact view of the same numbers. */
function ChartCard({ title, subtitle, controls, chart, table }: { title: string; subtitle?: ReactNode; controls?: ReactNode; chart: ReactNode; table: ReactNode }) {
  const [view, setView] = useState('chart')
  return (
    <Card withBorder h="100%">
      <Group justify="space-between" align="flex-start" mb="xs" wrap="nowrap">
        <div>
          <Title order={5}>{title}</Title>
          {subtitle && (
            <Text size="xs" c="dimmed">
              {subtitle}
            </Text>
          )}
        </div>
        <Group gap="xs" wrap="nowrap">
          {controls}
          <SegmentedControl size="xs" value={view} onChange={setView} data={[{ value: 'chart', label: 'Chart' }, { value: 'table', label: 'Table' }]} />
        </Group>
      </Group>
      {view === 'chart' ? chart : table}
    </Card>
  )
}

/** Donut with a legend that carries name, value and share (direct labels for every slice). */
function Pie({ data, format, total, empty }: { data: { name: string; value: number; color: string }[]; format: (v: number) => string; total: number; empty: string }) {
  if (!data.length)
    return (
      <Text size="sm" c="dimmed">
        {empty}
      </Text>
    )
  return (
    <Group align="center" wrap="nowrap" gap="md">
      <DonutChart data={data} size={150} thickness={26} paddingAngle={2} strokeWidth={0} withTooltip tooltipDataSource="segment" valueFormatter={format} chartLabel={format(total)} />
      <Stack gap={4} style={{ minWidth: 0, flex: 1 }}>
        {data.map((d) => (
          <Group key={d.name} gap={6} wrap="nowrap" justify="space-between">
            <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
              <Box w={10} h={10} style={{ borderRadius: 2, background: d.color, flex: 'none' }} />
              <Text size="xs" truncate title={d.name}>
                {d.name}
              </Text>
            </Group>
            <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
              {format(d.value)} · {pct(d.value, total)}
            </Text>
          </Group>
        ))}
      </Stack>
    </Group>
  )
}

function SimpleTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <Table.ScrollContainer minWidth={300} mah={260}>
      <Table fz="xs" verticalSpacing={4} stickyHeader>
        <Table.Thead>
          <Table.Tr>
            {head.map((h, i) => (
              <Table.Th key={h} ta={i ? 'right' : undefined}>
                {h}
              </Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r, i) => (
            <Table.Tr key={i}>
              {r.map((c, j) => (
                <Table.Td key={j} ta={j ? 'right' : undefined}>
                  {c}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  )
}

/** Licence analytics from the BMC MarketZone reports (and licences added by hand). */
export function LicenceCharts() {
  const palette = usePalette()
  const [period, setPeriod] = useState('all')
  const [granularity, setGranularity] = useState<'year' | 'quarter'>('year')
  const [productBy, setProductBy] = useState('customers')
  const { data } = useQuery({
    queryKey: ['licence-analytics', period, granularity],
    queryFn: () => api<Analytics>('/dashboard/licences', { params: { period, granularity } }),
    placeholderData: (prev) => prev,
  })
  if (!data) return null
  if (!data.years.length && !data.products.length) return <LapsedLicencesCard />
  const usd = (v: number) => money(v, data.currency)
  const periodLabel = period === 'all' ? 'all imported reports' : period.replace('-', ' ')
  const periodOptions = [
    { value: 'all', label: 'All reports' },
    ...(granularity === 'year' ? data.years.map((y) => ({ value: String(y), label: String(y) })) : data.quarters.map((q) => ({ value: q, label: q.replace('-', ' ') }))),
  ]

  const productRows = data.products.map((p) => ({ name: p.product, value: productBy === 'customers' ? p.customers : Number(p.revenue) }))
  const productSlices = slices(productRows, palette)
  const productTotal = productRows.reduce((n, r) => n + Math.max(r.value, 0), 0)
  const regionColor = Object.fromEntries(data.regions.map((r, i) => [r, r === 'Other' ? palette.other : palette.series[i]]))
  const regionSlices = data.revenue_by_region.filter((r) => Number(r.amount) > 0).map((r) => ({ name: r.name, value: Number(r.amount), color: regionColor[r.name] ?? palette.other }))
  const regionTotal = regionSlices.reduce((n, r) => n + r.value, 0)
  const countrySlices = slices(data.revenue_by_country.map((c) => ({ name: c.name, value: Number(c.amount) })), palette)
  const countryTotal = countrySlices.reduce((n, r) => n + r.value, 0)
  const usedRegions = data.regions.filter((r) => data.active_customers.some((y) => y[r] > 0))
  const money4 = data.invoiced_vs_fee.map((y) => ({ year: String(y.year), invoiced: Number(y.invoiced), fee: Number(y.fee) }))

  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Title order={4}>Licences</Title>
        <Group gap="xs">
          <SegmentedControl
            size="xs"
            value={granularity}
            onChange={(v) => {
              setGranularity(v as 'year' | 'quarter')
              setPeriod('all')
            }}
            data={[
              { value: 'year', label: 'Calendar year' },
              { value: 'quarter', label: 'Quarter' },
            ]}
          />
          <Select size="xs" w={140} allowDeselect={false} value={period} onChange={(v) => setPeriod(v ?? 'all')} data={periodOptions} aria-label="Period" />
        </Group>
      </Group>
      <LapsedLicencesCard />
      <Grid>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <ChartCard
            title="Products"
            subtitle={productBy === 'customers' ? (period === 'all' ? 'Customers holding each product now' : `Customers with a paid licence in ${periodLabel}`) : `Invoiced, ${periodLabel}`}
            controls={
              <SegmentedControl
                size="xs"
                value={productBy}
                onChange={setProductBy}
                data={[
                  { value: 'customers', label: 'Customers' },
                  { value: 'revenue', label: 'Revenue' },
                ]}
              />
            }
            chart={<Pie data={productSlices} total={productTotal} format={productBy === 'customers' ? (v) => String(v) : compact} empty="No licences yet." />}
            table={<SimpleTable head={['Product', 'Customers', 'Invoiced']} rows={data.products.map((p) => [p.product, p.customers, usd(Number(p.revenue))])} />}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <ChartCard
            title="Revenue by region and country"
            subtitle={`Share of invoiced amount, ${periodLabel}`}
            chart={
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
                <Pie data={regionSlices} total={regionTotal} format={compact} empty="No revenue in this period." />
                <Pie data={countrySlices} total={countryTotal} format={compact} empty="No revenue in this period." />
              </SimpleGrid>
            }
            table={
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <SimpleTable head={['Region', 'Invoiced', 'Share']} rows={data.revenue_by_region.map((r) => [r.name, usd(Number(r.amount)), pct(Number(r.amount), regionTotal)])} />
                <SimpleTable head={['Country', 'Invoiced', 'Share']} rows={data.revenue_by_country.map((r) => [r.name, usd(Number(r.amount)), pct(Number(r.amount), countryTotal)])} />
              </SimpleGrid>
            }
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <ChartCard
            title="Active customers"
            subtitle={`Customers with a paid licence during each ${granularity === 'year' ? 'calendar year' : 'quarter'}, by region`}
            chart={
              <BarChart
                h={240}
                data={data.active_customers}
                dataKey="label"
                type="stacked"
                series={usedRegions.map((r) => ({ name: r, color: regionColor[r] }))}
                withLegend
                legendProps={{ verticalAlign: 'bottom' }}
                tickLine="none"
                gridAxis="y"
                barProps={{ radius: 0, stroke: 'var(--mantine-color-body)', strokeWidth: 2 }}
                maxBarWidth={56}
                tooltipAnimationDuration={150}
              />
            }
            table={<SimpleTable head={[granularity === 'year' ? 'Year' : 'Quarter', ...usedRegions, 'Total']} rows={data.active_customers.map((y) => [y.label, ...usedRegions.map((r) => y[r]), y.total])} />}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <ChartCard
            title="Invoiced and paid to Sentry"
            subtitle="By invoice year: amount BMC invoiced customers (net) and the fee due to Sentry"
            chart={
              <Stack gap={6}>
                <BarChart
                  h={240}
                  data={money4}
                  dataKey="year"
                  series={[
                    { name: 'invoiced', label: 'Invoiced (net)', color: palette.series[0] },
                    { name: 'fee', label: 'Paid to Sentry (fee)', color: palette.series[1] },
                  ]}
                  withLegend
                  legendProps={{ verticalAlign: 'bottom' }}
                  valueFormatter={compact}
                  tickLine="none"
                  gridAxis="y"
                  barProps={{ radius: [4, 4, 0, 0] }}
                  maxBarWidth={40}
                />
                {data.fees_excluded.length > 0 && (
                  <Alert color="orange" variant="light" p="xs" title={`${data.fees_excluded.length} report lines left out of "Paid to Sentry"`}>
                    <Text size="xs" mb={4}>
                      Their fee is larger than the amount invoiced, which cannot be right (it looks like fee = amount × quantity). Ask BMC for a corrected report:
                    </Text>
                    <Text size="xs" c="dimmed">
                      {data.fees_excluded
                        .slice(0, 6)
                        .map((x) => `${x.report} · ${x.invoice} · invoiced ${usd(Number(x.invoiced))}, fee ${usd(Number(x.fee))}`)
                        .join(' — ')}
                      {data.fees_excluded.length > 6 ? ` — and ${data.fees_excluded.length - 6} more` : ''}
                    </Text>
                  </Alert>
                )}
                {data.lines_missing_fee > 0 && (
                  <Alert color="yellow" variant="light" p="xs">
                    <Text size="xs">
                      {data.lines_missing_fee} report lines were imported before fees were stored. Import those reports again (Import / export → BMC MarketZone report) to fill them in; nothing else changes.
                    </Text>
                  </Alert>
                )}
              </Stack>
            }
            table={<SimpleTable head={['Year', 'Invoiced (net)', 'Paid to Sentry', 'Fee share']} rows={money4.map((y) => [y.year, usd(y.invoiced), usd(y.fee), pct(y.fee, y.invoiced)])} />}
          />
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
