import { Badge, Button, Card, Group, MultiSelect, Table, TextInput } from '@mantine/core'
import { useDebouncedValue, useDisclosure } from '@mantine/hooks'
import { IconDownload, IconPlus, IconSearch } from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, download } from '../api'
import { useAuth } from '../auth'
import { LifecycleBadge, PageHeader, Pager } from '../components/common'
import { ContactFormModal } from '../components/forms'
import { CONTACT_ROLES, fmtDate, LEAD_SOURCES, LIFECYCLES, toOptions } from '../labels'
import type { Contact, Page } from '../types'

export default function Contacts() {
  const nav = useNavigate()
  const { canWrite } = useAuth()
  const [q, setQ] = useState('')
  const [lifecycle, setLifecycle] = useState<string[]>([])
  const [role, setRole] = useState<string[]>([])
  const [source, setSource] = useState<string[]>([])
  const [page, setPage] = useState(1)
  const [debounced] = useDebouncedValue(q, 250)
  const [opened, { open, close }] = useDisclosure()
  const params = { q: debounced, lifecycle, role, source, page, page_size: 50 }
  const { data } = useQuery({
    queryKey: ['contacts', params],
    queryFn: () => api<Page<Contact>>('/contacts', { params }),
    placeholderData: keepPreviousData,
  })
  const reset = <T,>(fn: (v: T) => void) => (v: T) => {
    fn(v)
    setPage(1)
  }

  return (
    <>
      <PageHeader
        title="Contacts"
        subtitle="Leads, customer contacts and platform account managers"
        actions={
          <>
            <Button variant="default" leftSection={<IconDownload size={16} />} onClick={() => download('/export/contacts', { q: debounced, lifecycle, source })}>
              Export
            </Button>
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
          <TextInput placeholder="Search name, email, company" leftSection={<IconSearch size={16} />} value={q} onChange={(e) => reset(setQ)(e.target.value)} w={260} />
          <MultiSelect placeholder="Lifecycle" data={toOptions(LIFECYCLES)} value={lifecycle} onChange={reset(setLifecycle)} clearable w={200} />
          <MultiSelect placeholder="Role" data={toOptions(CONTACT_ROLES)} value={role} onChange={reset(setRole)} clearable w={240} />
          <MultiSelect placeholder="Source" data={toOptions(LEAD_SOURCES)} value={source} onChange={reset(setSource)} clearable w={220} />
        </Group>
        <Table.ScrollContainer minWidth={860}>
          <Table highlightOnHover verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Email</Table.Th>
                <Table.Th>Account</Table.Th>
                <Table.Th>Role</Table.Th>
                <Table.Th>Lifecycle</Table.Th>
                <Table.Th>Source</Table.Th>
                <Table.Th>Created</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data?.items.map((c) => (
                <Table.Tr key={c.id} className="clickable-row" onClick={() => nav(`/contacts/${c.id}`)}>
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
    </>
  )
}
