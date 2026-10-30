import { Badge, Button, Card, Checkbox, Group, Modal, MultiSelect, SegmentedControl, Select, Stack, Table, Text, TextInput } from '@mantine/core'
import { useDebouncedValue, useDisclosure } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import { IconDownload, IconListDetails, IconPlus, IconSearch, IconUsersGroup } from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, download } from '../api'
import { useAuth } from '../auth'
import { LifecycleBadge, PageHeader, Pager } from '../components/common'
import { SortTh, type Sort } from '../components/ui'
import { ContactFormModal } from '../components/forms'
import { useApiMutation } from '../hooks'
import { CONTACT_ROLES, fmtDate, LEAD_SOURCES, LIFECYCLES, toOptions } from '../labels'
import type { Contact, Page } from '../types'
import { useLists } from './MailingLists'
import { AudienceForm, useAudiences } from './Marketing'

export default function Contacts() {
  const nav = useNavigate()
  const { canWrite } = useAuth()
  const [q, setQ] = useState('')
  const [lifecycle, setLifecycle] = useState<string[]>([])
  const [role, setRole] = useState<string[]>([])
  const [source, setSource] = useState<string[]>([])
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<Sort>({ key: 'created_at', desc: true })
  const th = { sort, onSort: (s: Sort) => { setSort(s); setPage(1) } }
  const [debounced] = useDebouncedValue(q, 250)
  const [opened, { open, close }] = useDisclosure()
  // view: all contacts, the members of a list ("list:3") or the contacts matching an audience ("audience:4")
  const [search, setSearch] = useSearchParams()
  const view = search.get('view')
  const [kind, viewId] = (view ?? '').split(':')
  const { data: lists } = useLists()
  const { data: audiences } = useAudiences()
  const [selected, setSelected] = useState<number[]>([])
  const [toList, setToList] = useState(false)
  const [newAudience, setNewAudience] = useState(false)
  const setView = (v: string | null) => {
    setSearch(v ? { view: v } : {}, { replace: true })
    setPage(1)
    setSelected([])
  }
  const params = {
    q: debounced,
    lifecycle,
    role,
    source,
    list_id: kind === 'list' ? viewId : undefined,
    audience_id: kind === 'audience' ? viewId : undefined,
    sort: sort.key,
    desc: sort.desc,
    page,
    page_size: 50,
  }
  const { data } = useQuery({
    queryKey: ['contacts', params],
    queryFn: () => api<Page<Contact>>('/contacts', { params }),
    placeholderData: keepPreviousData,
  })
  const reset = <T,>(fn: (v: T) => void) => (v: T) => {
    fn(v)
    setPage(1)
  }
  const pageIds = data?.items.map((c) => c.id) ?? []
  const allSelected = pageIds.length > 0 && pageIds.every((i) => selected.includes(i))
  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  const viewOptions = [
    { group: 'Contacts', items: [{ value: '', label: 'All contacts' }] },
    { group: 'Lists', items: (lists ?? []).map((l) => ({ value: `list:${l.id}`, label: `${l.name} (${l.subscribed})` })) },
    { group: 'Audiences', items: (audiences ?? []).map((a) => ({ value: `audience:${a.id}`, label: `${a.name} (${a.counts?.matching ?? 0})` })) },
  ].filter((g) => g.items.length)

  return (
    <>
      <PageHeader help="accounts-contacts"
        title="Contacts"
        subtitle="Leads, customer contacts and platform account managers"
        actions={
          <>
            <Button variant="default" leftSection={<IconDownload size={16} />} onClick={() => download('/export/contacts', { q: debounced, lifecycle, source })}>
              Export
            </Button>
            {canWrite && (lifecycle.length > 0 || role.length > 0 || source.length > 0) && (
              <Button variant="default" leftSection={<IconUsersGroup size={16} />} onClick={() => setNewAudience(true)}>
                Save as audience
              </Button>
            )}
            {canWrite && (
              <Button leftSection={<IconPlus size={16} />} onClick={open}>
                New contact
              </Button>
            )}
          </>
        }
      />
      <Card withBorder p={0}>
        <Group p="sm" gap="sm">
          <Select
            aria-label="View"
            leftSection={kind === 'audience' ? <IconUsersGroup size={16} /> : <IconListDetails size={16} />}
            data={viewOptions}
            value={view ?? ''}
            onChange={(v) => setView(v || null)}
            allowDeselect={false}
            searchable
            w={240}
          />
          <TextInput placeholder="Search name, email, company" leftSection={<IconSearch size={16} />} value={q} onChange={(e) => reset(setQ)(e.target.value)} w={260} />
          <MultiSelect placeholder="Lifecycle" data={toOptions(LIFECYCLES)} value={lifecycle} onChange={reset(setLifecycle)} clearable w={200} />
          <MultiSelect placeholder="Role" data={toOptions(CONTACT_ROLES)} value={role} onChange={reset(setRole)} clearable w={240} />
          <MultiSelect placeholder="Source" data={toOptions(LEAD_SOURCES)} value={source} onChange={reset(setSource)} clearable w={220} />
        </Group>
        {canWrite && selected.length > 0 && (
          <Group px="sm" pb="sm" gap="sm">
            <Text size="sm" fw={500}>
              {selected.length} selected
            </Text>
            <Button size="xs" leftSection={<IconListDetails size={14} />} onClick={() => setToList(true)}>
              Add to list
            </Button>
            <Button size="xs" variant="subtle" onClick={() => setSelected([])}>
              Clear selection
            </Button>
          </Group>
        )}
        <Table.ScrollContainer minWidth={860}>
          <Table highlightOnHover verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                {canWrite && (
                  <Table.Th w={36}>
                    <Checkbox
                      aria-label="Select all on this page"
                      checked={allSelected}
                      indeterminate={!allSelected && pageIds.some((i) => selected.includes(i))}
                      onChange={() => setSelected((s) => (allSelected ? s.filter((i) => !pageIds.includes(i)) : [...new Set([...s, ...pageIds])]))}
                    />
                  </Table.Th>
                )}
                <SortTh label="Name" sortKey="name" {...th} />
                <SortTh label="Email" sortKey="email" {...th} />
                <SortTh label="Account" sortKey="account" {...th} />
                <SortTh label="Role" sortKey="role" {...th} info="Customer contact, platform account manager (Datadog, BMC…), partner contact, technical, economic buyer or champion." />
                <SortTh label="Lifecycle" sortKey="lifecycle" {...th} info="Lead, qualified, customer or disqualified." />
                <SortTh label="Source" sortKey="source" {...th} info="How the contact reached the CRM: import, website form, Freshsales migration…" />
                <SortTh label="Created" sortKey="created_at" firstDesc {...th} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data?.items.map((c) => (
                <Table.Tr key={c.id} className="clickable-row" onClick={() => nav(`/contacts/${c.id}`)}>
                  {canWrite && (
                    <Table.Td onClick={(e) => e.stopPropagation()}>
                      <Checkbox aria-label={`Select ${c.full_name}`} checked={selected.includes(c.id)} onChange={() => toggle(c.id)} />
                    </Table.Td>
                  )}
                  <Table.Td fw={500}>
                    {c.full_name}
                    {c.job_title && (
                      <Badge ml={6} variant="transparent" color="gray" size="sm" tt="none">
                        {c.job_title}
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>{c.email}</Table.Td>
                  <Table.Td>{c.account?.name}</Table.Td>
                  <Table.Td>{CONTACT_ROLES[c.role]}</Table.Td>
                  <Table.Td>
                    <LifecycleBadge value={c.lifecycle} />
                  </Table.Td>
                  <Table.Td>{c.source ? LEAD_SOURCES[c.source] ?? c.source : ''}</Table.Td>
                  <Table.Td>{fmtDate(c.created_at)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Group px="sm" pb="sm" display="block">
          <Pager page={page} total={data?.total ?? 0} pageSize={50} onChange={setPage} />
        </Group>
      </Card>
      <ContactFormModal opened={opened} onClose={close} onSaved={(c) => nav(`/contacts/${c.id}`)} />
      <AddToListModal opened={toList} onClose={() => setToList(false)} contactIds={selected} onDone={() => setSelected([])} />
      <AudienceForm
        opened={newAudience}
        onClose={() => setNewAudience(false)}
        initialRules={{ lifecycle, role, source, ...(kind === 'list' ? { list_ids: [Number(viewId)] } : {}) }}
      />
    </>
  )
}

function AddToListModal({ opened, onClose, contactIds, onDone }: { opened: boolean; onClose: () => void; contactIds: number[]; onDone: () => void }) {
  const nav = useNavigate()
  const { data: lists } = useLists()
  const [mode, setMode] = useState('existing')
  const [listId, setListId] = useState<string | null>(null)
  const [name, setName] = useState('')
  const add = useApiMutation(
    () =>
      api<{ list_id: number; list_name: string; added: number; already_in_list: number }>('/contacts/add-to-list', {
        method: 'POST',
        body: { contact_ids: contactIds, ...(mode === 'new' ? { new_list_name: name } : { list_id: Number(listId) }) },
      }),
    {
      invalidate: [['lists'], ['contacts']],
      onSuccess: (r) => {
        notifications.show({
          color: 'green',
          message: `${r.added} added to ${r.list_name}${r.already_in_list ? ` (${r.already_in_list} already in it)` : ''}`,
        })
        onDone()
        onClose()
        if (mode === 'new') nav(`/email/lists/${r.list_id}`)
      },
    },
  )
  return (
    <Modal opened={opened} onClose={onClose} title={`Add ${contactIds.length} contact${contactIds.length === 1 ? '' : 's'} to a list`}>
      <Stack>
        <SegmentedControl
          value={mode}
          onChange={setMode}
          data={[
            { value: 'existing', label: 'Existing list' },
            { value: 'new', label: 'New list' },
          ]}
        />
        {mode === 'existing' ? (
          <Select label="List" searchable data={(lists ?? []).map((l) => ({ value: String(l.id), label: `${l.name} (${l.subscribed})` }))} value={listId} onChange={setListId} />
        ) : (
          <TextInput label="New list name" placeholder="e.g. Gartner summit 2026 attendees" value={name} onChange={(e) => setName(e.target.value)} data-autofocus />
        )}
        <Group justify="flex-end">
          <Button loading={add.isPending} disabled={mode === 'new' ? !name.trim() : !listId} onClick={() => add.mutate(undefined)}>
            Add to list
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
