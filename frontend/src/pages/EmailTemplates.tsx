import { ActionIcon, Button, Card, Group, Modal, Select, SimpleGrid, Stack, Table, Text, TextInput, UnstyledButton } from '@mantine/core'
import { modals } from '@mantine/modals'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { PageHeader } from '../components/common'
import { EmailEditor, MailStatus, type EmailContent } from '../components/EmailEditor'
import { useApiMutation, useBrands } from '../hooks'
import { fmtDate } from '../labels'

export interface EmailTemplate extends EmailContent {
  id: number
  name: string
  brand_id: number | null
  updated_at: string
}

interface Starter extends EmailContent {
  key: string
  name: string
}

export const useEmailTemplates = () => useQuery({ queryKey: ['email-templates'], queryFn: () => api<EmailTemplate[]>('/email-templates') })

export default function EmailTemplates() {
  const nav = useNavigate()
  const { canWrite } = useAuth()
  const { data } = useEmailTemplates()
  const { data: brands } = useBrands()
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [brandId, setBrandId] = useState<string | null>(null)
  const { data: starters } = useQuery({
    queryKey: ['email-starters', brandId],
    queryFn: () => api<Starter[]>('/email-templates/starters', { params: { brand_id: brandId ?? undefined } }),
    enabled: creating,
  })
  const create = useApiMutation(
    (s: Starter) =>
      api<EmailTemplate>('/email-templates', {
        method: 'POST',
        body: { name, brand_id: brandId ? Number(brandId) : null, subject: s.subject || name, preheader: s.preheader || null, body_html: s.body_html },
      }),
    { invalidate: [['email-templates']], onSuccess: (t) => nav(`/email/templates/${t.id}`) },
  )
  const remove = useApiMutation((id: number) => api(`/email-templates/${id}`, { method: 'DELETE' }), { invalidate: [['email-templates']], success: 'Template deleted' })

  return (
    <>
      <PageHeader
        title="Email templates"
        subtitle="Reusable designs for campaigns and newsletters"
        actions={
          <>
            <MailStatus />
            {canWrite && (
              <Button leftSection={<IconPlus size={16} />} onClick={() => setCreating(true)}>
                New template
              </Button>
            )}
          </>
        }
      />
      <Card withBorder>
        {data?.length ? (
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Subject</Table.Th>
                <Table.Th>Brand</Table.Th>
                <Table.Th>Updated</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.map((t) => (
                <Table.Tr key={t.id} className="clickable-row" onClick={() => nav(`/email/templates/${t.id}`)}>
                  <Table.Td fw={500}>{t.name}</Table.Td>
                  <Table.Td>{t.subject}</Table.Td>
                  <Table.Td>{brands?.find((b) => b.id === t.brand_id)?.name ?? 'Any'}</Table.Td>
                  <Table.Td>{fmtDate(t.updated_at)}</Table.Td>
                  <Table.Td onClick={(e) => e.stopPropagation()}>
                    {canWrite && (
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        aria-label="Delete template"
                        onClick={() =>
                          modals.openConfirmModal({
                            title: `Delete "${t.name}"?`,
                            children: <Text size="sm">Campaigns already created from it keep their own copy.</Text>,
                            labels: { confirm: 'Delete', cancel: 'Cancel' },
                            confirmProps: { color: 'red' },
                            onConfirm: () => remove.mutate(t.id),
                          })
                        }
                      >
                        <IconTrash size={16} />
                      </ActionIcon>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : (
          <Text size="sm" c="dimmed">
            No templates yet. Create one from a starter design.
          </Text>
        )}
      </Card>
      <Modal opened={creating} onClose={() => setCreating(false)} title="New email template" size="lg">
        <Stack>
          <SimpleGrid cols={2}>
            <TextInput label="Name" required value={name} onChange={(e) => setName(e.target.value)} data-autofocus />
            <Select label="Brand" placeholder="Any" clearable data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))} value={brandId} onChange={setBrandId} />
          </SimpleGrid>
          <Text size="sm" fw={500}>
            Start from
          </Text>
          <SimpleGrid cols={3}>
            {(starters ?? []).map((s) => (
              <UnstyledButton key={s.key} disabled={!name.trim() || create.isPending} onClick={() => create.mutate(s)}>
                <Card withBorder padding="sm" style={{ opacity: name.trim() ? 1 : 0.5 }}>
                  <Text fw={600} size="sm">
                    {s.name}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {s.key === 'blank' ? 'Header and footer only' : s.key === 'newsletter' ? 'Stories with buttons' : 'One message, one call to action'}
                  </Text>
                </Card>
              </UnstyledButton>
            ))}
          </SimpleGrid>
          {!name.trim() && (
            <Text size="xs" c="dimmed">
              Enter a name first.
            </Text>
          )}
        </Stack>
      </Modal>
    </>
  )
}

export function EmailTemplateEdit() {
  const id = Number(useParams().id)
  const { canWrite } = useAuth()
  const { data: brands } = useBrands()
  const { data } = useQuery({ queryKey: ['email-template', id], queryFn: () => api<EmailTemplate>(`/email-templates/${id}`) })
  const [draft, setDraft] = useState<EmailTemplate | null>(null)
  useEffect(() => {
    if (data) setDraft(data)
  }, [data])
  const dirty = JSON.stringify(draft) !== JSON.stringify(data)
  const save = useApiMutation(
    () => api<EmailTemplate>(`/email-templates/${id}`, { method: 'PUT', body: { name: draft!.name, brand_id: draft!.brand_id, subject: draft!.subject, preheader: draft!.preheader, body_html: draft!.body_html } }),
    { invalidate: [['email-templates'], ['email-template', id]], success: 'Template saved' },
  )
  if (!draft) return null
  return (
    <>
      <PageHeader
        title={draft.name || 'Template'}
        subtitle="Changes apply to campaigns created afterwards"
        actions={
          canWrite && (
            <Button onClick={() => save.mutate(undefined)} loading={save.isPending} disabled={!dirty || !draft.subject || !draft.body_html}>
              Save template
            </Button>
          )
        }
      />
      <Group mb="md" grow>
        <TextInput label="Template name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} readOnly={!canWrite} />
        <Select
          label="Brand"
          placeholder="Any"
          clearable
          data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))}
          value={draft.brand_id ? String(draft.brand_id) : null}
          onChange={(v) => setDraft({ ...draft, brand_id: v ? Number(v) : null })}
          disabled={!canWrite}
        />
      </Group>
      <EmailEditor value={draft} onChange={(v) => setDraft({ ...draft, ...v })} readOnly={!canWrite} />
    </>
  )
}
