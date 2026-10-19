import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Collapse,
  Group,
  Indicator,
  List,
  Menu,
  Modal,
  NumberInput,
  Select,
  SimpleGrid,
  Space,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
  Tooltip,
  UnstyledButton,
} from '@mantine/core'
import { Dropzone } from '@mantine/dropzone'
import { IconBell, IconCheck, IconChevronRight, IconFileUpload, IconPlus, IconTrash } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { useApiMutation } from '../hooks'
import { fmtDate } from '../labels'

export interface Holding {
  account_id: number
  account_name: string
  product_name: string
  license_type: string
  quantity: string
  period_start: string | null
  period_end: string | null
  renewal_date: string | null
  status: 'active' | 'renewal_due' | 'awaiting_report' | 'lapsed' | 'upcoming' | 'perpetual' | 'cancelled'
  installments: boolean
  days_to_renewal: number | null
  reseller: string | null
  latest_line_id: number
  resolved: boolean
  resolution: string | null
  resolved_by: string | null
  resolved_at: string | null
}

interface Line {
  id: number
  product_name: string
  quantity: string
  license_type: string
  start_date: string | null
  end_date: string | null
  net_amount: string | null
  currency: string
  source: string
  source_ref: string | null
  report_name: string | null
}

export const LICENCE_STATUS: Record<Holding['status'], { label: string; color: string }> = {
  active: { label: 'Active', color: 'green' },
  renewal_due: { label: 'Renewal due', color: 'orange' },
  awaiting_report: { label: 'Ended · awaiting next report', color: 'yellow' },
  lapsed: { label: 'Lapsed', color: 'red' },
  upcoming: { label: 'Starts later', color: 'blue' },
  perpetual: { label: 'Perpetual', color: 'teal' },
  cancelled: { label: 'Credited', color: 'gray' },
}

const TYPES: Record<string, string> = { term: 'Term', support: 'Support', saas: 'SaaS', perpetual: 'Perpetual', other: 'Other' }

const qty = (v: string) => Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 })

export function StatusBadge({ h }: { h: Pick<Holding, 'status' | 'days_to_renewal' | 'resolved'> }) {
  const s = LICENCE_STATUS[h.status]
  const label =
    h.status === 'renewal_due' && h.days_to_renewal !== null
      ? `Renews in ${h.days_to_renewal} d`
      : h.status === 'lapsed' && h.resolved
        ? 'Lapsed · resolved'
        : s.label
  return (
    <Badge color={h.status === 'lapsed' && h.resolved ? 'gray' : s.color} variant="light">
      {label}
    </Badge>
  )
}

/** Licences tab on the account page: what the customer owns and when it renews. */
export function AccountLicences({ accountId }: { accountId: number }) {
  const { canWrite, isAdmin } = useAuth()
  const key = ['licences', accountId]
  const { data } = useQuery({ queryKey: key, queryFn: () => api<{ holdings: Holding[]; lines: Line[] }>(`/accounts/${accountId}/licences`) })
  const [showLines, setShowLines] = useState(false)
  const [adding, setAdding] = useState(false)
  const [resolving, setResolving] = useState<Holding | null>(null)
  const [form, setForm] = useState({ product_name: '', quantity: 1 as number | string, license_type: 'term', start_date: '', end_date: '' })
  const add = useApiMutation(
    () =>
      api(`/accounts/${accountId}/licences`, {
        method: 'POST',
        body: { ...form, quantity: Number(form.quantity), start_date: form.start_date || null, end_date: form.end_date || null },
      }),
    { invalidate: [key, ['licences-lapsed']], success: 'Licence added', onSuccess: () => setAdding(false) },
  )
  const remove = useApiMutation((id: number) => api(`/licences/${id}`, { method: 'DELETE' }), { invalidate: [key, ['licences-lapsed']] })
  const reopen = useApiMutation((id: number) => api(`/licences/${id}/reopen`, { method: 'POST' }), { invalidate: [key, ['licences-lapsed']] })

  const holdings = data?.holdings.filter((h) => h.status !== 'cancelled') ?? []
  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          From the quarterly BMC MarketZone reports and licences added by hand. Quantities are for the current period. A report licence that ended after the last imported report shows as awaiting the next report; it lapses if that report has no renewal.
        </Text>
        {canWrite && (
          <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setAdding(true)}>
            Add licence
          </Button>
        )}
      </Group>
      {holdings.length ? (
        <Table.ScrollContainer minWidth={680}>
          <Table verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Product</Table.Th>
                <Table.Th ta="right">Quantity</Table.Th>
                <Table.Th>Type</Table.Th>
                <Table.Th>Renewal / paid until</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Via</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {holdings.map((h) => (
                <Table.Tr key={h.product_name}>
                  <Table.Td fw={500}>{h.product_name}</Table.Td>
                  <Table.Td ta="right">{qty(h.quantity)}</Table.Td>
                  <Table.Td>{TYPES[h.license_type] ?? h.license_type}</Table.Td>
                  <Table.Td c={h.status === 'lapsed' ? 'red' : undefined} style={{ whiteSpace: 'nowrap' }}>
                    {fmtDate(h.renewal_date)}
                    {h.installments && (
                      <Text size="xs" c="dimmed">
                        billed in instalments
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} wrap="nowrap">
                      <Tooltip disabled={!h.resolved} label={`${h.resolution} (${h.resolved_by}, ${fmtDate(h.resolved_at)})`} multiline w={260}>
                        <span>
                          <StatusBadge h={h} />
                        </span>
                      </Tooltip>
                      {canWrite && h.status === 'lapsed' && !h.resolved && (
                        <Button size="compact-xs" variant="subtle" onClick={() => setResolving(h)}>
                          Resolve
                        </Button>
                      )}
                      {canWrite && h.status === 'lapsed' && h.resolved && (
                        <Button size="compact-xs" variant="subtle" color="gray" onClick={() => reopen.mutate(h.latest_line_id)}>
                          Reopen
                        </Button>
                      )}
                    </Group>
                  </Table.Td>
                  <Table.Td>{h.reseller}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      ) : (
        <Text size="sm" c="dimmed">
          No licences recorded for this account.
        </Text>
      )}
      {!!data?.lines.length && (
        <Anchor size="xs" onClick={() => setShowLines((v) => !v)}>
          {showLines ? 'Hide' : 'Show'} the {data.lines.length} report line{data.lines.length === 1 ? '' : 's'}
        </Anchor>
      )}
      {showLines && data && (
        <Table.ScrollContainer minWidth={680}>
          <Table fz="xs" verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Product</Table.Th>
                <Table.Th ta="right">Qty</Table.Th>
                <Table.Th>Period</Table.Th>
                <Table.Th ta="right">Net</Table.Th>
                <Table.Th>Source</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.lines.map((l) => (
                <Table.Tr key={l.id}>
                  <Table.Td>{l.product_name}</Table.Td>
                  <Table.Td ta="right">{qty(l.quantity)}</Table.Td>
                  <Table.Td style={{ whiteSpace: 'nowrap' }}>
                    {l.end_date ? `${fmtDate(l.start_date)} – ${fmtDate(l.end_date)}` : fmtDate(l.start_date)}
                  </Table.Td>
                  <Table.Td ta="right">{l.net_amount !== null ? `${Number(l.net_amount).toLocaleString('en-US', { minimumFractionDigits: 2 })} ${l.currency}` : '—'}</Table.Td>
                  <Table.Td>{l.source === 'bmc_mzd' ? `${l.source_ref} · ${l.report_name}` : 'Added by hand'}</Table.Td>
                  <Table.Td>
                    {isAdmin && (
                      <ActionIcon size="sm" variant="subtle" color="red" aria-label="Delete line" onClick={() => remove.mutate(l.id)}>
                        <IconTrash size={14} />
                      </ActionIcon>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      <Modal opened={adding} onClose={() => setAdding(false)} title="Add licence">
        <Stack>
          <TextInput label="Product" required value={form.product_name} onChange={(e) => setForm({ ...form, product_name: e.target.value })} />
          <SimpleGrid cols={2}>
            <NumberInput label="Quantity" required value={form.quantity} onChange={(v) => setForm({ ...form, quantity: v })} />
            <Select label="Type" data={Object.entries(TYPES).map(([value, label]) => ({ value, label }))} value={form.license_type} onChange={(v) => setForm({ ...form, license_type: v ?? 'term' })} allowDeselect={false} />
            <TextInput label="Start" type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
            <TextInput
              label="End / renewal date"
              type="date"
              required={form.license_type !== 'perpetual'}
              description={form.license_type === 'perpetual' ? 'Not needed for a perpetual licence' : undefined}
              value={form.end_date}
              onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            />
          </SimpleGrid>
          <Group justify="flex-end">
            <Button loading={add.isPending} disabled={!form.product_name || (!form.end_date && form.license_type !== 'perpetual')} onClick={() => add.mutate(undefined)}>
              Add
            </Button>
          </Group>
        </Stack>
      </Modal>
      <ResolveModal holding={resolving} onClose={() => setResolving(null)} />
    </Stack>
  )
}

function ResolveModal({ holding, onClose }: { holding: Holding | null; onClose: () => void }) {
  const [note, setNote] = useState('')
  const resolve = useApiMutation(() => api(`/licences/${holding!.latest_line_id}/resolve`, { method: 'POST', body: { note } }), {
    invalidate: [['licences-lapsed'], ['licences', holding?.account_id]],
    success: 'Marked as resolved',
    onSuccess: () => {
      setNote('')
      onClose()
    },
  })
  return (
    <Modal opened={!!holding} onClose={onClose} title="Resolve lapsed licence">
      {holding && (
        <Stack>
          <Text size="sm">
            <b>{holding.account_name}</b> · {holding.product_name} ({qty(holding.quantity)}), ended {fmtDate(holding.renewal_date)}.
          </Text>
          <Textarea
            label="What happened?"
            description="e.g. renewed outside MarketZone, moved to SaaS, churned"
            autosize
            minRows={2}
            required
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <Group justify="flex-end">
            <Button leftSection={<IconCheck size={16} />} disabled={!note.trim()} loading={resolve.isPending} onClick={() => resolve.mutate(undefined)}>
              Mark resolved
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  )
}

/** Dashboard card: lapsed licences stay here until someone marks them resolved. */
export function LapsedLicencesCard() {
  const { canWrite } = useAuth()
  const { data } = useQuery({ queryKey: ['licences-lapsed'], queryFn: () => api<Holding[]>('/licences/lapsed') })
  const [resolving, setResolving] = useState<Holding | null>(null)
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem('crm.dashboard.lapsedOpen') === '1'
    } catch {
      return false
    }
  })
  const toggle = () => {
    setOpen(!open)
    try {
      localStorage.setItem('crm.dashboard.lapsedOpen', open ? '0' : '1')
    } catch {
      /* storage unavailable: the card still works */
    }
  }
  if (!data) return null
  return (
    <Card withBorder>
      <UnstyledButton onClick={toggle} w="100%" aria-expanded={open} aria-controls="lapsed-licences">
        <Group justify="space-between">
          <Group gap="xs">
            <IconChevronRight size={18} style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 150ms' }} />
            <Title order={5}>Lapsed licences</Title>
          </Group>
          {data.length > 0 ? (
            <Badge color="red" variant="light">
              {data.length} to follow up
            </Badge>
          ) : (
            <Text size="xs" c="dimmed">
              none
            </Text>
          )}
        </Group>
      </UnstyledButton>
      <Collapse in={open} id="lapsed-licences">
      <Space h="sm" />
      {data.length ? (
        <Table.ScrollContainer minWidth={560}>
          <Table verticalSpacing={6}>
            <Table.Tbody>
              {data.map((h) => (
                <Table.Tr key={`${h.account_id}-${h.product_name}`}>
                  <Table.Td>
                    <Anchor component={Link} to={`/accounts/${h.account_id}?tab=licences`} size="sm" fw={600}>
                      {h.account_name}
                    </Anchor>
                    <Text size="xs" c="dimmed">
                      {h.product_name} · {qty(h.quantity)}
                      {h.reseller ? ` · via ${h.reseller}` : ''}
                    </Text>
                  </Table.Td>
                  <Table.Td style={{ whiteSpace: 'nowrap' }}>
                    <Text size="sm" c="red">
                      Ended {fmtDate(h.renewal_date)}
                    </Text>
                  </Table.Td>
                  <Table.Td ta="right">
                    {canWrite && (
                      <Button size="compact-sm" variant="light" onClick={() => setResolving(h)}>
                        Resolve
                      </Button>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      ) : (
        <Text size="sm" c="dimmed">
          No lapsed licences. Licences whose renewal date has passed show here until they are renewed or marked resolved.
        </Text>
      )}
      </Collapse>
      <ResolveModal holding={resolving} onClose={() => setResolving(null)} />
    </Card>
  )
}

interface ImportResult {
  dry_run: boolean
  source: 'pdf' | 'xlsx'
  reliable: boolean
  report: string
  lines: number
  created: number
  already_imported: number
  fees_filled: number
  countries_filled: number
  accounts_matched: Record<string, string>
  accounts_created: string[]
  resellers: Record<string, string>
  totals_checked: number
  warnings: string[]
  preview: { customer: string; account: string; product: string; type: string; quantity: string; start: string; end: string; reseller: string | null; document: string }[]
}

/** Admin card on Import / export: load a quarterly BMC MarketZone report. */
export function MzdImport() {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const run = useApiMutation(
    (commit: boolean) => {
      const form = new FormData()
      form.append('file', file!)
      form.append('commit', String(commit))
      return api<ImportResult>('/licences/import/bmc-mzd', { method: 'POST', form })
    },
    { invalidate: [['licences-lapsed'], ['accounts'], ['licences']], onSuccess: setResult },
  )
  return (
    <Card withBorder mb="md">
      <Title order={5}>BMC MarketZone report (licences)</Title>
      <Text size="sm" c="dimmed" mb="sm">
        Load the quarterly “Reseller Fee Report to Sentry Software”: the Detail .xlsx (exact, preferred) or the PDF. Each line becomes a licence on the customer's account (quantity, period, renewal date). Loading the same report twice changes nothing, so the PDF and .xlsx of one quarter can both be loaded.
      </Text>
      <Dropzone
        onDrop={(f) => {
          setFile(f[0])
          setResult(null)
        }}
        accept={['application/pdf', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']}
        maxFiles={1}
        maxSize={20_000_000}
      >
        <Group justify="center" gap="xs" mih={60} style={{ pointerEvents: 'none' }}>
          <IconFileUpload size={28} stroke={1.5} />
          <Text size="sm">{file ? file.name : 'Drop the report (.xlsx or .pdf) here or click to choose'}</Text>
        </Group>
      </Dropzone>
      <Group mt="sm">
        <Button variant="default" disabled={!file} loading={run.isPending && !run.variables} onClick={() => run.mutate(false)}>
          Dry run
        </Button>
        <Button disabled={!file || !result?.dry_run || !result.reliable || (result.created === 0 && !result.fees_filled && !result.countries_filled)} loading={run.isPending && !!run.variables} onClick={() => run.mutate(true)}>
          Import licences
        </Button>
      </Group>
      {result && (
        <Stack gap="xs" mt="md">
          <Alert
            color={!result.reliable ? 'red' : result.dry_run ? 'blue' : 'green'}
            variant="light"
            title={!result.reliable ? 'This report cannot be imported' : result.dry_run ? 'Dry run: nothing saved yet' : 'Imported'}
          >
            {!result.reliable && (
              <Text size="sm" mb={4}>
                Some lines could not be read reliably (listed below), so nothing will be saved.{' '}
                {result.source === 'pdf' ? 'Load the Detail .xlsx of the same quarter instead.' : 'Check the file with BMC.'}
              </Text>
            )}
            {result.lines} lines read ({result.totals_checked} report totals cross-checked) · {result.created} new · {result.already_imported} already imported
            {result.fees_filled > 0 && ` · Sentry fee ${result.dry_run ? 'to fill in' : 'filled in'} on ${result.fees_filled} existing lines`}
            {result.countries_filled > 0 && ` · country ${result.dry_run ? 'to fill in' : 'filled in'} on ${result.countries_filled} existing lines`}
          </Alert>
          {result.warnings.length > 0 && (
            <Alert color="orange" variant="light" title={result.reliable ? 'Notes' : 'Problems'}>
              <List size="xs">
                {result.warnings.map((w) => (
                  <List.Item key={w}>{w}</List.Item>
                ))}
              </List>
            </Alert>
          )}
          {result.accounts_created.length > 0 && (
            <Text size="sm">
              <b>New customer accounts ({result.accounts_created.length}):</b> {result.accounts_created.join(', ')}
            </Text>
          )}
          {Object.keys(result.accounts_matched).length > 0 && (
            <Text size="sm">
              <b>Matched to existing accounts:</b>{' '}
              {Object.entries(result.accounts_matched)
                .map(([a, b]) => `${a} → ${b}`)
                .join(', ')}
            </Text>
          )}
          {Object.keys(result.resellers).length > 0 && (
            <Text size="sm">
              <b>Resellers:</b> {Object.values(result.resellers).join(', ')}
            </Text>
          )}
          {result.preview.length > 0 && (
            <Table.ScrollContainer minWidth={720} mah={320}>
              <Table fz="xs" verticalSpacing={2} stickyHeader>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Customer</Table.Th>
                    <Table.Th>Product</Table.Th>
                    <Table.Th ta="right">Qty</Table.Th>
                    <Table.Th>Period</Table.Th>
                    <Table.Th>Reseller</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {result.preview.map((p, i) => (
                    <Table.Tr key={i}>
                      <Table.Td>{p.account}</Table.Td>
                      <Table.Td>{p.product}</Table.Td>
                      <Table.Td ta="right">{qty(p.quantity)}</Table.Td>
                      <Table.Td style={{ whiteSpace: 'nowrap' }}>
                        {fmtDate(p.start)} – {fmtDate(p.end)}
                      </Table.Td>
                      <Table.Td>{p.reseller}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </Stack>
      )}
    </Card>
  )
}

interface NotificationRow {
  id: number
  title: string
  body: string | null
  link: string | null
  read_at: string | null
  created_at: string
}

/** Header bell: renewal notices and other alerts for the signed-in user. */
export function NotificationsBell() {
  const nav = useNavigate()
  const { data } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => api<{ unread: number; items: NotificationRow[] }>('/notifications'),
    refetchInterval: 300_000,
  })
  const read = useApiMutation((ids: number[] | null) => api('/notifications/read', { method: 'POST', body: ids }), {
    invalidate: [['notifications']],
  })
  return (
    <Menu position="bottom-end" width={360} shadow="md">
      <Menu.Target>
        <Indicator label={data?.unread} size={16} disabled={!data?.unread} color="red" offset={4}>
          <ActionIcon variant="subtle" aria-label="Notifications">
            <IconBell size={18} />
          </ActionIcon>
        </Indicator>
      </Menu.Target>
      <Menu.Dropdown>
        <Group justify="space-between" px="sm" py={4}>
          <Text size="sm" fw={600}>
            Notifications
          </Text>
          {!!data?.unread && (
            <Anchor size="xs" onClick={() => read.mutate(null)}>
              Mark all read
            </Anchor>
          )}
        </Group>
        <Menu.Divider />
        {data?.items.length ? (
          data.items.slice(0, 12).map((n) => (
            <UnstyledButton
              key={n.id}
              w="100%"
              px="sm"
              py={6}
              style={{ display: 'block', opacity: n.read_at ? 0.6 : 1 }}
              onClick={() => {
                if (!n.read_at) read.mutate([n.id])
                if (n.link) nav(n.link.startsWith('/accounts/') ? `${n.link}?tab=licences` : n.link)
              }}
            >
              <Text size="sm" fw={n.read_at ? 400 : 600} lineClamp={1}>
                {n.title}
              </Text>
              {n.body && (
                <Text size="xs" c="dimmed" lineClamp={3} style={{ whiteSpace: 'pre-line' }}>
                  {n.body}
                </Text>
              )}
              <Text size="xs" c="dimmed">
                {fmtDate(n.created_at)}
              </Text>
            </UnstyledButton>
          ))
        ) : (
          <Text size="sm" c="dimmed" px="sm" py="xs">
            Nothing new.
          </Text>
        )}
      </Menu.Dropdown>
    </Menu>
  )
}
