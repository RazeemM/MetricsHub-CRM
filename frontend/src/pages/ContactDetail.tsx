import { Anchor, Badge, Button, Card, Grid, Group, SimpleGrid, Stack, Text } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { modals } from '@mantine/modals'
import { IconEdit, IconMail, IconPlus, IconTrash } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Activities } from '../components/Activities'
import { WebActivity } from '../components/WebActivity'
import { ComposeEmail } from '../components/ComposeEmail'
import { Field, LifecycleBadge, PageHeader } from '../components/common'
import { ContactEmailCard } from '../components/EmailEditor'
import { ContactFormModal } from '../components/forms'
import { useApiMutation, useBrands } from '../hooks'
import { CONTACT_ROLES, fmtDate, LEAD_SOURCES } from '../labels'
import type { Contact } from '../types'

export default function ContactDetail() {
  const id = Number(useParams().id)
  const nav = useNavigate()
  const { canWrite } = useAuth()
  const { data: brands } = useBrands()
  const [composeOpen, composeModal] = useDisclosure()
  const [editOpen, edit] = useDisclosure()
  const { data: c } = useQuery({ queryKey: ['contact', id], queryFn: () => api<Contact>(`/contacts/${id}`) })
  const remove = useApiMutation(() => api(`/contacts/${id}`, { method: 'DELETE' }), {
    invalidate: [['contacts']],
    success: 'Contact deleted',
    onSuccess: () => nav('/contacts'),
  })
  if (!c) return null
  return (
    <>
      <PageHeader
        title={
          <Group gap="sm">
            {c.full_name} <LifecycleBadge value={c.lifecycle} />
          </Group>
        }
        subtitle={[c.job_title, c.account?.name].filter(Boolean).join(' at ')}
        actions={
          <>
            {c.email && canWrite && (
              <Button variant="default" onClick={composeModal.open} leftSection={<IconMail size={16} />}>
                Email
              </Button>
            )}
            {canWrite && (
              <>
                <Button variant="default" leftSection={<IconEdit size={16} />} onClick={edit.open}>
                  Edit
                </Button>
                {c.account_id && (
                  <Button component={Link} to={`/opportunities/new?account_id=${c.account_id}&primary_contact_id=${c.id}`} leftSection={<IconPlus size={16} />}>
                    New opportunity
                  </Button>
                )}
                <Button
                  variant="subtle"
                  color="red"
                  onClick={() =>
                    modals.openConfirmModal({
                      title: 'Delete contact?',
                      labels: { confirm: 'Delete', cancel: 'Cancel' },
                      confirmProps: { color: 'red' },
                      onConfirm: () => remove.mutate(undefined),
                    })
                  }
                >
                  <IconTrash size={16} />
                </Button>
              </>
            )}
          </>
        }
      />
      <Grid>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card withBorder>
            <Stack gap="sm">
              <SimpleGrid cols={2}>
                <Field label="Email">
                  {c.email &&
                    (canWrite ? (
                      <Anchor component="button" type="button" size="sm" onClick={composeModal.open}>
                        {c.email}
                      </Anchor>
                    ) : (
                      <Text size="sm">{c.email}</Text>
                    ))}
                  {!!c.previous_emails?.length && (
                    <Text size="xs" c="dimmed">
                      Previously {c.previous_emails.join(', ')}
                    </Text>
                  )}
                </Field>
                <Field label="Phone">{c.phone}</Field>
                <Field label="Mobile">{c.mobile}</Field>
                <Field label="Account">{c.account && <Anchor component={Link} to={`/accounts/${c.account.id}`} size="sm">{c.account.name}</Anchor>}</Field>
                <Field label="Role">{CONTACT_ROLES[c.role]}</Field>
                <Field label="Source">{c.source ? LEAD_SOURCES[c.source] ?? c.source : null}</Field>
                <Field label="Brand interest">{brands?.find((b) => b.id === c.brand_id)?.name}</Field>
                <Field label="Owner">{c.owner?.full_name}</Field>
                <Field label="Country">{c.country}</Field>
                <Field label="LinkedIn">{c.linkedin && <Anchor href={c.linkedin} target="_blank" size="sm">Profile</Anchor>}</Field>
              </SimpleGrid>
              <Group gap="xs">
                <Badge color={c.consent_marketing ? 'green' : 'gray'} variant="light">
                  {c.consent_marketing ? 'Marketing opt-in' : 'No marketing consent'}
                </Badge>
                {c.unsubscribed && <Badge color="red" variant="light">Unsubscribed</Badge>}
              </Group>
              <Field label="Notes">
                <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{c.notes}</Text>
              </Field>
              <Text size="xs" c="dimmed">Created {fmtDate(c.created_at)}</Text>
            </Stack>
          </Card>
          <ContactEmailCard contactId={id} />
          <WebActivity contactId={id} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Activities link={{ contact_id: id }} />
        </Grid.Col>
      </Grid>
      <ContactFormModal opened={editOpen} onClose={edit.close} contact={c} />
      <ComposeEmail opened={composeOpen} onClose={composeModal.close} contactId={id} />
    </>
  )
}
