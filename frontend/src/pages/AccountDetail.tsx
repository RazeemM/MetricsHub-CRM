import { Anchor, Badge, Button, Card, Grid, Group, SimpleGrid, Stack, Table, Tabs, Text } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { modals } from '@mantine/modals'
import { IconEdit, IconPlus, IconTrash } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Activities } from '../components/Activities'
import { AccountTypeBadge, Field, LifecycleBadge, PageHeader } from '../components/common'
import { AccountLicences } from '../components/Licences'
import { AccountFormModal, ContactFormModal } from '../components/forms'
import { useApiMutation } from '../hooks'
import { CONTACT_ROLES, fmtDate, money } from '../labels'
import type { Account, Contact, Opportunity, Page } from '../types'

export default function AccountDetail() {
  const id = Number(useParams().id)
  const nav = useNavigate()
  const { canWrite } = useAuth()
  const [params, setParams] = useSearchParams()
  const [editOpen, edit] = useDisclosure()
  const [contactOpen, contactModal] = useDisclosure()
  const { data: acc } = useQuery({ queryKey: ['account', id], queryFn: () => api<Account>(`/accounts/${id}`) })
  const { data: contacts } = useQuery({
    queryKey: ['contacts', { account_id: id }],
    queryFn: () => api<Page<Contact>>('/contacts', { params: { account_id: id, page_size: 200 } }),
  })
  const isPlatform = acc?.account_type === 'platform_partner'
  const { data: opps } = useQuery({
    queryKey: ['opportunities', { account: id, platform: isPlatform }],
    queryFn: () =>
      api<Page<Opportunity>>('/opportunities', {
        params: isPlatform ? { referring_platform_id: id, page_size: 200 } : { account_id: id, page_size: 200 },
      }),
    enabled: !!acc,
  })
  const remove = useApiMutation(() => api(`/accounts/${id}`, { method: 'DELETE' }), {
    invalidate: [['accounts']],
    success: 'Account deleted',
    onSuccess: () => nav('/accounts'),
  })

  if (!acc) return null
  return (
    <>
      <PageHeader
        title={
          <Group gap="sm">
            {acc.name} <AccountTypeBadge value={acc.account_type} />
          </Group>
        }
        subtitle={[acc.industry, acc.city, acc.country].filter(Boolean).join(' · ')}
        actions={
          canWrite && (
            <>
              <Button variant="default" leftSection={<IconEdit size={16} />} onClick={edit.open}>
                Edit
              </Button>
              <Button component={Link} to={`/opportunities/new?account_id=${id}`} leftSection={<IconPlus size={16} />}>
                New opportunity
              </Button>
              <Button
                variant="subtle"
                color="red"
                onClick={() =>
                  modals.openConfirmModal({
                    title: 'Delete account?',
                    children: <Text size="sm">Contacts stay in the CRM but are unlinked. Accounts with opportunities cannot be deleted.</Text>,
                    labels: { confirm: 'Delete', cancel: 'Cancel' },
                    confirmProps: { color: 'red' },
                    onConfirm: () => remove.mutate(undefined),
                  })
                }
              >
                <IconTrash size={16} />
              </Button>
            </>
          )
        }
      />
      <Grid>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card withBorder>
            <Stack gap="sm">
              <SimpleGrid cols={2}>
                <Field label="Domain">{acc.domain}</Field>
                <Field label="Phone">{acc.phone}</Field>
                <Field label="Website">
                  {acc.website && (
                    <Anchor href={acc.website.startsWith('http') ? acc.website : `https://${acc.website}`} target="_blank" size="sm">
                      {acc.website}
                    </Anchor>
                  )}
                </Field>
                <Field label="Owner">{acc.owner?.full_name}</Field>
                <Field label="Region">{acc.region}</Field>
                <Field label="VAT">{acc.vat_number}</Field>
              </SimpleGrid>
              <Field label="Address">{acc.address}</Field>
              <Field label="Notes">
                <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                  {acc.notes}
                </Text>
              </Field>
              <Text size="xs" c="dimmed">
                Created {fmtDate(acc.created_at)}
              </Text>
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Tabs value={params.get('tab') ?? (isPlatform ? 'contacts' : 'licences')} onChange={(v) => setParams(v ? { tab: v } : {}, { replace: true })}>
            <Tabs.List>
              {!isPlatform && <Tabs.Tab value="licences">Licences</Tabs.Tab>}
              <Tabs.Tab value="contacts">Contacts ({contacts?.total ?? 0})</Tabs.Tab>
              <Tabs.Tab value="opps">
                {isPlatform ? 'Referred deals' : 'Opportunities'} ({opps?.total ?? 0})
              </Tabs.Tab>
              <Tabs.Tab value="activity">Activity</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="licences" pt="sm">
              <AccountLicences accountId={id} />
            </Tabs.Panel>
            <Tabs.Panel value="contacts" pt="sm">
              {canWrite && (
                <Group justify="flex-end" mb="xs">
                  <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={contactModal.open}>
                    Add contact
                  </Button>
                </Group>
              )}
              <Table highlightOnHover>
                <Table.Tbody>
                  {contacts?.items.map((c) => (
                    <Table.Tr key={c.id} className="clickable-row" onClick={() => nav(`/contacts/${c.id}`)}>
                      <Table.Td fw={500}>{c.full_name}</Table.Td>
                      <Table.Td>{c.job_title}</Table.Td>
                      <Table.Td>{c.email}</Table.Td>
                      <Table.Td>
                        <Badge variant="outline" size="sm">
                          {CONTACT_ROLES[c.role]}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <LifecycleBadge value={c.lifecycle} />
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Tabs.Panel>
            <Tabs.Panel value="opps" pt="sm">
              <Table highlightOnHover>
                <Table.Tbody>
                  {opps?.items.map((o) => (
                    <Table.Tr key={o.id} className="clickable-row" onClick={() => nav(`/opportunities/${o.id}`)}>
                      <Table.Td fw={500}>{o.title}</Table.Td>
                      {isPlatform && <Table.Td>{o.account.name}</Table.Td>}
                      <Table.Td>{o.brand.name}</Table.Td>
                      <Table.Td>
                        <Badge variant="light" color={o.stage.kind === 'won' ? 'green' : o.stage.kind === 'lost' ? 'gray' : 'violet'}>
                          {o.stage.name}
                        </Badge>
                      </Table.Td>
                      <Table.Td ta="right">{money(o.amount_tcv, o.currency)}</Table.Td>
                      <Table.Td>{fmtDate(o.expected_close_date)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Tabs.Panel>
            <Tabs.Panel value="activity" pt="sm">
              <Activities link={{ account_id: id }} />
            </Tabs.Panel>
          </Tabs>
        </Grid.Col>
      </Grid>
      <AccountFormModal opened={editOpen} onClose={edit.close} account={acc} />
      <ContactFormModal
        opened={contactOpen}
        onClose={contactModal.close}
        defaults={{ account_id: id, role: isPlatform ? 'platform_account_manager' : 'customer_contact' }}
      />
    </>
  )
}
