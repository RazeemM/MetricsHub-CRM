import { Badge, Button, Card, FileButton, Grid, Group, Menu, ScrollArea, SegmentedControl, Stack, Text, Textarea, TextInput } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { IconBraces, IconUpload } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

export interface MailSettings {
  transactional: { enabled: boolean; backend: string; fixed_sender: string | null }
  bulk: { enabled: boolean; backend: string; fixed_sender: string | null }
  smtp: { host: string | null; port: number; security: string; username: string | null }
  from: string | null
  from_name: string | null
  rate_per_minute: number
  postal_address: string | null
  merge_fields: Record<string, string>
}

export const useMailSettings = () => useQuery({ queryKey: ['mail-settings'], queryFn: () => api<MailSettings>('/mail/settings'), staleTime: 60_000 })

export interface EmailContent {
  subject: string
  preheader: string | null
  body_html: string
}

/** Subject, preview text and HTML body with merge fields, plus a live preview rendered by the server. */
export function EmailEditor({ value, onChange, readOnly }: { value: EmailContent; onChange: (v: EmailContent) => void; readOnly?: boolean }) {
  const { data: settings } = useMailSettings()
  const [debounced] = useDebouncedValue(value, 400)
  const [preview, setPreview] = useState<{ subject: string; html: string } | null>(null)
  const [width, setWidth] = useState('desktop')
  const area = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    let cancelled = false
    api<{ subject: string; html: string }>('/email-templates/preview', { method: 'POST', body: debounced })
      .then((p) => !cancelled && setPreview(p))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [debounced])

  const insert = (field: string) => {
    const el = area.current
    const token = `{${field}}`
    if (!el) return onChange({ ...value, body_html: value.body_html + token })
    const { selectionStart: a, selectionEnd: b } = el
    onChange({ ...value, body_html: value.body_html.slice(0, a) + token + value.body_html.slice(b) })
    requestAnimationFrame(() => {
      el.focus()
      el.setSelectionRange(a + token.length, a + token.length)
    })
  }
  const loadFile = (f: File | null) => f && f.text().then((t) => onChange({ ...value, body_html: t }))

  return (
    <Grid>
      <Grid.Col span={{ base: 12, lg: 6 }}>
        <Stack gap="sm">
          <TextInput label="Subject" required value={value.subject} onChange={(e) => onChange({ ...value, subject: e.target.value })} readOnly={readOnly} />
          <TextInput
            label="Preview text"
            description="Shown next to the subject in most inboxes"
            value={value.preheader ?? ''}
            onChange={(e) => onChange({ ...value, preheader: e.target.value || null })}
            readOnly={readOnly}
          />
          <Group justify="space-between" align="flex-end">
            <Text size="sm" fw={500}>
              HTML content
            </Text>
            {!readOnly && (
              <Group gap="xs">
                <Menu shadow="md" width={280}>
                  <Menu.Target>
                    <Button size="xs" variant="light" leftSection={<IconBraces size={14} />}>
                      Insert field
                    </Button>
                  </Menu.Target>
                  <Menu.Dropdown>
                    {Object.entries(settings?.merge_fields ?? {}).map(([k, label]) => (
                      <Menu.Item key={k} onClick={() => insert(k)} rightSection={<Text size="xs" c="dimmed">{`{${k}}`}</Text>}>
                        {label}
                      </Menu.Item>
                    ))}
                    <Menu.Divider />
                    <Menu.Label>Fallback when empty: {'{first_name|there}'}</Menu.Label>
                  </Menu.Dropdown>
                </Menu>
                <FileButton onChange={loadFile} accept=".html,.htm,text/html">
                  {(props) => (
                    <Button {...props} size="xs" variant="default" leftSection={<IconUpload size={14} />}>
                      Load .html
                    </Button>
                  )}
                </FileButton>
              </Group>
            )}
          </Group>
          <Textarea
            ref={area}
            autosize
            minRows={18}
            maxRows={32}
            value={value.body_html}
            onChange={(e) => onChange({ ...value, body_html: e.target.value })}
            readOnly={readOnly}
            styles={{ input: { fontFamily: 'ui-monospace, Consolas, monospace', fontSize: 12 } }}
          />
          <Text size="xs" c="dimmed">
            Paste HTML from your designer or edit the starter. Merge fields are filled per recipient and escaped. An unsubscribe footer is added when the email has no {'{unsubscribe_url}'} link.
          </Text>
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 6 }}>
        <Card withBorder p={0} style={{ position: 'sticky', top: 72 }}>
          <Group justify="space-between" px="sm" py={6}>
            <Text size="sm" truncate>
              <Badge size="xs" variant="light" mr={6}>
                Preview
              </Badge>
              {preview?.subject || '(no subject)'}
            </Text>
            <SegmentedControl
              size="xs"
              value={width}
              onChange={setWidth}
              data={[
                { value: 'desktop', label: 'Desktop' },
                { value: 'mobile', label: 'Mobile' },
              ]}
            />
          </Group>
          <ScrollArea h="calc(100vh - 220px)" bg="gray.2">
            <iframe
              title="Email preview"
              srcDoc={preview?.html ?? ''}
              sandbox=""
              style={{ width: width === 'mobile' ? 375 : '100%', height: 1400, border: 0, background: 'white', display: 'block', margin: '0 auto' }}
            />
          </ScrollArea>
        </Card>
      </Grid.Col>
    </Grid>
  )
}

/** Mail server status for the email pages (and a test button for admins). */
export function MailStatus({ purpose = 'bulk' }: { purpose?: 'bulk' | 'transactional' }) {
  const { data } = useMailSettings()
  if (!data) return null
  const st = data[purpose]
  const via = st.backend === 'smtp' ? `SMTP ${data.smtp.host}:${data.smtp.port}` : st.backend === 'graph' ? 'Microsoft 365' : st.backend
  return (
    <Badge color={st.enabled ? 'green' : 'orange'} variant="light" tt="none">
      {st.enabled ? `Sending via ${via}${data.from ? ` as ${data.from}` : ''}` : 'Email sending is not configured'}
    </Badge>
  )
}

interface ContactEmailHistory {
  campaigns: { campaign_id: number; name: string; status: string; sent_at: string | null; opened_at: string | null; clicked_at: string | null; unsubscribed_at: string | null }[]
  lists: { id: number; name: string; status: string }[]
}

/** Lists a contact is on and the campaigns they received (contact page). */
export function ContactEmailCard({ contactId }: { contactId: number }) {
  const { data } = useQuery({ queryKey: ['contact-campaigns', contactId], queryFn: () => api<ContactEmailHistory>(`/contacts/${contactId}/campaigns`) })
  if (!data || (!data.lists.length && !data.campaigns.length)) return null
  return (
    <Card withBorder mt="md">
      <Text size="sm" fw={600} mb={6}>
        Email marketing
      </Text>
      <Group gap={4} mb="xs">
        {data.lists.map((l) => (
          <Badge key={l.id} size="sm" variant="light" color={l.status === 'subscribed' ? 'blue' : 'gray'} component={Link} to={`/email/lists/${l.id}`} style={{ cursor: 'pointer' }}>
            {l.name}
            {l.status !== 'subscribed' ? ' (unsubscribed)' : ''}
          </Badge>
        ))}
      </Group>
      <Stack gap={4}>
        {data.campaigns.slice(0, 8).map((c) => (
          <Group key={c.campaign_id} justify="space-between" wrap="nowrap">
            <Text size="xs" truncate component={Link} to={`/email/campaigns/${c.campaign_id}`}>
              {c.name}
            </Text>
            <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
              {c.unsubscribed_at ? 'unsubscribed' : c.clicked_at ? 'clicked' : c.opened_at ? 'opened' : c.status}
            </Text>
          </Group>
        ))}
      </Stack>
    </Card>
  )
}
