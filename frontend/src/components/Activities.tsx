import { ActionIcon, Badge, Button, Card, Checkbox, Group, SegmentedControl, Stack, Text, Textarea, TextInput, Timeline } from '@mantine/core'
import { DateTimePicker } from '@mantine/dates'
import { IconCalendarEvent, IconChecklist, IconMail, IconNote, IconPhone, IconTrash } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { useApiMutation } from '../hooks'
import { fmtDate } from '../labels'
import type { Activity, Page } from '../types'

const ICONS = { note: IconNote, task: IconChecklist, call: IconPhone, meeting: IconCalendarEvent, email: IconMail }

type Link = { account_id?: number; contact_id?: number; opportunity_id?: number }

export function Activities({ link }: { link: Link }) {
  const { canWrite } = useAuth()
  const key = ['activities', link]
  const { data } = useQuery({ queryKey: key, queryFn: () => api<Page<Activity>>('/activities', { params: { ...link, page_size: 100 } }) })
  const [type, setType] = useState<Activity['type']>('note')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [due, setDue] = useState<Date | null>(null)

  const create = useApiMutation(
    () => api('/activities', { method: 'POST', body: { ...link, type, subject, body: body || null, due_at: due?.toISOString() ?? null } }),
    {
      invalidate: [['activities'], ['dashboard']],
      onSuccess: () => {
        setSubject('')
        setBody('')
        setDue(null)
      },
    },
  )
  const toggle = useApiMutation(
    (a: Activity) => api(`/activities/${a.id}`, { method: 'PATCH', body: { completed_at: a.completed_at ? null : new Date().toISOString() } }),
    { invalidate: [['activities'], ['dashboard']] },
  )
  const remove = useApiMutation((id: number) => api(`/activities/${id}`, { method: 'DELETE' }), { invalidate: [['activities']] })

  return (
    <Stack>
      {canWrite && (
        <Card withBorder>
          <Stack gap="xs">
            <SegmentedControl
              size="xs"
              value={type}
              onChange={(v) => setType(v as Activity['type'])}
              data={[
                { value: 'note', label: 'Note' },
                { value: 'task', label: 'Task' },
                { value: 'call', label: 'Call' },
                { value: 'meeting', label: 'Meeting' },
                { value: 'email', label: 'Email (log)' },
              ]}
            />
            <TextInput placeholder={type === 'task' ? 'Follow up on…' : 'Subject'} value={subject} onChange={(e) => setSubject(e.target.value)} />
            <Textarea placeholder="Details" autosize minRows={2} value={body} onChange={(e) => setBody(e.target.value)} />
            {type === 'task' && <DateTimePicker placeholder="Due date" value={due} onChange={(v) => setDue(v ? new Date(v) : null)} clearable />}
            <Group justify="flex-end">
              <Button size="xs" disabled={!subject.trim()} loading={create.isPending} onClick={() => create.mutate(undefined)}>
                Add {type}
              </Button>
            </Group>
          </Stack>
        </Card>
      )}
      {!data?.items.length ? (
        <Text c="dimmed" size="sm">
          No activity yet.
        </Text>
      ) : (
        <Timeline bulletSize={26} lineWidth={2}>
          {data.items.map((a) => {
            const Icon = ICONS[a.type]
            return (
              <Timeline.Item key={a.id} bullet={<Icon size={14} />}>
                <Group justify="space-between" wrap="nowrap" align="flex-start">
                  <Group gap={6} wrap="nowrap">
                    {a.type === 'task' && (
                      <Checkbox size="xs" checked={!!a.completed_at} onChange={() => toggle.mutate(a)} disabled={!canWrite} aria-label="Done" />
                    )}
                    <Text fw={500} size="sm" td={a.completed_at && a.type === 'task' ? 'line-through' : undefined}>
                      {a.subject}
                    </Text>
                    {a.type === 'task' && a.due_at && !a.completed_at && (
                      <Badge size="xs" color={new Date(a.due_at) < new Date() ? 'red' : 'blue'} variant="light">
                        due {fmtDate(a.due_at)}
                      </Badge>
                    )}
                  </Group>
                  {canWrite && (
                    <ActionIcon size="sm" variant="subtle" color="gray" onClick={() => remove.mutate(a.id)} aria-label="Delete">
                      <IconTrash size={14} />
                    </ActionIcon>
                  )}
                </Group>
                {a.body && (
                  <Text size="sm" c="dimmed" style={{ whiteSpace: 'pre-wrap' }}>
                    {a.body}
                  </Text>
                )}
                <Text size="xs" c="dimmed" mt={2}>
                  {a.owner?.full_name} · {fmtDate(a.created_at)}
                </Text>
              </Timeline.Item>
            )
          })}
        </Timeline>
      )}
    </Stack>
  )
}
