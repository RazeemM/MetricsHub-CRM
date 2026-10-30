import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Checkbox,
  Code,
  CopyButton,
  Group,
  NumberInput,
  PasswordInput,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Tabs,
  TagsInput,
  Text,
  Textarea,
  TextInput,
  Tooltip,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import { IconCheck, IconCopy, IconPlus, IconRefresh, IconTrash } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { PageHeader, Pager } from '../components/common'
import { useApiMutation, useBrands, useUsers } from '../hooks'
import { LEAD_SOURCES, fmtDate } from '../labels'
import { useLists } from './MailingLists'

export interface WebForm {
  id: number
  key: string
  name: string
  brand_id: number | null
  lead_source: string
  field_map: Record<string, string>
  owner_id: number | null
  list_id: number | null
  auth_mode: 'hmac' | 'token'
  allowed_origins: string[]
  honeypot_field: string | null
  redirect_url: string | null
  confirm_redirect_url: string | null
  confirm_subject: string | null
  confirm_body_html: string | null
  notify_owner: boolean
  rate_limit_per_hour: number
  active: boolean
  secret: string
  endpoint: string
  list_kind: 'list' | 'newsletter' | null
  submissions_30d: number
  last_submission_at: string | null
  created_at: string
}

interface Submission {
  id: number
  created_at: string
  status: 'accepted' | 'pending' | 'confirmed' | 'spam' | 'error'
  email: string | null
  contact_id: number | null
  contact_created: boolean
  data: Record<string, string>
  ip: string | null
  note: string | null
}

interface Meta {
  contact_fields: Record<string, string>
  endpoint_base: string
}

const FORM_SOURCES = ['website_contact', 'quote_request', 'trial', 'download', 'partner_signup', 'newsletter']
const STATUS_COLORS: Record<string, string> = { accepted: 'green', pending: 'yellow', confirmed: 'teal', spam: 'gray', error: 'red' }
const STATUS_LABELS: Record<string, string> = {
  accepted: 'Accepted',
  pending: 'Pending opt-in',
  confirmed: 'Confirmed',
  spam: 'Spam',
  error: 'Error',
}

const useMeta = () => useQuery({ queryKey: ['web-forms', 'meta'], queryFn: () => api<Meta>('/web-forms/meta'), staleTime: 300_000 })

export default function WebForms() {
  const nav = useNavigate()
  const { data } = useQuery({ queryKey: ['web-forms'], queryFn: () => api<WebForm[]>('/web-forms') })
  const { data: lists } = useLists()
  return (
    <>
      <PageHeader help="web-forms"
        title="Website forms"
        subtitle="Contact, quote, trial, download, partner and newsletter forms that create contacts in the CRM"
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={() => nav('/web-forms/new')}>
            New form
          </Button>
        }
      />
      <Card withBorder>
        {data?.length ? (
          <Table.ScrollContainer minWidth={760}>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Name</Table.Th>
                  <Table.Th>Key</Table.Th>
                  <Table.Th>Lead source</Table.Th>
                  <Table.Th>Adds to list</Table.Th>
                  <Table.Th ta="right">Last 30 days</Table.Th>
                  <Table.Th>Last submission</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.map((f) => (
                  <Table.Tr key={f.id} className="clickable-row" onClick={() => nav(`/web-forms/${f.id}`)}>
                    <Table.Td fw={500}>
                      {f.name}{' '}
                      {!f.active && (
                        <Badge size="xs" color="gray" variant="light">
                          off
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Code>{f.key}</Code>
                    </Table.Td>
                    <Table.Td>{LEAD_SOURCES[f.lead_source] ?? f.lead_source}</Table.Td>
                    <Table.Td>
                      {f.list_id ? lists?.find((l) => l.id === f.list_id)?.name : '—'}
                      {f.list_kind === 'newsletter' && (
                        <Badge ml={6} size="xs" variant="light" color="grape">
                          double opt-in
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td ta="right">{f.submissions_30d}</Table.Td>
                    <Table.Td>{fmtDate(f.last_submission_at)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        ) : (
          <Text size="sm" c="dimmed">
            No forms yet. Create one per website form; each gets its own address and secret.
          </Text>
        )}
      </Card>
    </>
  )
}

type Draft = Omit<WebForm, 'id' | 'secret' | 'endpoint' | 'list_kind' | 'submissions_30d' | 'last_submission_at' | 'created_at'>

const EMPTY: Draft = {
  key: '',
  name: '',
  brand_id: null,
  lead_source: 'website_contact',
  field_map: {},
  owner_id: null,
  list_id: null,
  auth_mode: 'hmac',
  allowed_origins: [],
  honeypot_field: 'website',
  redirect_url: null,
  confirm_redirect_url: null,
  confirm_subject: null,
  confirm_body_html: null,
  notify_owner: true,
  rate_limit_per_hour: 20,
  active: true,
}

const slug = (s: string) =>
  s
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)

function FieldMap({ value, onChange, fields }: { value: Record<string, string>; onChange: (v: Record<string, string>) => void; fields: Record<string, string> }) {
  const [rows, setRowsState] = useState<[string, string][]>(() => Object.entries(value))
  const setRows = (next: [string, string][]) => {
    setRowsState(next)
    onChange(Object.fromEntries(next.filter(([k, t]) => k.trim() && t)))
  }
  const options = Object.entries(fields).map(([value, label]) => ({ value, label }))
  return (
    <Stack gap="xs">
      {rows.map(([k, t], i) => (
        <Group key={i} gap="xs" wrap="nowrap">
          <TextInput placeholder="Website field name, e.g. your-email" value={k} onChange={(e) => setRows(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))} style={{ flex: 1 }} />
          <Text c="dimmed">→</Text>
          <Select data={options} value={t} onChange={(v) => setRows(rows.map((r, j) => (j === i ? [r[0], v ?? ''] : r)))} style={{ flex: 1 }} placeholder="Contact field" />
          <ActionIcon variant="subtle" color="red" aria-label="Remove" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
            <IconTrash size={16} />
          </ActionIcon>
        </Group>
      ))}
      <Group>
        <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setRows([...rows, ['', '']])}>
          Add field
        </Button>
      </Group>
    </Stack>
  )
}

function Settings({ form, onSaved }: { form?: WebForm; onSaved: (f: WebForm) => void }) {
  const { data: brands } = useBrands()
  const { data: users } = useUsers()
  const { data: lists } = useLists()
  const { data: meta } = useMeta()
  const [d, setD] = useState<Draft>(() => (form ? { ...EMPTY, ...form } : EMPTY))
  const [keyTouched, setKeyTouched] = useState(!!form)
  const set = (patch: Partial<Draft>) => setD((x) => ({ ...x, ...patch }))
  const list = lists?.find((l) => l.id === d.list_id)
  const save = useApiMutation(() => api<WebForm>(form ? `/web-forms/${form.id}` : '/web-forms', { method: form ? 'PUT' : 'POST', body: d }), {
    invalidate: [['web-forms']],
    success: form ? 'Form saved' : 'Form created',
    onSuccess: onSaved,
  })
  return (
    <Stack>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <TextInput
          label="Name"
          description="As shown in the CRM and on contacts' timelines"
          required
          value={d.name}
          onChange={(e) => set({ name: e.target.value, ...(keyTouched ? {} : { key: slug(e.target.value) }) })}
          data-autofocus
        />
        <TextInput
          label="Key"
          description={`${meta?.endpoint_base ?? '/api/public/forms/'}${d.key || '…'}`}
          required
          value={d.key}
          onChange={(e) => {
            setKeyTouched(true)
            set({ key: e.target.value.toLowerCase() })
          }}
        />
        <Select
          label="Lead source"
          description="Set on contacts this form creates"
          data={FORM_SOURCES.map((v) => ({ value: v, label: LEAD_SOURCES[v] }))}
          value={d.lead_source}
          onChange={(v) => set({ lead_source: v ?? 'website_contact' })}
        />
        <Select label="Brand" placeholder="None" clearable data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))} value={d.brand_id ? String(d.brand_id) : null} onChange={(v) => set({ brand_id: v ? Number(v) : null })} />
        <Select
          label="Owner of new contacts"
          description="Contacts that already have an owner keep theirs"
          placeholder="Account owner, else nobody"
          clearable
          searchable
          data={(users ?? []).filter((u) => u.is_active).map((u) => ({ value: String(u.id), label: u.full_name }))}
          value={d.owner_id ? String(d.owner_id) : null}
          onChange={(v) => set({ owner_id: v ? Number(v) : null })}
        />
        <Select
          label="Add to mailing list"
          description={list?.kind === 'newsletter' ? 'Newsletter: people get a confirmation email and join once they confirm' : 'Optional'}
          placeholder="None"
          clearable
          data={(lists ?? []).map((l) => ({ value: String(l.id), label: `${l.name}${l.kind === 'newsletter' ? ' (newsletter)' : ''}` }))}
          value={d.list_id ? String(d.list_id) : null}
          onChange={(v) => set({ list_id: v ? Number(v) : null })}
        />
      </SimpleGrid>

      <Card withBorder>
        <Text fw={600} mb={4}>
          Field mapping
        </Text>
        <Text size="xs" c="dimmed" mb="sm">
          Website fields named like <Code>email</Code>, <Code>first_name</Code>, <Code>name</Code>, <Code>company</Code>, <Code>phone</Code>, <Code>message</Code> work without a mapping. Every submitted field is copied to
          the contact's timeline. Map a checkbox to <i>Marketing consent</i> to add people to the list only when they tick it.
        </Text>
        {meta && <FieldMap value={d.field_map} onChange={(field_map) => set({ field_map })} fields={meta.contact_fields} />}
      </Card>

      <Card withBorder>
        <Text fw={600} mb="sm">
          Security
        </Text>
        <Stack>
          <SegmentedControl
            value={d.auth_mode}
            onChange={(v) => set({ auth_mode: v as 'hmac' | 'token' })}
            data={[
              { value: 'hmac', label: 'Signed by the website server (HMAC)' },
              { value: 'token', label: 'Posted from the browser (token)' },
            ]}
          />
          <Text size="xs" c="dimmed">
            {d.auth_mode === 'hmac'
              ? 'Recommended: the website backend signs each request with the secret, which never reaches visitors.'
              : 'The token is in the page, so anyone can read it: restrict the allowed websites; the honeypot and rate limit stop most bots.'}
          </Text>
          <TagsInput
            label="Allowed websites"
            description="Origins that may post from a browser, e.g. https://www.metricshub.com (empty = any)"
            value={d.allowed_origins}
            onChange={(allowed_origins) => set({ allowed_origins })}
          />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput
              label="Honeypot field"
              description="A hidden field people never fill; bots do. Submissions with it filled are dropped."
              value={d.honeypot_field ?? ''}
              onChange={(e) => set({ honeypot_field: e.target.value || null })}
            />
            <NumberInput label="Submissions per hour per visitor" min={0} max={10000} value={d.rate_limit_per_hour} onChange={(v) => set({ rate_limit_per_hour: Number(v) || 0 })} />
          </SimpleGrid>
        </Stack>
      </Card>

      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <TextInput label="Thank-you page" description="Where a plain HTML form post is sent afterwards" placeholder="https://www.metricshub.com/thank-you" value={d.redirect_url ?? ''} onChange={(e) => set({ redirect_url: e.target.value || null })} />
        {list?.kind === 'newsletter' && (
          <TextInput label="Page after confirming" description="Where the confirmation link leads (optional)" placeholder="https://www.metricshub.com/subscribed" value={d.confirm_redirect_url ?? ''} onChange={(e) => set({ confirm_redirect_url: e.target.value || null })} />
        )}
      </SimpleGrid>

      {list?.kind === 'newsletter' && (
        <Card withBorder>
          <Text fw={600} mb={4}>
            Confirmation email (double opt-in)
          </Text>
          <Text size="xs" c="dimmed" mb="sm">
            Leave empty for the default. Merge fields: <Code>{'{first_name}'}</Code> <Code>{'{list_name}'}</Code> <Code>{'{brand}'}</Code> <Code>{'{confirm_url}'}</Code> <Code>{'{postal_address}'}</Code>. Sent through the
            campaign mail server.
          </Text>
          <Stack>
            <TextInput label="Subject" placeholder="Please confirm your subscription to {list_name}" value={d.confirm_subject ?? ''} onChange={(e) => set({ confirm_subject: e.target.value || null })} />
            <Textarea label="HTML" autosize minRows={3} maxRows={14} styles={{ input: { fontFamily: 'monospace', fontSize: 12 } }} value={d.confirm_body_html ?? ''} onChange={(e) => set({ confirm_body_html: e.target.value || null })} />
          </Stack>
        </Card>
      )}

      <Group justify="space-between">
        <Group>
          <Checkbox label="Notify the contact owner (bell)" checked={d.notify_owner} onChange={(e) => set({ notify_owner: e.currentTarget.checked })} />
          <Switch label="Accept submissions" checked={d.active} onChange={(e) => set({ active: e.currentTarget.checked })} />
        </Group>
        <Button loading={save.isPending} disabled={!d.name.trim() || d.key.length < 2} onClick={() => save.mutate(undefined)}>
          {form ? 'Save' : 'Create form'}
        </Button>
      </Group>
    </Stack>
  )
}

function Copy({ value, label = 'Copy' }: { value: string; label?: string }) {
  return (
    <CopyButton value={value}>
      {({ copied, copy }) => (
        <Tooltip label={copied ? 'Copied' : label}>
          <ActionIcon variant="subtle" onClick={copy} aria-label={label}>
            {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
          </ActionIcon>
        </Tooltip>
      )}
    </CopyButton>
  )
}

function Snippet({ title, code, children }: { title: string; code: string; children?: ReactNode }) {
  return (
    <Card withBorder>
      <Group justify="space-between" mb={4}>
        <Text fw={600}>{title}</Text>
        <Copy value={code} />
      </Group>
      {children}
      <Code block style={{ whiteSpace: 'pre', overflowX: 'auto', fontSize: 12 }}>
        {code}
      </Code>
    </Card>
  )
}

function websiteFields(form: WebForm): string[] {
  const keys = Object.keys(form.field_map)
  const targets = Object.values(form.field_map)
  const out = [...keys]
  if (!targets.includes('email')) out.unshift('email')
  if (form.list_kind !== 'newsletter' && !targets.includes('full_name') && !targets.includes('first_name')) out.push('name')
  if (form.list_kind !== 'newsletter' && !targets.includes('message')) out.push('message')
  return out
}

function WebsiteCode({ form }: { form: WebForm }) {
  const fields = websiteFields(form)
  const hp = form.honeypot_field
  const sample = Object.fromEntries(fields.map((f) => [f, form.field_map[f] === 'email' || f === 'email' ? 'jane@example.com' : form.field_map[f] === 'consent' ? 'yes' : 'Jane Example']))
  const json = JSON.stringify(sample)
  const inputs = fields
    .map((f) => {
      const t = form.field_map[f] ?? (f === 'email' ? 'email' : f)
      if (t === 'consent') return `  <label><input type="checkbox" name="${f}" value="yes"> Send me the newsletter</label>`
      if (t === 'message') return `  <textarea name="${f}" placeholder="Message"></textarea>`
      return `  <input ${t === 'email' ? 'type="email" required' : 'type="text"'} name="${f}" placeholder="${t.replace('_', ' ')}">`
    })
    .join('\n')
  const honeypot = hp ? `\n  <!-- honeypot: hidden from people, bots fill it -->\n  <input type="text" name="${hp}" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px" aria-hidden="true">` : ''
  const html = `<form action="${form.endpoint}" method="post">
  <input type="hidden" name="_token" value="${form.secret}">
${inputs}${honeypot}
  <button type="submit">Send</button>
</form>`
  const js = `<script>
document.querySelector('#crm-form').addEventListener('submit', async (e) => {
  e.preventDefault()
  const fields = Object.fromEntries(new FormData(e.target))
  fields._page = location.href
  const res = await fetch('${form.endpoint}', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CRM-Form-Token': '${form.secret}' },
    body: JSON.stringify(fields),
  })
  const r = await res.json()
  e.target.innerHTML = r.ok
    ? (r.status === 'pending_confirmation' ? 'Check your inbox to confirm.' : 'Thank you, we will be in touch.')
    : 'Sorry: ' + r.detail
})
</script>`
  const node = `// Node.js (website backend): forward the visitor's form fields, signed with the secret
import crypto from 'node:crypto'

const SECRET = process.env.CRM_FORM_SECRET // ${form.key}: keep it on the server
export async function sendToCrm(fields, visitorIp) {
  const body = JSON.stringify(fields)
  const ts = Math.floor(Date.now() / 1000).toString()
  const sig = crypto.createHmac('sha256', SECRET).update(ts + '.' + body).digest('hex')
  const res = await fetch('${form.endpoint}', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CRM-Timestamp': ts, 'X-CRM-Signature': 'sha256=' + sig },
    body,
  })
  return res.json() // { ok: true, status: 'accepted' | 'pending_confirmation' }
}`
  const php = `<?php // PHP (e.g. WordPress): forward the form fields, signed with the secret
$body = json_encode($fields);
$ts = (string) time();
$sig = hash_hmac('sha256', $ts . '.' . $body, getenv('CRM_FORM_SECRET'));
$res = wp_remote_post('${form.endpoint}', [
  'headers' => ['Content-Type' => 'application/json', 'X-CRM-Timestamp' => $ts, 'X-CRM-Signature' => 'sha256=' . $sig],
  'body' => $body,
]);`
  const curl =
    form.auth_mode === 'hmac'
      ? `SECRET='${form.secret}'
BODY='${json}'
TS=$(date +%s)
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')
curl -i '${form.endpoint}' -H 'Content-Type: application/json' \\
  -H "X-CRM-Timestamp: $TS" -H "X-CRM-Signature: sha256=$SIG" -d "$BODY"`
      : `curl -i '${form.endpoint}' -H 'Content-Type: application/json' \\
  -H 'X-CRM-Form-Token: ${form.secret}' -d '${json}'`
  return (
    <Stack>
      {form.auth_mode === 'hmac' ? (
        <>
          <Alert variant="light">
            This form expects requests signed by your website's server: <Code>X-CRM-Timestamp</Code> (Unix seconds) and <Code>X-CRM-Signature: sha256=HMAC_SHA256(secret, timestamp + "." + body)</Code>. Requests older than 5
            minutes are refused.
          </Alert>
          <Snippet title="Node.js" code={node} />
          <Snippet title="PHP / WordPress" code={php} />
        </>
      ) : (
        <>
          <Snippet title="Plain HTML form" code={html}>
            <Text size="xs" c="dimmed" mb="xs">
              The browser posts the form and is sent to the thank-you page{form.redirect_url ? '' : ' (set one in the settings, otherwise a simple CRM page is shown)'}.
            </Text>
          </Snippet>
          <Snippet title="JavaScript (stay on the page)" code={js}>
            <Text size="xs" c="dimmed" mb="xs">
              Give your form <Code>id="crm-form"</Code>. Keep the honeypot field{hp ? ` "${hp}"` : ''} in it.
            </Text>
          </Snippet>
        </>
      )}
      <Snippet title="Test with curl" code={curl} />
    </Stack>
  )
}

function Submissions({ form }: { form: WebForm }) {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<string | null>(null)
  const { data } = useQuery({
    queryKey: ['web-forms', form.id, 'submissions', page, status],
    queryFn: () => api<{ total: number; items: Submission[] }>(`/web-forms/${form.id}/submissions`, { params: { page, status: status ?? undefined, page_size: 50 } }),
  })
  return (
    <Card withBorder>
      <Select mb="sm" w={240} placeholder="All statuses" clearable data={Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }))} value={status} onChange={(v) => { setStatus(v); setPage(1) }} />
      <Table.ScrollContainer minWidth={760}>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>When</Table.Th>
              <Table.Th>Email</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Fields</Table.Th>
              <Table.Th>From</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data?.items.map((s) => (
              <Table.Tr key={s.id}>
                <Table.Td style={{ whiteSpace: 'nowrap' }}>{new Date(s.created_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}</Table.Td>
                <Table.Td>
                  {s.contact_id ? (
                    <Anchor component={Link} to={`/contacts/${s.contact_id}`} size="sm">
                      {s.email}
                    </Anchor>
                  ) : (
                    s.email ?? '—'
                  )}
                  {s.contact_created && (
                    <Badge ml={6} size="xs" variant="light">
                      new
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td>
                  <Badge size="sm" variant="light" color={STATUS_COLORS[s.status]}>
                    {STATUS_LABELS[s.status] ?? s.status}
                  </Badge>
                  {s.note && (
                    <Text size="xs" c="dimmed">
                      {s.note}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Text size="xs" lineClamp={3} maw={360}>
                    {Object.entries(s.data)
                      .filter(([k]) => !k.startsWith('_'))
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(' · ')}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="xs">{s.ip ?? 'CRM test'}</Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {data && !data.items.length && (
        <Text size="sm" c="dimmed">
          No submissions{status ? ' with this status' : ' yet'}.
        </Text>
      )}
      {data && <Pager page={page} total={data.total} pageSize={50} onChange={setPage} />}
    </Card>
  )
}

function TestSubmit({ form }: { form: WebForm }) {
  const fields = websiteFields(form)
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(fields.map((f) => [f, ''])))
  const [result, setResult] = useState<Submission | null>(null)
  const run = useApiMutation(() => api<Submission>(`/web-forms/${form.id}/test`, { method: 'POST', body: { fields: values } }), {
    invalidate: [['web-forms']],
    onSuccess: setResult,
  })
  return (
    <Card withBorder>
      <Text size="sm" c="dimmed" mb="sm">
        Processes a submission exactly as if the website had posted it (without the secret and rate limit): the contact is created or updated, and newsletter sign-ups get the real confirmation email.
      </Text>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        {fields.map((f) => (
          <TextInput key={f} label={f} value={values[f] ?? ''} onChange={(e) => setValues({ ...values, [f]: e.target.value })} />
        ))}
      </SimpleGrid>
      <Group justify="flex-end" mt="sm">
        <Button loading={run.isPending} onClick={() => run.mutate(undefined)}>
          Send test submission
        </Button>
      </Group>
      {result && (
        <Alert mt="sm" variant="light" color={STATUS_COLORS[result.status]} title={STATUS_LABELS[result.status]}>
          {result.note && <Text size="sm">{result.note}</Text>}
          {result.contact_id && (
            <Anchor component={Link} to={`/contacts/${result.contact_id}`} size="sm">
              Open the {result.contact_created ? 'new ' : ''}contact
            </Anchor>
          )}
        </Alert>
      )}
    </Card>
  )
}

export function WebFormDetail() {
  const params = useParams()
  const nav = useNavigate()
  const isNew = params.id === 'new'
  const id = Number(params.id)
  const { data: form } = useQuery({ queryKey: ['web-forms', id], queryFn: () => api<WebForm>(`/web-forms/${id}`), enabled: !isNew })
  const [tab, setTab] = useState<string | null>('settings')
  const rotate = useApiMutation(() => api<WebForm>(`/web-forms/${id}/rotate-secret`, { method: 'POST' }), { invalidate: [['web-forms']], success: 'New secret created: update the website' })
  const del = useApiMutation(() => api(`/web-forms/${id}`, { method: 'DELETE' }), { invalidate: [['web-forms']], success: 'Form deleted', onSuccess: () => nav('/web-forms') })

  if (isNew)
    return (
      <>
        <PageHeader title="New website form" />
        <Card withBorder>
          <Settings onSaved={(f) => nav(`/web-forms/${f.id}`, { replace: true })} />
        </Card>
      </>
    )
  if (!form) return null
  return (
    <>
      <PageHeader
        title={form.name}
        subtitle={
          <>
            {LEAD_SOURCES[form.lead_source] ?? form.lead_source} · {form.submissions_30d} submission{form.submissions_30d === 1 ? '' : 's'} in the last 30 days {!form.active && '· not accepting submissions'}
          </>
        }
        actions={
          <Button
            variant="subtle"
            color="red"
            leftSection={<IconTrash size={16} />}
            onClick={() =>
              modals.openConfirmModal({
                title: `Delete "${form.name}"?`,
                children: <Text size="sm">The website can no longer post to it. Contacts it created stay in the CRM; its submission log is deleted.</Text>,
                labels: { confirm: 'Delete', cancel: 'Cancel' },
                confirmProps: { color: 'red' },
                onConfirm: () => del.mutate(undefined),
              })
            }
          >
            Delete
          </Button>
        }
      />
      <Card withBorder mb="md">
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Endpoint" readOnly value={form.endpoint} rightSection={<Copy value={form.endpoint} />} />
          <Group align="flex-end" gap="xs" wrap="nowrap">
            <PasswordInput label={form.auth_mode === 'hmac' ? 'Signing secret' : 'Form token'} readOnly value={form.secret} style={{ flex: 1 }} />
            <Copy value={form.secret} label="Copy secret" />
            <Tooltip label="Create a new secret (the current one stops working)">
              <ActionIcon
                variant="subtle"
                aria-label="Rotate secret"
                onClick={() =>
                  modals.openConfirmModal({
                    title: 'Create a new secret?',
                    children: <Text size="sm">The website stops being able to post until it uses the new secret.</Text>,
                    labels: { confirm: 'Create new secret', cancel: 'Cancel' },
                    onConfirm: () => rotate.mutate(undefined),
                  })
                }
              >
                <IconRefresh size={16} />
              </ActionIcon>
            </Tooltip>
          </Group>
        </SimpleGrid>
      </Card>
      <Tabs value={tab} onChange={setTab} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="settings">Settings</Tabs.Tab>
          <Tabs.Tab value="code">Website code</Tabs.Tab>
          <Tabs.Tab value="submissions">Submissions</Tabs.Tab>
          <Tabs.Tab value="test">Test</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="settings">
          <Card withBorder>
            <Settings key={form.id} form={form} onSaved={() => undefined} />
          </Card>
        </Tabs.Panel>
        <Tabs.Panel value="code">
          <WebsiteCode form={form} />
        </Tabs.Panel>
        <Tabs.Panel value="submissions">
          <Submissions form={form} />
        </Tabs.Panel>
        <Tabs.Panel value="test">
          <TestSubmit form={form} />
        </Tabs.Panel>
      </Tabs>
    </>
  )
}
