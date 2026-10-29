import {
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Checkbox,
  Code,
  CopyButton,
  Grid,
  Group,
  List,
  Modal,
  NavLink,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  TagsInput,
  Text,
  TextInput,
  ThemeIcon,
  Title,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import { IconCheck, IconCode, IconCopy, IconMail, IconPlus, IconTrash, IconWorldCheck, IconX } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { PageHeader } from '../components/common'
import { DataTable, InfoTip, Stat } from '../components/ui'
import { useApiMutation, useBrands, useUsers } from '../hooks'
import { LEAD_SOURCES } from '../labels'

interface Site {
  id: number
  key: string
  name: string
  domains: string[]
  brand_id: number | null
  owner_id: number | null
  lead_source: string
  track_utm: boolean
  track_params: boolean
  capture_forms: boolean
  require_consent: boolean
  respect_dnt: boolean
  active: boolean
  snippet: string
  script_url: string
  last_hit_at: string | null
  last_hit_url: string | null
}

interface Overview {
  days: number
  visitors: number
  identified: number
  page_views: number
  sessions: number
  events: number
  top_pages: { url: string; views: number }[]
  top_events: { name: string; count: number }[]
  top_sources: { source: string; visitors: number }[]
  recent_contacts: { id: number; name: string; email: string; last_seen: string; page_views: number; source: string }[]
  last_hit_at: string | null
  last_hit_url: string | null
}

interface Check {
  results: { url: string; status: number | null; found: boolean; message: string }[]
  last_hit_at: string | null
  last_hit_url: string | null
  domains_ok: boolean
}

const SOURCES = ['website_contact', 'download', 'trial', 'newsletter', 'quote_request', 'direct']
const when = (d: string | null) => (d ? new Date(d).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—')
const path = (u: string) => {
  try {
    const x = new URL(u)
    return x.pathname + x.search
  } catch {
    return u
  }
}

const IDENTIFY = `<script>
  window.mhcrm = window.mhcrm || []
  // after sign-up, sign-in or any step where you know the visitor
  mhcrm.push(['identify', {
    email: 'jane@example.com',      // required
    first_name: 'Jane',
    last_name: 'Doe',
    company: 'Example Corp',
    job_title: 'IT Operations Manager',
    phone: '+33 1 23 45 67 89',
  }])
</script>`

const TRACK = `<script>
  window.mhcrm = window.mhcrm || []
  // any action worth knowing about, with optional details
  mhcrm.push(['track', 'Downloaded datasheet', { product: 'Hardware Sentry' }])
  mhcrm.push(['track', 'Started trial', { edition: 'Enterprise' }])
</script>`

const CONSENT = `<script>
  window.mhcrm = window.mhcrm || []
  // call from your cookie banner
  mhcrm.push(['consent', true])   // accepted: tracking starts
  mhcrm.push(['consent', false])  // refused or withdrawn: the visitor is forgotten
</script>`

function CodeBox({ code, children }: { code: string; children?: ReactNode }) {
  return (
    <Box bg="var(--mantine-color-default-hover)" p="sm" style={{ borderRadius: 8 }}>
      <Code block bg="transparent" style={{ whiteSpace: 'pre', overflowX: 'auto', fontSize: 12.5 }}>
        {code}
      </Code>
      <Group gap="xs" mt="xs">
        <CopyButton value={code}>
          {({ copied, copy }) => (
            <Button size="xs" variant="default" leftSection={copied ? <IconCheck size={14} /> : <IconCopy size={14} />} onClick={copy}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
          )}
        </CopyButton>
        {children}
      </Group>
    </Box>
  )
}

function Step({ id, n, title, children, done }: { id: string; n?: number; title: string; children: ReactNode; done?: boolean }) {
  return (
    <Box id={id} style={{ scrollMarginTop: 80 }}>
      <Group gap="sm" mb="xs" wrap="nowrap">
        {n !== undefined && (
          <ThemeIcon radius="xl" size={26} color={done ? 'green' : 'dark'}>
            {done ? <IconCheck size={14} /> : <Text size="xs" fw={700}>{n}</Text>}
          </ThemeIcon>
        )}
        <Title order={4}>{title}</Title>
      </Group>
      <Box pl={n !== undefined ? 38 : 0}>{children}</Box>
    </Box>
  )
}

function NewSite({ opened, onClose, onCreated }: { opened: boolean; onClose: () => void; onCreated: (s: Site) => void }) {
  const [name, setName] = useState('')
  const [domains, setDomains] = useState<string[]>([])
  const create = useApiMutation(() => api<Site>('/tracking/sites', { method: 'POST', body: { name, domains } }), {
    invalidate: [['tracking-sites']],
    success: 'Website added',
    onSuccess: (s) => {
      setName('')
      setDomains([])
      onCreated(s)
    },
  })
  return (
    <Modal opened={opened} onClose={onClose} title="Add a website">
      <Stack>
        <TextInput label="Name" placeholder="metricshub.com" required value={name} onChange={(e) => setName(e.target.value)} />
        <TagsInput label="Domains" description="Press Enter after each. Subdomains are included." placeholder="metricshub.com" value={domains} onChange={setDomains} />
        <Group justify="flex-end">
          <Button loading={create.isPending} disabled={!name.trim()} onClick={() => create.mutate(undefined)}>
            Create tracking code
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function Statistics({ site }: { site: Site }) {
  const [days, setDays] = useState('30')
  const { data } = useQuery({ queryKey: ['tracking-overview', site.id, days], queryFn: () => api<Overview>(`/tracking/sites/${site.id}/overview`, { params: { days } }) })
  return (
    <Stack>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          Last hit: {data?.last_hit_at ? `${when(data.last_hit_at)} on ${data.last_hit_url ? path(data.last_hit_url) : '—'}` : 'nothing received yet'}
        </Text>
        <SegmentedControl size="xs" value={days} onChange={setDays} data={[{ value: '7', label: '7 days' }, { value: '30', label: '30 days' }, { value: '90', label: '90 days' }]} />
      </Group>
      {data && (
        <>
          <SimpleGrid cols={{ base: 2, md: 5 }}>
            <Stat label="Visitors" value={data.visitors} info="Browsers seen on the site in the period. One person on two devices counts twice until identified." />
            <Stat label="Identified" value={data.identified} hint={data.visitors ? `${Math.round((100 * data.identified) / data.visitors)}% of visitors` : undefined} info="Visitors linked to a contact: they filled in a form with their email, or the site identified them." />
            <Stat label="Page views" value={data.page_views} />
            <Stat label="Sessions" value={data.sessions} info={`Visits: a session ends after 30 minutes without activity.`} />
            <Stat label="Custom events" value={data.events} info="Actions the site reports with mhcrm.track (downloads, sign-ups…)." />
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, lg: 3 }}>
            <Card withBorder>
              <Title order={6} mb="xs">Top pages</Title>
              <DataTable rows={data.top_pages} minWidth={0} maxHeight={320} initial="v" empty="No page views yet." cols={[
                { key: 'u', label: 'Page', render: (r) => <Text size="xs" style={{ overflowWrap: 'anywhere' }}>{path(r.url)}</Text>, sort: (r) => r.url },
                { key: 'v', label: 'Views', align: 'right', render: (r) => r.views, sort: (r) => r.views },
              ]} />
            </Card>
            <Card withBorder>
              <Group gap={6} mb="xs">
                <Title order={6}>Where visitors come from</Title>
                <InfoTip info="Source / medium of each visitor's first visit: campaign (utm) parameters first, otherwise the referring site — organic for search engines, social for social networks, referral for other sites, direct when there is none." />
              </Group>
              <DataTable rows={data.top_sources} minWidth={0} maxHeight={320} initial="n" empty="No visitors yet." cols={[
                { key: 's', label: 'Source / medium', render: (r) => r.source, sort: (r) => r.source },
                { key: 'n', label: 'Visitors', align: 'right', render: (r) => r.visitors, sort: (r) => r.visitors },
              ]} />
            </Card>
            <Card withBorder>
              <Title order={6} mb="xs">Custom events</Title>
              <DataTable rows={data.top_events} minWidth={0} maxHeight={320} initial="c" empty="No custom events yet." cols={[
                { key: 'n', label: 'Event', render: (r) => r.name, sort: (r) => r.name },
                { key: 'c', label: 'Count', align: 'right', render: (r) => r.count, sort: (r) => r.count },
              ]} />
            </Card>
          </SimpleGrid>
          <Card withBorder>
            <Title order={6} mb="xs">Recently seen contacts</Title>
            <DataTable rows={data.recent_contacts} maxHeight={360} empty="No identified visitor yet." cols={[
              { key: 'n', label: 'Contact', render: (r) => <Anchor component={Link} to={`/contacts/${r.id}`} size="sm">{r.name}</Anchor>, sort: (r) => r.name },
              { key: 'e', label: 'Email', render: (r) => r.email, sort: (r) => r.email },
              { key: 's', label: 'First came from', render: (r) => r.source, sort: (r) => r.source },
              { key: 'p', label: 'Page views', align: 'right', render: (r) => r.page_views, sort: (r) => r.page_views },
              { key: 'l', label: 'Last seen', render: (r) => when(r.last_seen), sort: (r) => r.last_seen },
            ]} />
          </Card>
        </>
      )}
    </Stack>
  )
}

const SECTIONS = [
  { id: 'code', label: 'Add the tracking code', n: 1 },
  { id: 'domains', label: 'Add your domains', n: 2 },
  { id: 'contacts', label: 'Create and update contacts' },
  { id: 'events', label: 'Track custom events' },
  { id: 'privacy', label: 'Privacy and consent' },
  { id: 'stats', label: 'Visitor statistics' },
]

/** Admin page: the tracking code for each website, its settings, how to use it, and what it collected. */
export default function WebsiteTracking() {
  const { isAdmin } = useAuth()
  const { data: sites } = useQuery({ queryKey: ['tracking-sites'], queryFn: () => api<Site[]>('/tracking/sites'), enabled: isAdmin })
  const { data: users } = useUsers()
  const { data: brands } = useBrands()
  const [siteId, setSiteId] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)
  const [domains, setDomains] = useState<string[]>([])
  const [check, setCheck] = useState<Check | null>(null)
  const site = sites?.find((s) => s.id === siteId) ?? sites?.[0]
  useEffect(() => {
    setDomains(site?.domains ?? [])
    setCheck(null)
  }, [site?.id, site?.domains.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = useApiMutation((body: Partial<Site>) => api<Site>(`/tracking/sites/${site!.id}`, { method: 'PATCH', body }), {
    invalidate: [['tracking-sites']],
    success: 'Saved',
  })
  const runCheck = useApiMutation(() => api<Check>(`/tracking/sites/${site!.id}/check`, { method: 'POST' }), { onSuccess: setCheck })
  const remove = useApiMutation(() => api(`/tracking/sites/${site!.id}`, { method: 'DELETE' }), {
    invalidate: [['tracking-sites']],
    success: 'Website removed',
    onSuccess: () => setSiteId(null),
  })

  if (!isAdmin) return <Navigate to="/" replace />
  const header = (
    <PageHeader
      title="Website tracking"
      subtitle="Bring in leads from your websites, see the pages they visit and where they came from"
      actions={
        <Button variant="default" leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
          Add a website
        </Button>
      }
    />
  )
  const modal = <NewSite opened={adding} onClose={() => setAdding(false)} onCreated={(s) => { setAdding(false); setSiteId(s.id) }} />
  if (!sites) return header
  if (!site)
    return (
      <>
        {header}
        {modal}
        <Card withBorder p="xl">
          <Stack align="flex-start" maw={640}>
            <ThemeIcon size={44} variant="light"><IconCode size={24} /></ThemeIcon>
            <Title order={3}>Track your website</Title>
            <Text>
              Add one line to your website and the CRM receives the pages visitors view, the forms they fill in (creating or updating the contact) and where they
              came from: campaign, search engine, social network or referring site.
            </Text>
            <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>Add a website</Button>
          </Stack>
        </Card>
      </>
    )

  const set = (patch: Partial<Site>) => save.mutate(patch)
  const domainsChanged = domains.join(',') !== site.domains.join(',')
  const developerMail = `mailto:?subject=${encodeURIComponent(`CRM tracking code for ${site.name}`)}&body=${encodeURIComponent(
    `Hi,\n\nPlease add this line to every page of ${site.name}, just before </head>:\n\n${site.snippet}\n\nTo identify visitors (after a sign-up, for example) or record actions, see:\n\n${IDENTIFY}\n\n${TRACK}\n\nThanks!`,
  )}`
  const live = !!site.last_hit_at

  return (
    <>
      {header}
      {modal}
      {sites.length > 1 && (
        <Select mb="md" w={320} data={sites.map((s) => ({ value: String(s.id), label: s.name + (s.active ? '' : ' (off)') }))} value={String(site.id)} onChange={(v) => setSiteId(Number(v))} allowDeselect={false} aria-label="Website" />
      )}
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, md: 3 }}>
          <Card withBorder p="xs" style={{ position: 'sticky', top: 76 }}>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600} px="sm" pt={4} pb={6}>
              {site.name}
            </Text>
            {SECTIONS.map((s) => (
              <NavLink
                key={s.id}
                href={`#${s.id}`}
                label={s.label}
                onClick={(e) => {
                  e.preventDefault()
                  document.getElementById(s.id)?.scrollIntoView({ behavior: 'smooth' })
                }}
                leftSection={s.n ? <ThemeIcon radius="xl" size={20} color={(s.n === 1 ? live : site.domains.length > 0) ? 'green' : 'dark'}><Text size="10px" fw={700}>{s.n}</Text></ThemeIcon> : undefined}
              />
            ))}
            <Group px="sm" pt="sm" pb={4} gap={6}>
              <Badge color={!site.active ? 'gray' : live ? 'green' : 'orange'} variant="light">
                {!site.active ? 'Turned off' : live ? 'Receiving data' : 'Waiting for the first visit'}
              </Badge>
            </Group>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 9 }}>
          <Stack gap={36}>
            <Title order={3}>To bring in leads from your website and see what they do, complete steps 1 and 2</Title>

            <Step id="code" n={1} title="Add the tracking code to your website" done={live}>
              <Text size="sm" mb="sm">
                Copy this line and paste it before the closing <Code>{'</head>'}</Code> tag of every page you want to track (or once in your site's template or tag manager).
              </Text>
              <CodeBox code={site.snippet}>
                <Button size="xs" variant="default" component="a" href={developerMail} leftSection={<IconMail size={14} />}>
                  Send this to a developer
                </Button>
                <Button size="xs" variant="default" leftSection={<IconWorldCheck size={14} />} loading={runCheck.isPending} disabled={!site.domains.length} onClick={() => runCheck.mutate(undefined)}>
                  Check website integration
                </Button>
              </CodeBox>
              {check && (
                <Alert mt="sm" variant="light" color={check.results.some((r) => r.found) || check.last_hit_at ? 'green' : 'orange'} title="Integration check">
                  <List size="sm" spacing={4}>
                    {check.results.map((r) => (
                      <List.Item key={r.url} icon={r.found ? <IconCheck size={14} color="var(--mantine-color-green-6)" /> : <IconX size={14} color="var(--mantine-color-orange-6)" />}>
                        {r.url}: {r.message}
                      </List.Item>
                    ))}
                  </List>
                  <Text size="sm" mt={6}>
                    {check.last_hit_at ? `Last page view received ${when(check.last_hit_at)} from ${check.last_hit_url}.` : 'No page view received yet: open your website once the code is in place.'}
                  </Text>
                </Alert>
              )}
              <Stack gap="sm" mt="md">
                <Checkbox
                  checked={site.track_utm}
                  onChange={(e) => set({ track_utm: e.currentTarget.checked })}
                  label="Track the contact's source, medium and campaign"
                  description="From utm_source, utm_medium and utm_campaign in the address, or the referring site. Contacts get their original and latest source."
                />
                <Checkbox
                  ml="xl"
                  checked={site.track_params}
                  onChange={(e) => set({ track_params: e.currentTarget.checked })}
                  label="Track other URL parameters"
                  description="Keeps utm_term, utm_content and ad click ids (gclid, msclkid, fbclid, li_fat_id) with the visit."
                />
                <Checkbox
                  checked={site.capture_forms}
                  onChange={(e) => set({ capture_forms: e.currentTarget.checked })}
                  label="Create and update contacts from website forms"
                  description="When a visitor submits a form with an email field, the contact is created or completed (name, company, phone, job title). Other fields are not sent; add data-mhcrm-ignore to a form to skip it."
                />
              </Stack>
            </Step>

            <Step id="domains" n={2} title="Add your domains" done={site.domains.length > 0}>
              <Text size="sm" mb="sm">
                The CRM only accepts data sent from these domains and their subdomains (<Code>metricshub.com</Code> also covers <Code>www.metricshub.com</Code> and <Code>docs.metricshub.com</Code>).
              </Text>
              <Group align="flex-end">
                <TagsInput w={420} placeholder="metricshub.com, then Enter" value={domains} onChange={setDomains} aria-label="Domains" />
                <Button disabled={!domainsChanged} loading={save.isPending} onClick={() => set({ domains })}>
                  Save domains
                </Button>
              </Group>
              {!site.domains.length && (
                <Text size="sm" c="orange" mt="xs">
                  Nothing is recorded until a domain is added.
                </Text>
              )}
            </Step>

            <Step id="contacts" title="Create and update contacts">
              <Text size="sm" mb="sm">
                Forms are captured automatically (see step 1). To identify visitors elsewhere, for example after a sign-in or a trial sign-up, call <Code>identify</Code> with their email. Earlier visits from
                the same browser are added to the contact.
              </Text>
              <CodeBox code={IDENTIFY} />
              <SimpleGrid cols={{ base: 1, sm: 3 }} mt="md">
                <Select
                  label="Source of new contacts"
                  data={SOURCES.map((v) => ({ value: v, label: LEAD_SOURCES[v] ?? v }))}
                  value={site.lead_source}
                  onChange={(v) => v && set({ lead_source: v })}
                  allowDeselect={false}
                />
                <Select label="Owner of new contacts" placeholder="Nobody (or the account's owner)" data={(users ?? []).map((u) => ({ value: String(u.id), label: u.full_name }))} value={site.owner_id ? String(site.owner_id) : null} onChange={(v) => set({ owner_id: v ? Number(v) : null })} clearable searchable />
                <Select label="Brand interest" placeholder="None" data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))} value={site.brand_id ? String(site.brand_id) : null} onChange={(v) => set({ brand_id: v ? Number(v) : null })} clearable />
              </SimpleGrid>
            </Step>

            <Step id="events" title="Track custom events">
              <Text size="sm" mb="sm">
                Record actions that matter, such as downloads, trial starts or demo requests. They show on the contact's website activity, and in the statistics below.
              </Text>
              <CodeBox code={TRACK} />
            </Step>

            <Step id="privacy" title="Privacy and consent">
              <Stack gap="sm">
                <Text size="sm">
                  The code sets two first-party cookies on your website: a visitor id (13 months) and a session id (30 minutes). Page addresses are stored without their query string, IP addresses are
                  not stored, and visits are deleted after 13 months (anonymous visitors too).
                </Text>
                <Switch
                  checked={site.require_consent}
                  onChange={(e) => set({ require_consent: e.currentTarget.checked })}
                  label="Wait for the visitor's consent"
                  description="Nothing is recorded and no cookie is set until your cookie banner calls consent. Recommended for visitors in the EU (GDPR and ePrivacy)."
                />
                {site.require_consent && <CodeBox code={CONSENT} />}
                <Switch checked={site.respect_dnt} onChange={(e) => set({ respect_dnt: e.currentTarget.checked })} label="Respect Do Not Track and Global Privacy Control" description="Browsers with this setting are never tracked." />
              </Stack>
            </Step>

            <Step id="stats" title="Visitor statistics">
              <Statistics site={site} />
            </Step>

            <Card withBorder>
              <Group justify="space-between">
                <div>
                  <Text fw={600}>Tracking for {site.name}</Text>
                  <Text size="sm" c="dimmed">
                    Turning it off stops recording at once; the code can stay on the website.
                  </Text>
                </div>
                <Group>
                  <Switch checked={site.active} onChange={(e) => set({ active: e.currentTarget.checked })} label={site.active ? 'On' : 'Off'} />
                  <Button
                    color="red"
                    variant="light"
                    leftSection={<IconTrash size={16} />}
                    onClick={() =>
                      modals.openConfirmModal({
                        title: `Remove ${site.name}?`,
                        children: <Text size="sm">Its tracking code stops working and its visits are deleted. Contacts and their timelines stay.</Text>,
                        labels: { confirm: 'Remove', cancel: 'Cancel' },
                        confirmProps: { color: 'red' },
                        onConfirm: () => remove.mutate(undefined),
                      })
                    }
                  >
                    Remove
                  </Button>
                </Group>
              </Group>
            </Card>
          </Stack>
        </Grid.Col>
      </Grid>
    </>
  )
}
