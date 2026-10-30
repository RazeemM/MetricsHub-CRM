import { Button, Card, Group, MultiSelect, Table, TextInput } from '@mantine/core'
import { useDebouncedValue, useDisclosure } from '@mantine/hooks'
import { IconDownload, IconPlus, IconSearch } from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, download } from '../api'
import { useAuth } from '../auth'
import { AccountTypeBadge, PageHeader, Pager } from '../components/common'
import { AccountFormModal } from '../components/forms'
import { SortTh, type Sort } from '../components/ui'
import { ACCOUNT_TYPES, toOptions } from '../labels'
import type { Account, Page } from '../types'

export default function Accounts() {
  const nav = useNavigate()
  const { canWrite } = useAuth()
  const [q, setQ] = useState('')
  const [types, setTypes] = useState<string[]>([])
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<Sort>({ key: 'name', desc: false })
  const [debounced] = useDebouncedValue(q, 250)
  const [opened, { open, close }] = useDisclosure()
  const params = { q: debounced, account_type: types, sort: sort.key, desc: sort.desc, page, page_size: 50 }
  const th = { sort, onSort: (s: Sort) => { setSort(s); setPage(1) } }
  const { data } = useQuery({
    queryKey: ['accounts', params],
    queryFn: () => api<Page<Account>>('/accounts', { params }),
    placeholderData: keepPreviousData,
  })

  return (
    <>
      <PageHeader
        title="Accounts"
        help="accounts-contacts"
        subtitle="Customers, prospects, platform partners and resellers"
        actions={
          <>
            <Button variant="default" leftSection={<IconDownload size={16} />} onClick={() => download('/export/accounts', { q: debounced, account_type: types })}>
              Export
            </Button>
            {canWrite && (
              <Button leftSection={<IconPlus size={16} />} onClick={open}>
                New account
              </Button>
            )}
          </>
        }
      />
      <Card withBorder p={0}>
        <Group p="sm" gap="sm">
          <TextInput placeholder="Search name or domain" leftSection={<IconSearch size={16} />} value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} w={280} />
          <MultiSelect placeholder="Type" data={toOptions(ACCOUNT_TYPES)} value={types} onChange={(v) => { setTypes(v); setPage(1) }} clearable w={320} />
        </Group>
        <Table.ScrollContainer minWidth={760}>
          <Table highlightOnHover verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <SortTh label="Name" sortKey="name" {...th} />
                <SortTh label="Type" sortKey="account_type" {...th} />
                <SortTh label="Domain" sortKey="domain" {...th} />
                <SortTh label="Country" sortKey="country" {...th} />
                <SortTh label="Contacts" sortKey="contacts" firstDesc {...th} />
                <SortTh label="Open deals" sortKey="open_deals" firstDesc {...th} info="Opportunities of this account not yet won or lost." />
                <SortTh label="Owner" sortKey="owner" {...th} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data?.items.map((a) => (
                <Table.Tr key={a.id} className="clickable-row" onClick={() => nav(`/accounts/${a.id}`)}>
                  <Table.Td fw={500}>{a.name}</Table.Td>
                  <Table.Td>
                    <AccountTypeBadge value={a.account_type} />
                  </Table.Td>
                  <Table.Td>{a.domain}</Table.Td>
                  <Table.Td>{a.country}</Table.Td>
                  <Table.Td>{a.contact_count}</Table.Td>
                  <Table.Td>{a.open_opportunity_count}</Table.Td>
                  <Table.Td>{a.owner?.full_name}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Group px="sm" pb="sm" display="block">
          <Pager page={page} total={data?.total ?? 0} pageSize={50} onChange={setPage} />
        </Group>
      </Card>
      <AccountFormModal opened={opened} onClose={close} onSaved={(a) => nav(`/accounts/${a.id}`)} />
    </>
  )
}
