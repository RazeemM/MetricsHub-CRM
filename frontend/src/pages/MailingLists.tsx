import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Checkbox,
  FileButton,
  Group,
  Menu,
  Modal,
  MultiSelect,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  TagsInput,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { modals } from '@mantine/modals'
import { IconDots, IconFilter, IconPlus, IconTrash, IconUpload } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { PageHeader, Pager } from '../components/common'
import { useApiMutation, useBrands } from '../hooks'
import { ACCOUNT_TYPES, CONTACT_ROLES, LIFECYCLES, fmtDate, toOptions } from '../labels'

export interface MailingList {
  id: number
  name: string
  kind: 'list' | 'newsletter'
  description: string | null
  brand_id: number | null
  subscribed: number
  unsubscribed: number
  pending: number
  created_at: string
}

interface Member {
  id: number
  contact_id: number
  name: string
  email: string | null
  company: string | null
  status: 'subscribed' | 'unsubscribed' | 'pending'
  source: string | null
  added_at: string
  consent: boolean
  globally_unsubscribed: boolean
}

export const useLists = () => useQuery({ queryKey: ['lists'], queryFn: () => api<MailingList[]>('/lists') })

function ListForm({ opened, onClose, list }: { opened: boolean; onClose: () => void; list?: MailingList }) {
  const nav = useNavigate()
  const { data: brands } = useBrands()
  const [form, setForm] = useState({ name: list?.name ?? '', kind: list?.kind ?? 'list', description: list?.description ?? '', brand_id: list?.brand_id ? String(list.brand_id) : null as string | null })
  const save = useApiMutation(
    () =>
      api<MailingList>(list ? `/lists/${list.id}` : '/lists', {
        method: list ? 'PUT' : 'POST',
        body: { ...form, description: form.description || null, brand_id: form.brand_id ? Number(form.brand_id) : null },
      }),
    {
      invalidate: [['lists']],
      success: list ? 'List saved' : 'List created',
      onSuccess: (l) => {
        onClose()
        if (!list) nav(`/email/lists/${l.id}`)
      },
    },
  )
  return (
    <Modal opened={opened} onClose={onClose} title={list ? 'Edit list' : 'New list'}>
      <Stack>
        <TextInput label="Name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-autofocus />
        <SegmentedControl
          value={form.kind}
          onChange={(v) => setForm({ ...form, kind: v as 'list' | 'newsletter' })}
          data={[
            { value: 'list', label: 'Contact list' },
            { value: 'newsletter', label: 'Newsletter subscribers' },
          ]}
        />
        <Text size="xs" c="dimmed">
          {form.kind === 'newsletter'
            ? 'People who subscribed to a newsletter. Being a subscriber counts as consent to receive it.'
            : 'Any group of contacts: leads in a region, event attendees, customers of a product...'}
        </Text>
        <Select label="Brand" placeholder="Any" clearable data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))} value={form.brand_id} onChange={(v) => setForm({ ...form, brand_id: v })} />
        <Textarea label="Description" autosize minRows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <Group justify="flex-end">
          <Button loading={save.isPending} disabled={!form.name.trim()} onClick={() => save.mutate(undefined)}>
            Save
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

export default function MailingLists() {
  const nav = useNavigate()
  const { canWrite } = useAuth()
  const { data } = useLists()
  const [open, setOpen] = useState(false)
  return (
    <>
      <PageHeader help="audiences-lists"
        title="Mailing lists"
        subtitle="Who campaigns and newsletters go to"
        actions={
          canWrite && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setOpen(true)}>
              New list
            </Button>
          )
        }
      />
      <Card withBorder>
        {data?.length ? (
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Type</Table.Th>
                <Table.Th ta="right">Subscribed</Table.Th>
                <Table.Th ta="right">Unsubscribed</Table.Th>
                <Table.Th>Created</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.map((l) => (
                <Table.Tr key={l.id} className="clickable-row" onClick={() => nav(`/email/lists/${l.id}`)}>
                  <Table.Td fw={500}>{l.name}</Table.Td>
                  <Table.Td>
                    <Badge variant="light" color={l.kind === 'newsletter' ? 'grape' : 'blue'}>
                      {l.kind === 'newsletter' ? 'Newsletter' : 'List'}
                    </Badge>
                  </Table.Td>
                  <Table.Td ta="right">{l.subscribed.toLocaleString()}</Table.Td>
                  <Table.Td ta="right">{l.unsubscribed.toLocaleString()}</Table.Td>
                  <Table.Td>{fmtDate(l.created_at)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : (
          <Text size="sm" c="dimmed">
            No lists yet.
          </Text>
        )}
      </Card>
      {open && <ListForm opened onClose={() => setOpen(false)} />}
    </>
  )
}

function AddByFilter({ listId, onClose }: { listId: number; onClose: () => void }) {
  const { data: brands } = useBrands()
  const [f, setF] = useState({ lifecycle: [] as string[], role: [] as string[], account_type: [] as string[], country: [] as string[], brand_id: null as string | null, consent_only: false })
  const add = useApiMutation(
    () =>
      api<{ added: number; already_in_list: number }>(`/lists/${listId}/members`, {
        method: 'POST',
        body: { filter: { ...f, brand_id: f.brand_id ? Number(f.brand_id) : null, lifecycle: f.lifecycle.length ? f.lifecycle : null, role: f.role.length ? f.role : null, account_type: f.account_type.length ? f.account_type : null, country: f.country.length ? f.country : null } },
      }),
    { invalidate: [['list-members', listId], ['lists']], success: 'Contacts added', onSuccess: onClose },
  )
  return (
    <Modal opened onClose={onClose} title="Add contacts by filter" size="lg">
      <Stack>
        <Text size="sm" c="dimmed">
          Every contact with an email address that matches all the filters you set is added.
        </Text>
        <SimpleGrid cols={2}>
          <MultiSelect label="Lifecycle" data={toOptions(LIFECYCLES)} value={f.lifecycle} onChange={(v) => setF({ ...f, lifecycle: v })} clearable />
          <MultiSelect label="Contact role" data={toOptions(CONTACT_ROLES)} value={f.role} onChange={(v) => setF({ ...f, role: v })} clearable />
          <MultiSelect label="Account type" data={toOptions(ACCOUNT_TYPES)} value={f.account_type} onChange={(v) => setF({ ...f, account_type: v })} clearable />
          <TagsInput label="Countries" placeholder="Type and press Enter" value={f.country} onChange={(v) => setF({ ...f, country: v })} />
          <Select label="Brand" placeholder="Any" clearable data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))} value={f.brand_id} onChange={(v) => setF({ ...f, brand_id: v })} />
          <Checkbox mt="xl" label="Only contacts who gave marketing consent" checked={f.consent_only} onChange={(e) => setF({ ...f, consent_only: e.currentTarget.checked })} />
        </SimpleGrid>
        <Group justify="flex-end">
          <Button leftSection={<IconFilter size={16} />} loading={add.isPending} onClick={() => add.mutate(undefined)}>
            Add matching contacts
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function ImportCsv({ listId, onClose }: { listId: number; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [consent, setConsent] = useState(false)
  const run = useApiMutation(
    () => {
      const form = new FormData()
      form.append('file', file!)
      form.append('consent', String(consent))
      return api<{ rows: number; added: number; new_contacts: number; invalid_rows: number }>(`/lists/${listId}/import`, { method: 'POST', form })
    },
    {
      invalidate: [['list-members', listId], ['lists']],
      onSuccess: (r) => {
        modals.openConfirmModal({
          title: 'Import done',
          children: (
            <Text size="sm">
              {r.rows} rows: {r.added} added to the list, {r.new_contacts} new contacts created
              {r.invalid_rows ? `, ${r.invalid_rows} rows without a valid email skipped` : ''}.
            </Text>
          ),
          labels: { confirm: 'OK', cancel: 'Close' },
        })
        onClose()
      },
    },
  )
  return (
    <Modal opened onClose={onClose} title="Import from Excel or CSV">
      <Stack>
        <Text size="sm">
          An Excel (.xlsx) or CSV file with an <b>Email</b> column; <b>First name</b>, <b>Last name</b> and <b>Company</b> are optional. People not yet in the CRM are created as leads.
        </Text>
        <FileButton onChange={setFile} accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet">
          {(props) => (
            <Button {...props} variant="default" leftSection={<IconUpload size={16} />}>
              {file ? file.name : 'Choose file'}
            </Button>
          )}
        </FileButton>
        <Checkbox label="These people agreed to receive marketing email from us" checked={consent} onChange={(e) => setConsent(e.currentTarget.checked)} />
        <Alert variant="light" color="gray">
          Only tick this when you have their consent (e.g. a web form or event sign-up). It is recorded on each contact.
        </Alert>
        <Group justify="flex-end">
          <Button disabled={!file} loading={run.isPending} onClick={() => run.mutate(undefined)}>
            Import
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

export function MailingListDetail() {
  const id = Number(useParams().id)
  const nav = useNavigate()
  const { canWrite } = useAuth()
  const { data: lists } = useLists()
  const list = lists?.find((l) => l.id === id)
  const [q, setQ] = useState('')
  const [debounced] = useDebouncedValue(q, 300)
  const [status, setStatus] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState<'filter' | 'csv' | 'edit' | null>(null)
  const key = ['list-members', id]
  const { data } = useQuery({
    queryKey: [...key, debounced, status, page],
    queryFn: () => api<{ total: number; items: Member[] }>(`/lists/${id}/members`, { params: { q: debounced, status: status ?? undefined, page, page_size: 50 } }),
  })
  const setMember = useApiMutation((v: { mid: number; status: string }) => api(`/lists/${id}/members/${v.mid}`, { method: 'PATCH', body: { status: v.status } }), { invalidate: [key, ['lists']] })
  const remove = useApiMutation((mid: number) => api(`/lists/${id}/members/${mid}`, { method: 'DELETE' }), { invalidate: [key, ['lists']] })
  const del = useApiMutation(() => api(`/lists/${id}`, { method: 'DELETE' }), { invalidate: [['lists']], success: 'List deleted', onSuccess: () => nav('/email/lists') })

  if (!list) return null
  return (
    <>
      <PageHeader
        title={list.name}
        subtitle={`${list.kind === 'newsletter' ? 'Newsletter' : 'Contact list'} · ${list.subscribed} subscribed · ${list.unsubscribed} unsubscribed${list.pending ? ` · ${list.pending} waiting for confirmation` : ''}`}
        actions={
          canWrite && (
            <>
              <Button variant="light" leftSection={<IconFilter size={16} />} onClick={() => setModal('filter')}>
                Add by filter
              </Button>
              <Button variant="light" leftSection={<IconUpload size={16} />} onClick={() => setModal('csv')}>
                Import Excel / CSV
              </Button>
              <Menu position="bottom-end">
                <Menu.Target>
                  <ActionIcon variant="default" size="lg" aria-label="More">
                    <IconDots size={16} />
                  </ActionIcon>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Item onClick={() => setModal('edit')}>Edit list</Menu.Item>
                  <Menu.Item
                    color="red"
                    leftSection={<IconTrash size={14} />}
                    onClick={() =>
                      modals.openConfirmModal({
                        title: `Delete "${list.name}"?`,
                        children: <Text size="sm">The contacts stay in the CRM. Sent campaigns keep their reports.</Text>,
                        labels: { confirm: 'Delete', cancel: 'Cancel' },
                        confirmProps: { color: 'red' },
                        onConfirm: () => del.mutate(undefined),
                      })
                    }
                  >
                    Delete list
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </>
          )
        }
      />
      {list.description && (
        <Text size="sm" c="dimmed" mb="sm">
          {list.description}
        </Text>
      )}
      <Card withBorder>
        <Group mb="sm">
          <TextInput placeholder="Search name or email" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} w={280} />
          <Select placeholder="All statuses" clearable data={[{ value: 'subscribed', label: 'Subscribed' }, { value: 'pending', label: 'Waiting for confirmation' }, { value: 'unsubscribed', label: 'Unsubscribed' }]} value={status} onChange={(v) => { setStatus(v); setPage(1) }} w={180} />
        </Group>
        <Table.ScrollContainer minWidth={720}>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Contact</Table.Th>
                <Table.Th>Email</Table.Th>
                <Table.Th>Company</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Added</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data?.items.map((m) => (
                <Table.Tr key={m.id}>
                  <Table.Td>
                    <Anchor component={Link} to={`/contacts/${m.contact_id}`} size="sm">
                      {m.name}
                    </Anchor>
                  </Table.Td>
                  <Table.Td>{m.email ?? <Text c="red" size="sm">no email</Text>}</Table.Td>
                  <Table.Td>{m.company}</Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      <Badge size="sm" variant="light" color={m.status === 'subscribed' ? 'green' : m.status === 'pending' ? 'yellow' : 'gray'}>
                        {m.status === 'pending' ? 'waiting for confirmation' : m.status}
                      </Badge>
                      {m.globally_unsubscribed && (
                        <Badge size="sm" variant="light" color="red">
                          opted out of all email
                        </Badge>
                      )}
                      {m.consent && (
                        <Badge size="sm" variant="outline" color="teal">
                          consent
                        </Badge>
                      )}
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    {fmtDate(m.added_at)} {m.source && <Text span size="xs" c="dimmed">({m.source})</Text>}
                  </Table.Td>
                  <Table.Td>
                    {canWrite && (
                      <Menu position="bottom-end">
                        <Menu.Target>
                          <ActionIcon variant="subtle" aria-label="Member actions">
                            <IconDots size={16} />
                          </ActionIcon>
                        </Menu.Target>
                        <Menu.Dropdown>
                          {m.status === 'subscribed' ? (
                            <Menu.Item onClick={() => setMember.mutate({ mid: m.id, status: 'unsubscribed' })}>Unsubscribe from this list</Menu.Item>
                          ) : (
                            <Menu.Item onClick={() => setMember.mutate({ mid: m.id, status: 'subscribed' })}>Subscribe again</Menu.Item>
                          )}
                          <Menu.Item color="red" onClick={() => remove.mutate(m.id)}>
                            Remove from list
                          </Menu.Item>
                        </Menu.Dropdown>
                      </Menu>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        {data && !data.items.length && (
          <Text size="sm" c="dimmed">
            No members{q || status ? ' match' : ' yet: add contacts by filter or import an Excel or CSV file'}.
          </Text>
        )}
        {data && <Pager page={page} total={data.total} pageSize={50} onChange={setPage} />}
      </Card>
      {modal === 'filter' && <AddByFilter listId={id} onClose={() => setModal(null)} />}
      {modal === 'csv' && <ImportCsv listId={id} onClose={() => setModal(null)} />}
      {modal === 'edit' && <ListForm opened list={list} onClose={() => setModal(null)} />}
    </>
  )
}
