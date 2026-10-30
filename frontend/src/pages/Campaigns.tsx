import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  Modal,
  MultiSelect,
  Progress,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  TagsInput,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import { IconCalendar, IconPlayerPause, IconPlayerPlay, IconPlus, IconSend, IconTestPipe, IconX } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { PageHeader, Pager } from '../components/common'
import { Stat } from '../components/ui'
import { EmailEditor, MailStatus, useMailSettings } from '../components/EmailEditor'
import { useApiMutation, useBrands } from '../hooks'
import { fmtDate } from '../labels'
import { useEmailTemplates } from './EmailTemplates'
import { useLists } from './MailingLists'
import { useAudiences } from './Marketing'

interface Stats {
  queued: number
  sent: number
  failed: number
  skipped: number
  opened: number
  clicked: number
  unsubscribed: number
  open_rate: number
  click_rate: number
}

interface Campaign {
  id: number
  name: string
  kind: 'campaign' | 'newsletter'
  brand_id: number | null
  template_id: number | null
  subject: string
  preheader: string | null
  body_html: string
  from_name: string | null
  reply_to: string | null
  list_ids: number[]
  audience_ids: number[]
  require_consent: boolean
  track_opens: boolean
  track_clicks: boolean
  status: 'draft' | 'scheduled' | 'sending' | 'paused' | 'sent' | 'cancelled'
  scheduled_at: string | null
  started_at: string | null
  finished_at: string | null
  last_error: string | null
  created_at: string
  stats: Stats | null
}

const STATUS: Record<Campaign['status'], { label: string; color: string }> = {
  draft: { label: 'Draft', color: 'gray' },
  scheduled: { label: 'Scheduled', color: 'blue' },
  sending: { label: 'Sending', color: 'violet' },
  paused: { label: 'Paused', color: 'orange' },
  sent: { label: 'Sent', color: 'green' },
  cancelled: { label: 'Cancelled', color: 'gray' },
}

const editable = (c: Campaign) => c.status === 'draft' || c.status === 'scheduled'

export default function Campaigns() {
  const nav = useNavigate()
  const { canWrite } = useAuth()
  const { data } = useQuery({ queryKey: ['campaigns'], queryFn: () => api<Campaign[]>('/campaigns'), refetchInterval: 15_000 })
  const { data: templates } = useEmailTemplates()
  const { data: lists } = useLists()
  const { data: audiences } = useAudiences()
  // "Email this audience" (on an audience's page) opens this form with the audience chosen
  const fromAudience = (useLocation().state as { audienceId?: number } | null)?.audienceId
  const [open, setOpen] = useState(!!fromAudience)
  const [form, setForm] = useState({ name: '', kind: 'campaign', template_id: null as string | null, list_ids: [] as string[], audience_ids: fromAudience ? [String(fromAudience)] : ([] as string[]) })
  const create = useApiMutation(
    () =>
      api<Campaign>('/campaigns', {
        method: 'POST',
        body: { name: form.name, kind: form.kind, template_id: form.template_id ? Number(form.template_id) : null, list_ids: form.list_ids.map(Number), audience_ids: form.audience_ids.map(Number) },
      }),
    { invalidate: [['campaigns']], onSuccess: (c) => nav(`/email/campaigns/${c.id}`) },
  )
  return (
    <>
      <PageHeader help="campaigns"
        title="Campaigns & newsletters"
        subtitle="Bulk email to your lists, with opens, clicks and unsubscribes"
        actions={
          <>
            <MailStatus />
            {canWrite && (
              <Button leftSection={<IconPlus size={16} />} onClick={() => setOpen(true)}>
                New campaign
              </Button>
            )}
          </>
        }
      />
      <Card withBorder>
        {data?.length ? (
          <Table.ScrollContainer minWidth={760}>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Name</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Sent</Table.Th>
                  <Table.Th ta="right">Recipients</Table.Th>
                  <Table.Th ta="right">Opened</Table.Th>
                  <Table.Th ta="right">Clicked</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.map((c) => (
                  <Table.Tr key={c.id} className="clickable-row" onClick={() => nav(`/email/campaigns/${c.id}`)}>
                    <Table.Td>
                      <Text size="sm" fw={500}>
                        {c.name}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {c.kind === 'newsletter' ? 'Newsletter · ' : ''}
                        {c.subject}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={STATUS[c.status].color} variant="light">
                        {STATUS[c.status].label}
                      </Badge>
                    </Table.Td>
                    <Table.Td>{c.status === 'scheduled' ? `for ${new Date(c.scheduled_at!).toLocaleString()}` : fmtDate(c.started_at)}</Table.Td>
                    <Table.Td ta="right">{c.stats ? c.stats.sent + c.stats.queued + c.stats.failed : '—'}</Table.Td>
                    <Table.Td ta="right">{c.stats?.sent ? `${c.stats.open_rate}%` : '—'}</Table.Td>
                    <Table.Td ta="right">{c.stats?.sent ? `${c.stats.click_rate}%` : '—'}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        ) : (
          <Text size="sm" c="dimmed">
            No campaigns yet. Create a template and a list first, then a campaign.
          </Text>
        )}
      </Card>
      <Modal opened={open} onClose={() => setOpen(false)} title="New campaign">
        <Stack>
          <TextInput label="Name (internal)" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-autofocus />
          <SegmentedControl
            value={form.kind}
            onChange={(v) => setForm({ ...form, kind: v })}
            data={[
              { value: 'campaign', label: 'Campaign' },
              { value: 'newsletter', label: 'Newsletter' },
            ]}
          />
          <Select label="Template" placeholder="Start from a template" clearable data={(templates ?? []).map((t) => ({ value: String(t.id), label: t.name }))} value={form.template_id} onChange={(v) => setForm({ ...form, template_id: v })} />
          <MultiSelect label="Send to lists" data={(lists ?? []).map((l) => ({ value: String(l.id), label: `${l.name} (${l.subscribed})` }))} value={form.list_ids} onChange={(v) => setForm({ ...form, list_ids: v })} />
          <MultiSelect
            label="And/or to audiences"
            description="Saved filters: whoever matches when sending starts"
            data={(audiences ?? []).map((a) => ({ value: String(a.id), label: `${a.name} (${a.counts?.reachable ?? 0})` }))}
            value={form.audience_ids}
            onChange={(v) => setForm({ ...form, audience_ids: v })}
          />
          <Group justify="flex-end">
            <Button loading={create.isPending} disabled={!form.name.trim()} onClick={() => create.mutate(undefined)}>
              Create
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  )
}

interface Recipient {
  id: number
  contact_id: number | null
  email: string
  status: string
  reason: string | null
  sent_at: string | null
  opened_at: string | null
  clicked_at: string | null
  unsubscribed_at: string | null
}

function Report({ c }: { c: Campaign }) {
  const s = c.stats!
  const [filter, setFilter] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const { data } = useQuery({
    queryKey: ['campaign-recipients', c.id, filter, page],
    queryFn: () => api<{ total: number; items: Recipient[] }>(`/campaigns/${c.id}/recipients`, { params: { status: filter ?? undefined, page, page_size: 50 } }),
    refetchInterval: c.status === 'sending' ? 10_000 : false,
  })
  const total = s.sent + s.queued + s.failed
  return (
    <Stack>
      {c.status === 'sending' && (
        <Card withBorder padding="sm">
          <Group justify="space-between" mb={6}>
            <Text size="sm">Sending in the background…</Text>
            <Text size="sm" c="dimmed">
              {s.sent + s.failed} / {total}
            </Text>
          </Group>
          <Progress value={total ? (100 * (s.sent + s.failed)) / total : 0} animated />
        </Card>
      )}
      <SimpleGrid cols={{ base: 2, sm: 3, md: 6 }}>
        <Stat label="Sent" value={s.sent} hint={s.queued ? `${s.queued} queued` : undefined} info="Emails accepted by the mail server. Queued: waiting for the next batch (sending stays under the per-minute limit, CRM_BULK_RATE_PER_MINUTE)." />
        <Stat label="Opened" value={`${s.open_rate}%`} hint={`${s.opened} people`} info="Recipients who opened ÷ emails sent. Counted with a tracking image, so approximate." />
        <Stat label="Clicked" value={`${s.click_rate}%`} hint={`${s.clicked} people`} info="Recipients who clicked at least one link ÷ emails sent." />
        <Stat label="Unsubscribed" value={s.unsubscribed} info="Recipients who used this campaign's unsubscribe link." />
        <Stat label="Failed" value={s.failed} info="Emails the mail server refused. The recipient list shows each reason." />
        <Stat label="Skipped" value={s.skipped} hint="no email, opted out, no consent" info="Contacts in the lists or audiences that were not emailed: no address, unsubscribed, or no marketing consent when the campaign requires it." />
      </SimpleGrid>
      <Text size="xs" c="dimmed">
        Opens are approximate: many mail apps block or pre-load images. Clicks are reliable.
      </Text>
      <Card withBorder>
        <Group mb="sm">
          <Title order={5}>Recipients</Title>
          <SegmentedControl
            size="xs"
            value={filter ?? 'all'}
            onChange={(v) => {
              setFilter(v === 'all' ? null : v)
              setPage(1)
            }}
            data={['all', 'sent', 'opened', 'clicked', 'unsubscribed', 'failed', 'skipped', 'queued'].map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1) }))}
          />
        </Group>
        <Table.ScrollContainer minWidth={640}>
          <Table verticalSpacing={4} fz="sm">
            <Table.Tbody>
              {data?.items.map((r) => (
                <Table.Tr key={r.id}>
                  <Table.Td>{r.contact_id ? <Link to={`/contacts/${r.contact_id}`}>{r.email}</Link> : r.email}</Table.Td>
                  <Table.Td>
                    <Badge size="sm" variant="light" color={r.status === 'sent' ? 'green' : r.status === 'failed' ? 'red' : 'gray'}>
                      {r.status}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed">
                      {[r.opened_at && 'opened', r.clicked_at && 'clicked', r.unsubscribed_at && 'unsubscribed'].filter(Boolean).join(' · ') || r.reason}
                    </Text>
                  </Table.Td>
                  <Table.Td>{r.sent_at ? new Date(r.sent_at).toLocaleString() : ''}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {data && <Pager page={page} total={data.total} pageSize={50} onChange={setPage} />}
      </Card>
    </Stack>
  )
}

export function CampaignDetail() {
  const id = Number(useParams().id)
  const nav = useNavigate()
  const { canWrite, user } = useAuth()
  const { data: settings } = useMailSettings()
  const { data: lists } = useLists()
  const { data: audiences } = useAudiences()
  const { data: brands } = useBrands()
  const key = ['campaign', id]
  const { data: c } = useQuery({
    queryKey: key,
    queryFn: () => api<Campaign>(`/campaigns/${id}`),
    refetchInterval: (q) => (q.state.data?.status === 'sending' ? 10_000 : false),
  })
  const [draft, setDraft] = useState<Campaign | null>(null)
  useEffect(() => {
    if (c) setDraft(c)
  }, [c])
  const dirty = !!draft && !!c && JSON.stringify(draft) !== JSON.stringify(c)
  const { data: aud } = useQuery({
    queryKey: ['campaign-audience', id, c?.list_ids, c?.audience_ids, c?.require_consent],
    queryFn: () => api<{ recipients: number; skipped: number; skipped_by_reason: Record<string, number> }>(`/campaigns/${id}/audience`),
    enabled: !!c && editable(c),
  })
  const save = useApiMutation(
    () => {
      const { name, kind, brand_id, template_id, subject, preheader, body_html, from_name, reply_to, list_ids, audience_ids, require_consent, track_opens, track_clicks } = draft!
      return api<Campaign>(`/campaigns/${id}`, { method: 'PUT', body: { name, kind, brand_id, template_id, subject, preheader, body_html, from_name: from_name || null, reply_to: reply_to || null, list_ids, audience_ids, require_consent, track_opens, track_clicks } })
    },
    { invalidate: [key, ['campaigns'], ['campaign-audience', id]], success: 'Saved' },
  )
  const [testOpen, setTestOpen] = useState(false)
  const [testTo, setTestTo] = useState<string[]>([])
  const test = useApiMutation(() => api(`/campaigns/${id}/test`, { method: 'POST', body: { to: testTo } }), { success: 'Test sent', onSuccess: () => setTestOpen(false) })
  const [schedOpen, setSchedOpen] = useState(false)
  const [when, setWhen] = useState('')
  const send = useApiMutation((scheduled_at: string | null) => api<Campaign>(`/campaigns/${id}/send`, { method: 'POST', body: { scheduled_at } }), {
    invalidate: [key, ['campaigns']],
    success: 'Campaign started',
    onSuccess: () => setSchedOpen(false),
  })
  const act = useApiMutation((action: string) => api<Campaign>(`/campaigns/${id}/action`, { method: 'POST', body: { action } }), { invalidate: [key, ['campaigns']] })
  const del = useApiMutation(() => api(`/campaigns/${id}`, { method: 'DELETE' }), { invalidate: [['campaigns']], onSuccess: () => nav('/email/campaigns') })

  if (!c || !draft) return null
  const edit = editable(c) && canWrite
  const confirmSend = () =>
    modals.openConfirmModal({
      title: 'Send this campaign now?',
      children: (
        <Text size="sm">
          {aud?.recipients ?? 0} people will receive “{c.subject}”. Sending runs in the background at about {settings?.rate_per_minute ?? 0} emails per minute and can be paused.
        </Text>
      ),
      labels: { confirm: 'Send now', cancel: 'Cancel' },
      onConfirm: () => send.mutate(null),
    })

  return (
    <>
      <PageHeader
        title={
          <Group gap="sm">
            {c.name}
            <Badge color={STATUS[c.status].color} variant="light">
              {STATUS[c.status].label}
            </Badge>
          </Group>
        }
        subtitle={c.status === 'scheduled' ? `Scheduled for ${new Date(c.scheduled_at!).toLocaleString()}` : c.started_at ? `Started ${new Date(c.started_at).toLocaleString()}` : 'Draft'}
        actions={
          canWrite && (
            <>
              {edit && (
                <>
                  <Button variant="default" onClick={() => save.mutate(undefined)} loading={save.isPending} disabled={!dirty}>
                    Save
                  </Button>
                  <Button variant="default" leftSection={<IconTestPipe size={16} />} disabled={dirty} onClick={() => { setTestTo(user ? [user.email] : []); setTestOpen(true) }}>
                    Send test
                  </Button>
                </>
              )}
              {c.status === 'draft' && (
                <>
                  <Button variant="light" leftSection={<IconCalendar size={16} />} disabled={dirty || !aud?.recipients} onClick={() => setSchedOpen(true)}>
                    Schedule
                  </Button>
                  <Button leftSection={<IconSend size={16} />} disabled={dirty || !aud?.recipients || !settings?.bulk.enabled} onClick={confirmSend} loading={send.isPending}>
                    Send now
                  </Button>
                </>
              )}
              {c.status === 'scheduled' && (
                <Button variant="light" onClick={() => act.mutate('unschedule')}>
                  Unschedule
                </Button>
              )}
              {c.status === 'sending' && (
                <Button variant="light" color="orange" leftSection={<IconPlayerPause size={16} />} onClick={() => act.mutate('pause')}>
                  Pause
                </Button>
              )}
              {c.status === 'paused' && (
                <Button leftSection={<IconPlayerPlay size={16} />} onClick={() => act.mutate('resume')}>
                  Resume
                </Button>
              )}
              {['scheduled', 'sending', 'paused'].includes(c.status) && (
                <Button
                  variant="subtle"
                  color="red"
                  leftSection={<IconX size={16} />}
                  onClick={() =>
                    modals.openConfirmModal({
                      title: 'Cancel the campaign?',
                      children: <Text size="sm">Emails not sent yet will not be sent.</Text>,
                      labels: { confirm: 'Cancel campaign', cancel: 'Back' },
                      confirmProps: { color: 'red' },
                      onConfirm: () => act.mutate('cancel'),
                    })
                  }
                >
                  Cancel
                </Button>
              )}
              {c.status === 'draft' && (
                <Button variant="subtle" color="red" onClick={() => del.mutate(undefined)}>
                  Delete
                </Button>
              )}
            </>
          )
        }
      />
      {c.last_error && (
        <Alert color="orange" mb="md" title="Sending paused">
          {c.last_error}. Fix the mail server settings, then Resume.
        </Alert>
      )}
      {!settings?.bulk.enabled && editable(c) && (
        <Alert color="orange" mb="md" title="Bulk email is not set up">
          An administrator needs to configure the SMTP server (CRM_BULK_MAIL_BACKEND / CRM_SMTP_*) before campaigns can be sent. You can still prepare this one.
        </Alert>
      )}
      {c.stats && c.status !== 'scheduled' && <Report c={c} />}
      {editable(c) && (
        <Stack>
          <Card withBorder>
            <SimpleGrid cols={{ base: 1, md: 3 }}>
              <TextInput label="Name (internal)" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} readOnly={!edit} />
              <TextInput label="From name" placeholder={settings?.from_name ?? 'Your company'} value={draft.from_name ?? ''} onChange={(e) => setDraft({ ...draft, from_name: e.target.value })} readOnly={!edit} description={`From address: ${settings?.from ?? 'CRM_MAIL_FROM not set'}`} />
              <TextInput label="Reply-to" placeholder="sales@…" value={draft.reply_to ?? ''} onChange={(e) => setDraft({ ...draft, reply_to: e.target.value })} readOnly={!edit} />
              <MultiSelect
                label="Lists"
                data={(lists ?? []).map((l) => ({ value: String(l.id), label: `${l.name} (${l.subscribed})` }))}
                value={draft.list_ids.map(String)}
                onChange={(v) => setDraft({ ...draft, list_ids: v.map(Number) })}
                readOnly={!edit}
              />
              <MultiSelect
                label="Audiences"
                description="Resolved when sending starts"
                data={(audiences ?? []).map((a) => ({ value: String(a.id), label: `${a.name} (${a.counts?.reachable ?? 0})` }))}
                value={(draft.audience_ids ?? []).map(String)}
                onChange={(v) => setDraft({ ...draft, audience_ids: v.map(Number) })}
                readOnly={!edit}
              />
              <Select label="Brand" placeholder="Any" clearable data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))} value={draft.brand_id ? String(draft.brand_id) : null} onChange={(v) => setDraft({ ...draft, brand_id: v ? Number(v) : null })} disabled={!edit} />
              <Stack gap={6} mt="lg">
                <Checkbox label="Only contacts with marketing consent" checked={draft.require_consent} onChange={(e) => setDraft({ ...draft, require_consent: e.currentTarget.checked })} disabled={!edit} />
                <Group>
                  <Switch size="xs" label="Track opens" checked={draft.track_opens} onChange={(e) => setDraft({ ...draft, track_opens: e.currentTarget.checked })} disabled={!edit} />
                  <Switch size="xs" label="Track clicks" checked={draft.track_clicks} onChange={(e) => setDraft({ ...draft, track_clicks: e.currentTarget.checked })} disabled={!edit} />
                </Group>
              </Stack>
            </SimpleGrid>
            {aud && (
              <Text size="sm" mt="sm">
                <b>{aud.recipients}</b> recipients
                {aud.skipped > 0 && (
                  <Text span c="dimmed">
                    {' '}
                    · left out:{' '}
                    {Object.entries(aud.skipped_by_reason)
                      .map(([r, n]) => `${n} ${r}`)
                      .join(', ')}
                  </Text>
                )}
                {dirty && (
                  <Text span c="orange">
                    {' '}
                    (save to update)
                  </Text>
                )}
              </Text>
            )}
          </Card>
          <EmailEditor value={draft} onChange={(v) => setDraft({ ...draft, ...v })} readOnly={!edit} />
        </Stack>
      )}
      <Modal opened={testOpen} onClose={() => setTestOpen(false)} title="Send a test">
        <Stack>
          <TagsInput label="To" description="Up to 5 addresses; merge fields use sample values" value={testTo} onChange={setTestTo} splitChars={[',', ';', ' ']} maxTags={5} />
          <Group justify="flex-end">
            <Button leftSection={<IconTestPipe size={16} />} disabled={!testTo.length} loading={test.isPending} onClick={() => test.mutate(undefined)}>
              Send test
            </Button>
          </Group>
        </Stack>
      </Modal>
      <Modal opened={schedOpen} onClose={() => setSchedOpen(false)} title="Schedule">
        <Stack>
          <TextInput type="datetime-local" label="Send at (your local time)" value={when} onChange={(e) => setWhen(e.target.value)} />
          <Group justify="flex-end">
            <Button disabled={!when || new Date(when) <= new Date()} loading={send.isPending} onClick={() => send.mutate(new Date(when).toISOString())}>
              Schedule
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  )
}
