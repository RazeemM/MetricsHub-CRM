import { Anchor, Badge, Card, Group, SimpleGrid, Stack, Text, Timeline, Title, Tooltip } from '@mantine/core'
import { IconClick, IconFileText, IconForms } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api'
import { Field } from './common'
import { InfoTip } from './ui'

interface Touch {
  source?: string
  medium?: string
  campaign?: string
  landing?: string
  referrer?: string
  [param: string]: string | undefined
}

interface WebActivityData {
  tracked: boolean
  first_seen: string | null
  last_seen: string | null
  sessions: number
  page_views: number
  browsers: number
  original: Touch | null
  latest: Touch | null
  top_pages: { url: string; views: number }[]
  events: { kind: 'page' | 'event' | 'identify'; name: string | null; url: string | null; props: Record<string, unknown>; at: string }[]
}

const when = (d: string | null) => (d ? new Date(d).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—')
const path = (u: string | null) => {
  if (!u) return ''
  try {
    const x = new URL(u)
    return x.pathname + x.search
  } catch {
    return u
  }
}

function TouchText({ t }: { t: Touch | null }) {
  if (!t?.source) return <Text size="sm">—</Text>
  const extra = Object.entries(t).filter(([k]) => !['source', 'medium', 'campaign', 'landing', 'referrer'].includes(k))
  return (
    <Tooltip
      multiline
      w={300}
      withArrow
      label={
        <>
          {t.landing && <div>Landed on {path(t.landing)}</div>}
          {t.referrer && <div>Referred by {t.referrer}</div>}
          {extra.map(([k, v]) => (
            <div key={k}>
              {k}: {v}
            </div>
          ))}
        </>
      }
      disabled={!t.landing && !t.referrer && !extra.length}
    >
      <Text size="sm">
        {t.source} / {t.medium}
        {t.campaign && (
          <Text span size="xs" c="dimmed">
            {' '}
            · {t.campaign}
          </Text>
        )}
      </Text>
    </Tooltip>
  )
}

const ICON = { page: IconFileText, event: IconClick, identify: IconForms }

/** Pages viewed and actions on the tracked websites, and where the contact came from. Hidden when never tracked. */
export function WebActivity({ contactId }: { contactId: number }) {
  const { data } = useQuery({ queryKey: ['contact-web', contactId], queryFn: () => api<WebActivityData>(`/contacts/${contactId}/web`) })
  const [all, setAll] = useState(false)
  if (!data?.tracked) return null
  const events = all ? data.events : data.events.slice(0, 12)
  return (
    <Card withBorder mt="md">
      <Group gap={6} mb="sm">
        <Title order={5}>Website activity</Title>
        <InfoTip info="From the CRM tracking code on your websites (Marketing → Website tracking). Visits made before the contact filled in a form on that browser are included." />
      </Group>
      <Stack gap="sm">
        <SimpleGrid cols={2}>
          <Field label="Original source">
            <TouchText t={data.original} />
          </Field>
          <Field label="Latest source">
            <TouchText t={data.latest} />
          </Field>
          <Field label="First seen">{when(data.first_seen)}</Field>
          <Field label="Last seen">{when(data.last_seen)}</Field>
          <Field label="Visits">{data.sessions}</Field>
          <Field label="Page views">{data.page_views}</Field>
        </SimpleGrid>
        {data.top_pages.length > 0 && (
          <div>
            <Text size="xs" c="dimmed" fw={600} tt="uppercase" mb={4}>
              Most viewed
            </Text>
            <Group gap={6}>
              {data.top_pages.map((p) => (
                <Badge key={p.url} variant="light" color="gray" tt="none">
                  {path(p.url)} · {p.views}
                </Badge>
              ))}
            </Group>
          </div>
        )}
        <Timeline bulletSize={20} lineWidth={2} mt={4}>
          {events.map((e, i) => {
            const Icon = ICON[e.kind]
            const title = e.kind === 'page' ? e.name || path(e.url) : e.kind === 'identify' ? e.name : e.name
            const props = Object.entries(e.props ?? {})
            return (
              <Timeline.Item key={i} bullet={<Icon size={12} />} color={e.kind === 'page' ? 'gray' : e.kind === 'identify' ? 'green' : 'violet'}>
                <Text size="sm" fw={e.kind === 'page' ? 400 : 600} lineClamp={1}>
                  {title}
                </Text>
                <Text size="xs" c="dimmed" lineClamp={1}>
                  {e.url && (
                    <Anchor href={e.url} target="_blank" rel="noreferrer" size="xs" c="dimmed">
                      {path(e.url)}
                    </Anchor>
                  )}
                  {props.length > 0 && ` · ${props.map(([k, v]) => `${k}: ${String(v)}`).join(', ')}`}
                </Text>
                <Text size="xs" c="dimmed">
                  {when(e.at)}
                </Text>
              </Timeline.Item>
            )
          })}
        </Timeline>
        {data.events.length > 12 && (
          <Anchor component="button" size="sm" onClick={() => setAll(!all)}>
            {all ? 'Show less' : `Show all ${data.events.length}`}
          </Anchor>
        )}
      </Stack>
    </Card>
  )
}
