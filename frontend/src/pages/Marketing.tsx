import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  Modal,
  MultiSelect,
  NumberInput,
  ScrollArea,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  TagsInput,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { modals } from '@mantine/modals'
import { IconAddressBook, IconListDetails, IconMail, IconPlus, IconTrash, IconUsersGroup } from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { PageHeader, Pager, UserPicker } from '../components/common'
import { Stat } from '../components/ui'
import { useApiMutation, useBrands } from '../hooks'
import { ACCOUNT_TYPES, CONTACT_ROLES, fmtDate, LEAD_SOURCES, LIFECYCLES, toOptions } from '../labels'
import { useLists } from './MailingLists'

/** Every rule given must match; several values in one rule mean any of them. Mirrors backend audiences.py. */
export interface AudienceRules {
  lifecycle?: string[]
  role?: string[]
  account_type?: string[]
  country?: string[]
  source?: string[]
  brand_id?: number | null
  owner_id?: number | null
  consent_only?: boolean
  licence?: 'active' | 'lapsed' | 'none' | null
  product?: string | null
  renews_within_days?: number | null
  list_ids?: number[]
  created_within_days?: number | null
}

interface Counts {
  matching: number
  reachable: number
  with_consent: number
}

export interface Audience {
  id: number
  name: string
  description: string | null
  brand_id: number | null
  rules: AudienceRules
  created_at: string
  updated_at: string
  counts: Counts | null
}

interface Overview {
  days: number
  contacts: { with_email: number; reachable: number; with_consent: number; unsubscribed: number }
  lists: number
  audiences: number
  new_subscriptions: number
  campaigns: Record<string, number>
  email: { sent: number; opened: number; clicked: number; unsubscribed: number; failed: number; open_rate: number; click_rate: number; unsubscribe_rate: number }
  recent: { id: number; name: string; kind: string; status: string; date: string | null; stats: { sent: number; opened: number; clicked: number; open_rate: number; click_rate: number } }[]
}

export const useAudiences = () => useQuery({ queryKey: ['audiences'], queryFn: () => api<Audience[]>('/audiences') })

const LICENCES = { active: 'Has an active licence', lapsed: 'Licences lapsed (none active)', none: 'Never had a licence' }
const n = (v: number) => v.toLocaleString('en-US')

/** Marketing home: who can be reached, and how recent campaigns did. */
export default function MarketingOverview() {
  const nav = useNavigate()
  const [days, setDays] = useState('90')
  const { data } = useQuery({ queryKey: ['marketing-overview', days], queryFn: () => api<Overview>('/marketing/overview', { params: { days } }) })
  const e = data?.email
  return (
    <>
      <PageHeader
        title="Marketing"
        subtitle="Email campaigns and newsletters, the audiences and lists they go to, and how they perform"
        actions={
          <SegmentedControl
            value={days}
            onChange={setDays}
            data={[
              { value: '30', label: '30 days' },
              { value: '90', label: '90 days' },
              { value: '365', label: '12 months' },
            ]}
          />
        }
      />
      <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }} mb="md">
        <Card withBorder padding="md" className="clickable-row" onClick={() => nav('/email/campaigns')}>
          <Group gap="xs">
            <IconMail size={18} />
            <Text fw={600}>Campaigns</Text>
          </Group>
          <Text size="sm" c="dimmed" mt={4}>
            Create, schedule and follow campaigns and newsletters
          </Text>
        </Card>
        <Card withBorder padding="md" className="clickable-row" onClick={() => nav('/marketing/audiences')}>
          <Group gap="xs">
            <IconUsersGroup size={18} />
            <Text fw={600}>Audiences · {data?.audiences ?? '…'}</Text>
          </Group>
          <Text size="sm" c="dimmed" mt={4}>
            Saved filters that keep themselves up to date
          </Text>
        </Card>
        <Card withBorder padding="md" className="clickable-row" onClick={() => nav('/email/lists')}>
          <Group gap="xs">
            <IconListDetails size={18} />
            <Text fw={600}>Lists · {data?.lists ?? '…'}</Text>
          </Group>
          <Text size="sm" c="dimmed" mt={4}>
            Static lists and newsletter subscribers
          </Text>
        </Card>
        <Card withBorder padding="md" className="clickable-row" onClick={() => nav('/contacts')}>
          <Group gap="xs">
            <IconAddressBook size={18} />
            <Text fw={600}>Contacts</Text>
          </Group>
          <Text size="sm" c="dimmed" mt={4}>
            Select contacts to add them to a list
          </Text>
        </Card>
      </SimpleGrid>
      {data && e && (
        <>
          <Title order={5} mb="xs">
            Reach
          </Title>
          <SimpleGrid cols={{ base: 2, md: 4 }} mb="md">
            <Stat label="Contacts with email" value={n(data.contacts.with_email)} info="Contacts that have an email address." />
            <Stat label="Can be emailed" value={n(data.contacts.reachable)} hint="not unsubscribed" info="Contacts with an email address who have not unsubscribed. Campaigns can reach them." />
            <Stat label="With marketing consent" value={n(data.contacts.with_consent)} hint="needed for newsletters" info="Contacts who opted in to marketing email and have not unsubscribed. Campaigns set to require consent only go to them." />
            <Stat label="Unsubscribed" value={n(data.contacts.unsubscribed)} hint={`${n(data.new_subscriptions)} new list subscriptions in ${data.days} days`} info="Contacts who unsubscribed from all marketing email. They are never emailed by a campaign." />
          </SimpleGrid>
          <Title order={5} mb="xs">
            Last {data.days} days
          </Title>
          <SimpleGrid cols={{ base: 2, md: 4 }} mb="md">
            <Stat label="Emails delivered" value={n(e.sent)} hint={e.failed ? `${n(e.failed)} failed` : undefined} info="Campaign emails accepted by the mail server in the period. Failed: refused by the server." />
            <Stat label="Open rate" value={`${e.open_rate}%`} hint={`${n(e.opened)} opened`} info="Recipients who opened ÷ emails delivered. Opens are counted with a tracking image, so mail apps that block images (and privacy features that load them all) make it approximate." />
            <Stat label="Click rate" value={`${e.click_rate}%`} hint={`${n(e.clicked)} clicked`} info="Recipients who clicked at least one link ÷ emails delivered." />
            <Stat label="Unsubscribe rate" value={`${e.unsubscribe_rate}%`} hint={`${n(e.unsubscribed)} unsubscribed`} info="Recipients who used the unsubscribe link ÷ emails delivered." />
          </SimpleGrid>
          <Card withBorder>
            <Group justify="space-between" mb="xs">
              <Title order={5}>Recent campaigns</Title>
              <Anchor component={Link} to="/email/campaigns" size="sm">
                All campaigns
              </Anchor>
            </Group>
            {data.recent.length ? (
              <ScrollArea type="auto" offsetScrollbars>
                <Table highlightOnHover miw={640}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Name</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th>Date</Table.Th>
                      <Table.Th ta="right">Sent</Table.Th>
                      <Table.Th ta="right">Opened</Table.Th>
                      <Table.Th ta="right">Clicked</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {data.recent.map((c) => (
                      <Table.Tr key={c.id} className="clickable-row" onClick={() => nav(`/email/campaigns/${c.id}`)}>
                        <Table.Td fw={500}>
                          {c.kind === 'newsletter' ? 'Newsletter · ' : ''}
                          {c.name}
                        </Table.Td>
                        <Table.Td>
                          <Badge variant="light" color={c.status === 'sent' ? 'green' : c.status === 'paused' ? 'orange' : 'blue'}>
                            {c.status}
                          </Badge>
                        </Table.Td>
                        <Table.Td>{c.date ? fmtDate(c.date) : ''}</Table.Td>
                        <Table.Td ta="right">{n(c.stats.sent)}</Table.Td>
                        <Table.Td ta="right">{c.stats.open_rate}%</Table.Td>
                        <Table.Td ta="right">{c.stats.click_rate}%</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            ) : (
              <Text c="dimmed" size="sm">
                No campaign has been sent yet.
              </Text>
            )}
          </Card>
        </>
      )}
    </>
  )
}

/** One line summary of an audience's rules, e.g. "Lead, Customer · France · active licence". */
export function describeRules(r: AudienceRules, listNames: Record<number, string> = {}) {
  const parts = [
    r.lifecycle?.map((v) => LIFECYCLES[v] ?? v).join(' or '),
    r.role?.map((v) => CONTACT_ROLES[v] ?? v).join(' or '),
    r.account_type?.map((v) => ACCOUNT_TYPES[v] ?? v).join(' or '),
    r.country?.join(' or '),
    r.source?.map((v) => LEAD_SOURCES[v] ?? v).join(' or '),
    r.licence && LICENCES[r.licence],
    r.product && `active ${r.product} licence`,
    r.renews_within_days && `renews within ${r.renews_within_days} days`,
    r.list_ids?.length && `in ${r.list_ids.map((i) => listNames[i] ?? `list ${i}`).join(' or ')}`,
    r.created_within_days && `added in the last ${r.created_within_days} days`,
    r.consent_only && 'with marketing consent',
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : 'All contacts with an email address'
}

export function AudienceForm({ opened, onClose, audience, initialRules }: { opened: boolean; onClose: () => void; audience?: Audience; initialRules?: AudienceRules }) {
  const nav = useNavigate()
  const { data: brands } = useBrands()
  const { data: lists } = useLists()
  const [form, setForm] = useState({ name: '', description: '', brand_id: null as number | null, rules: {} as AudienceRules })
  useEffect(() => {
    if (opened)
      setForm(
        audience
          ? { name: audience.name, description: audience.description ?? '', brand_id: audience.brand_id, rules: audience.rules }
          : { name: '', description: '', brand_id: null, rules: initialRules ?? {} },
      )
  }, [opened, audience, initialRules])
  const r = form.rules
  const set = (patch: Partial<AudienceRules>) => setForm({ ...form, rules: { ...r, ...patch } })
  const [debounced] = useDebouncedValue(r, 300)
  const { data: pv } = useQuery({
    queryKey: ['audience-preview', debounced],
    queryFn: () => api<Counts & { sample: { id: number; name: string; email: string; company: string | null }[] }>('/audiences/preview', { method: 'POST', body: debounced }),
    enabled: opened,
    placeholderData: keepPreviousData,
  })
  const save = useApiMutation(
    () =>
      api<Audience>(audience ? `/audiences/${audience.id}` : '/audiences', {
        method: audience ? 'PUT' : 'POST',
        body: { ...form, description: form.description || null },
      }),
    {
      invalidate: [['audiences'], ['audience', audience?.id], ['contacts']],
      success: audience ? 'Audience saved' : 'Audience created',
      onSuccess: (a) => {
        onClose()
        if (!audience) nav(`/marketing/audiences/${a.id}`)
      },
    },
  )
  return (
    <Modal opened={opened} onClose={onClose} title={audience ? 'Edit audience' : 'New audience'} size="xl">
      <Stack>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-autofocus />
          <Select label="Brand" placeholder="Any" clearable data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))} value={form.brand_id ? String(form.brand_id) : null} onChange={(v) => setForm({ ...form, brand_id: v ? Number(v) : null })} />
        </SimpleGrid>
        <Textarea label="Description" autosize minRows={1} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <Text size="sm" fw={600}>
          Contacts who match all of these
        </Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <MultiSelect label="Lifecycle" placeholder="Any" data={toOptions(LIFECYCLES)} value={r.lifecycle ?? []} onChange={(v) => set({ lifecycle: v })} clearable />
          <MultiSelect label="Contact role" placeholder="Any" data={toOptions(CONTACT_ROLES)} value={r.role ?? []} onChange={(v) => set({ role: v })} clearable />
          <MultiSelect label="Account type" placeholder="Any" data={toOptions(ACCOUNT_TYPES)} value={r.account_type ?? []} onChange={(v) => set({ account_type: v })} clearable />
          <TagsInput label="Country" placeholder="Any · type and press Enter" description="The contact's country, or its account's" value={r.country ?? []} onChange={(v) => set({ country: v })} clearable />
          <MultiSelect label="Lead source" placeholder="Any" data={toOptions(LEAD_SOURCES)} value={r.source ?? []} onChange={(v) => set({ source: v })} clearable />
          <UserPicker label="Contact owner" placeholder="Anyone" value={r.owner_id ?? null} onChange={(v) => set({ owner_id: v })} />
          <Select label="Licences (of the account)" placeholder="Any" clearable data={toOptions(LICENCES)} value={r.licence ?? null} onChange={(v) => set({ licence: v as AudienceRules['licence'] })} />
          <TextInput label="Holds an active licence for" placeholder="Product name contains… e.g. Hardware" value={r.product ?? ''} onChange={(e) => set({ product: e.target.value || null })} />
          <NumberInput label="A licence renews within (days)" placeholder="Any" min={1} max={730} value={r.renews_within_days ?? ''} onChange={(v) => set({ renews_within_days: typeof v === 'number' ? v : null })} />
          <NumberInput label="Added to the CRM in the last (days)" placeholder="Any time" min={1} max={3650} value={r.created_within_days ?? ''} onChange={(v) => set({ created_within_days: typeof v === 'number' ? v : null })} />
          <MultiSelect label="Subscribed to a list" placeholder="Any" data={(lists ?? []).map((l) => ({ value: String(l.id), label: l.name }))} value={(r.list_ids ?? []).map(String)} onChange={(v) => set({ list_ids: v.map(Number) })} clearable />
          <Checkbox mt="xl" label="Only contacts with marketing consent" checked={!!r.consent_only} onChange={(e) => set({ consent_only: e.currentTarget.checked })} />
        </SimpleGrid>
        {pv && (
          <Alert color="violet" variant="light" title={`${n(pv.matching)} contacts match today`}>
            {n(pv.reachable)} can be emailed, {n(pv.with_consent)} with marketing consent.
            {pv.sample.length > 0 && (
              <Text size="xs" c="dimmed" mt={4}>
                e.g. {pv.sample.slice(0, 5).map((s) => `${s.name}${s.company ? ` (${s.company})` : ''}`).join(', ')}
              </Text>
            )}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button loading={save.isPending} disabled={!form.name.trim()} onClick={() => save.mutate(undefined)}>
            Save audience
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

export function Audiences() {
  const nav = useNavigate()
  const { canWrite } = useAuth()
  const { data } = useAudiences()
  const { data: lists } = useLists()
  const listNames = Object.fromEntries((lists ?? []).map((l) => [l.id, l.name]))
  const [open, setOpen] = useState(false)
  return (
    <>
      <PageHeader
        title="Audiences"
        subtitle="Saved filters on your contacts. Campaigns sent to an audience go to whoever matches on the day they are sent."
        actions={
          canWrite && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setOpen(true)}>
              New audience
            </Button>
          )
        }
      />
      <Card withBorder>
        {data?.length ? (
          <ScrollArea type="auto" offsetScrollbars>
            <Table highlightOnHover miw={720}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Name</Table.Th>
                  <Table.Th>Rules</Table.Th>
                  <Table.Th ta="right">Matching</Table.Th>
                  <Table.Th ta="right">Can be emailed</Table.Th>
                  <Table.Th ta="right">With consent</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.map((a) => (
                  <Table.Tr key={a.id} className="clickable-row" onClick={() => nav(`/marketing/audiences/${a.id}`)}>
                    <Table.Td fw={500}>{a.name}</Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed" lineClamp={2}>
                        {describeRules(a.rules, listNames)}
                      </Text>
                    </Table.Td>
                    <Table.Td ta="right">{n(a.counts?.matching ?? 0)}</Table.Td>
                    <Table.Td ta="right">{n(a.counts?.reachable ?? 0)}</Table.Td>
                    <Table.Td ta="right">{n(a.counts?.with_consent ?? 0)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        ) : (
          <Text c="dimmed" size="sm">
            No audience yet. An audience is a saved filter, for example customers whose licence renews in the next 90 days, or leads in France with marketing consent. It
            stays up to date as contacts change.
          </Text>
        )}
      </Card>
      <AudienceForm opened={open} onClose={() => setOpen(false)} />
    </>
  )
}

export function AudienceDetail() {
  const id = Number(useParams().id)
  const nav = useNavigate()
  const { canWrite } = useAuth()
  const { data: a } = useQuery({ queryKey: ['audience', id], queryFn: () => api<Audience>(`/audiences/${id}`) })
  const { data: lists } = useLists()
  const listNames = Object.fromEntries((lists ?? []).map((l) => [l.id, l.name]))
  const [q, setQ] = useState('')
  const [debounced] = useDebouncedValue(q, 250)
  const [page, setPage] = useState(1)
  const { data: people } = useQuery({
    queryKey: ['audience-contacts', id, debounced, page],
    queryFn: () =>
      api<{ total: number; items: { id: number; name: string; email: string; company: string | null; lifecycle: string; consent: boolean; unsubscribed: boolean }[] }>(
        `/audiences/${id}/contacts`,
        { params: { q: debounced, page, page_size: 50 } },
      ),
    placeholderData: keepPreviousData,
  })
  const [edit, setEdit] = useState(false)
  const [snapshot, setSnapshot] = useState<string | null>(null)
  const toList = useApiMutation(() => api<{ id: number }>(`/audiences/${id}/save-as-list`, { method: 'POST', body: { name: snapshot } }), {
    invalidate: [['lists']],
    success: 'List created',
    onSuccess: (l) => nav(`/email/lists/${l.id}`),
  })
  const del = useApiMutation(() => api(`/audiences/${id}`, { method: 'DELETE' }), {
    invalidate: [['audiences']],
    success: 'Audience deleted',
    onSuccess: () => nav('/marketing/audiences'),
  })
  if (!a) return null
  return (
    <>
      <PageHeader
        title={a.name}
        subtitle={
          <>
            <Anchor component={Link} to="/marketing/audiences" size="sm">
              Audiences
            </Anchor>{' '}
            · {describeRules(a.rules, listNames)}
          </>
        }
        actions={
          canWrite && (
            <>
              <Button variant="default" onClick={() => nav('/email/campaigns', { state: { audienceId: a.id } })} leftSection={<IconMail size={16} />}>
                Email this audience
              </Button>
              <Button variant="default" onClick={() => setSnapshot(`${a.name} · ${fmtDate(new Date().toISOString())}`)}>
                Save as a list
              </Button>
              <Button variant="default" onClick={() => setEdit(true)}>
                Edit rules
              </Button>
              <Button
                variant="subtle"
                color="red"
                leftSection={<IconTrash size={16} />}
                onClick={() =>
                  modals.openConfirmModal({
                    title: 'Delete this audience?',
                    children: <Text size="sm">Contacts are not deleted. Campaigns already sent keep their recipients.</Text>,
                    labels: { confirm: 'Delete', cancel: 'Cancel' },
                    confirmProps: { color: 'red' },
                    onConfirm: () => del.mutate(undefined),
                  })
                }
              >
                Delete
              </Button>
            </>
          )
        }
      />
      {a.description && (
        <Text size="sm" mb="sm">
          {a.description}
        </Text>
      )}
      {a.counts && (
        <SimpleGrid cols={{ base: 1, xs: 3 }} mb="md">
          <Stat label="Matching today" value={n(a.counts.matching)} info="Contacts that match the rules now. The audience is worked out again each time a campaign uses it." />
          <Stat label="Can be emailed" value={n(a.counts.reachable)} hint="not unsubscribed" info="Matching contacts with an email address who have not unsubscribed." />
          <Stat label="With marketing consent" value={n(a.counts.with_consent)} info="Matching contacts who opted in to marketing email: who a campaign that requires consent reaches." />
        </SimpleGrid>
      )}
      <Card withBorder p={0}>
        <Group p="sm">
          <TextInput placeholder="Search name or email" value={q} onChange={(e) => (setQ(e.target.value), setPage(1))} w={280} />
        </Group>
        <ScrollArea.Autosize mah={600} type="auto" offsetScrollbars>
          <Table highlightOnHover miw={640} stickyHeader>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Email</Table.Th>
                <Table.Th>Account</Table.Th>
                <Table.Th>Lifecycle</Table.Th>
                <Table.Th>Marketing</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {people?.items.map((p) => (
                <Table.Tr key={p.id} className="clickable-row" onClick={() => nav(`/contacts/${p.id}`)}>
                  <Table.Td fw={500}>{p.name}</Table.Td>
                  <Table.Td>{p.email}</Table.Td>
                  <Table.Td>{p.company}</Table.Td>
                  <Table.Td>{LIFECYCLES[p.lifecycle] ?? p.lifecycle}</Table.Td>
                  <Table.Td>
                    {p.unsubscribed ? (
                      <Badge color="red" variant="light">
                        Unsubscribed
                      </Badge>
                    ) : p.consent ? (
                      <Badge color="green" variant="light">
                        Consent
                      </Badge>
                    ) : null}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea.Autosize>
        <Group px="sm" pb="sm" display="block">
          <Pager page={page} total={people?.total ?? 0} pageSize={50} onChange={setPage} />
        </Group>
      </Card>
      <AudienceForm opened={edit} onClose={() => setEdit(false)} audience={a} />
      <Modal opened={snapshot !== null} onClose={() => setSnapshot(null)} title="Save as a static list">
        <Stack>
          <Text size="sm" c="dimmed">
            Copies the {n(a.counts?.matching ?? 0)} contacts who match today into a new list. The list will not change when contacts do, which suits, for example, the invitees of an
            event.
          </Text>
          <TextInput label="List name" value={snapshot ?? ''} onChange={(e) => setSnapshot(e.target.value)} data-autofocus />
          <Group justify="flex-end">
            <Button loading={toList.isPending} disabled={!snapshot?.trim()} onClick={() => toList.mutate(undefined)}>
              Create list
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  )
}
