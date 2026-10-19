import { Anchor, Box, Card, Grid, Group, Select, SimpleGrid, Stack, Table, Text, Title, Tooltip } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { PageHeader } from '../components/common'
import { LicenceCharts } from '../components/LicenceCharts'
import { useBrands } from '../hooks'
import { fmtDate, money } from '../labels'

interface Row {
  currency: string
  count: number
  amount: string
}
interface Summary {
  open_count: number
  pipeline: { currency: string; total: string; weighted: string; count: number }[]
  won_this_quarter: Row[]
  win_rate_12m: number
  new_leads_30d: number
  by_stage: (Row & { stage: string })[]
  by_platform: (Row & { platform: string })[]
  by_brand: (Row & { brand: string })[]
  closing_soon: { id: number; title: string; amount: string; currency: string; expected_close_date: string; stage: string }[]
  my_tasks: { id: number; subject: string; due_at: string | null; contact_id: number | null; account_id: number | null; opportunity_id: number | null }[]
}

function Stat({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <Card withBorder>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text fw={700} size="xl" mt={4} component="div">
        {children}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      )}
    </Card>
  )
}

const multi = (rows: { currency: string; amount?: string; total?: string }[], field: 'amount' | 'total' = 'amount') =>
  rows.length ? rows.map((r) => money(r[field], r.currency)).join(' + ') : money(0)

/** Single-hue horizontal bars: magnitude only, value labels in text ink, hover shows exact figures. */
function BarList({ rows }: { rows: { label: string; amount: number; currency: string; count: number }[] }) {
  const max = Math.max(...rows.map((r) => r.amount), 1)
  if (!rows.length)
    return (
      <Text size="sm" c="dimmed">
        No open opportunities yet.
      </Text>
    )
  return (
    <Stack gap={8}>
      {rows.map((r) => (
        <Tooltip key={`${r.label}-${r.currency}`} label={`${r.label}: ${money(r.amount, r.currency)} · ${r.count} deal${r.count === 1 ? '' : 's'}`} position="top-start">
          <Box>
            <Group justify="space-between" gap="xs" mb={2} wrap="nowrap">
              <Text size="sm" truncate>
                {r.label}
              </Text>
              <Text size="sm" fw={600} style={{ whiteSpace: 'nowrap' }}>
                {money(r.amount, r.currency)}
              </Text>
            </Group>
            <Box h={8} bg="var(--mantine-color-default-hover)" style={{ borderRadius: 4 }}>
              <Box h={8} w={`${Math.max((r.amount / max) * 100, 1)}%`} bg="violet.6" style={{ borderRadius: 4 }} />
            </Box>
          </Box>
        </Tooltip>
      ))}
    </Stack>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const { data: brands } = useBrands()
  const [brandId, setBrandId] = useState<string | null>(null)
  const { data: s } = useQuery({
    queryKey: ['dashboard', brandId],
    queryFn: () => api<Summary>('/dashboard', { params: { brand_id: brandId ?? undefined } }),
  })

  return (
    <>
      <PageHeader
        title={`Hello ${user?.full_name.split(' ')[0] ?? ''}`}
        subtitle="Pipeline overview"
        actions={<Select placeholder="All brands" data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))} value={brandId} onChange={setBrandId} clearable w={200} />}
      />
      {s && (
        <Stack>
          <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }}>
            <Stat label="Open pipeline" hint={`${s.open_count} open opportunities`}>
              {multi(s.pipeline, 'total')}
            </Stat>
            <Stat label="Weighted pipeline" hint="Value × stage probability">
              {s.pipeline.length ? s.pipeline.map((p) => money(p.weighted, p.currency)).join(' + ') : money(0)}
            </Stat>
            <Stat label="Won this quarter" hint={`${s.won_this_quarter.reduce((a, r) => a + r.count, 0)} deals`}>
              {multi(s.won_this_quarter)}
            </Stat>
            <Stat label="Win rate (12 months)" hint={`${s.new_leads_30d} new leads in 30 days`}>
              {s.win_rate_12m}%
            </Stat>
          </SimpleGrid>
          <Grid>
            <Grid.Col span={{ base: 12, md: 6 }}>
              <Card withBorder h="100%">
                <Title order={5} mb="sm">
                  Open pipeline by stage
                </Title>
                <BarList rows={s.by_stage.map((r) => ({ label: r.stage, amount: Number(r.amount), currency: r.currency, count: r.count }))} />
              </Card>
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 6 }}>
              <Card withBorder h="100%">
                <Title order={5} mb="sm">
                  Open pipeline by referring platform
                </Title>
                <BarList rows={s.by_platform.map((r) => ({ label: r.platform, amount: Number(r.amount), currency: r.currency, count: r.count }))} />
              </Card>
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 7 }}>
              <Card withBorder h="100%">
                <Title order={5} mb="sm">
                  Closing in the next 30 days
                </Title>
                {s.closing_soon.length ? (
                  <Table>
                    <Table.Tbody>
                      {s.closing_soon.map((o) => (
                        <Table.Tr key={o.id}>
                          <Table.Td>
                            <Anchor component={Link} to={`/opportunities/${o.id}`} size="sm">
                              {o.title}
                            </Anchor>
                          </Table.Td>
                          <Table.Td>{o.stage}</Table.Td>
                          <Table.Td ta="right">{money(o.amount, o.currency)}</Table.Td>
                          <Table.Td>{fmtDate(o.expected_close_date)}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                ) : (
                  <Text size="sm" c="dimmed">
                    Nothing due to close in the next 30 days.
                  </Text>
                )}
              </Card>
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 5 }}>
              <Card withBorder h="100%">
                <Title order={5} mb="sm">
                  My open tasks
                </Title>
                {s.my_tasks.length ? (
                  <Stack gap={6}>
                    {s.my_tasks.map((t) => {
                      const to = t.opportunity_id ? `/opportunities/${t.opportunity_id}` : t.contact_id ? `/contacts/${t.contact_id}` : `/accounts/${t.account_id}`
                      const overdue = t.due_at && new Date(t.due_at) < new Date()
                      return (
                        <Group key={t.id} justify="space-between" wrap="nowrap">
                          <Anchor component={Link} to={to} size="sm" truncate>
                            {t.subject}
                          </Anchor>
                          <Text size="xs" c={overdue ? 'red' : 'dimmed'} style={{ whiteSpace: 'nowrap' }}>
                            {t.due_at ? fmtDate(t.due_at) : 'no date'}
                          </Text>
                        </Group>
                      )
                    })}
                  </Stack>
                ) : (
                  <Text size="sm" c="dimmed">
                    You're all caught up.
                  </Text>
                )}
              </Card>
            </Grid.Col>
          </Grid>
          <LicenceCharts />
        </Stack>
      )}
    </>
  )
}
