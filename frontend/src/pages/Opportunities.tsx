import { Badge, Button, Card, Group, SegmentedControl, Select, Table, TextInput } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { IconDownload, IconPlus, IconSearch } from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, download } from '../api'
import { useAuth } from '../auth'
import { PageHeader, Pager } from '../components/common'
import { SortTh, type Sort } from '../components/ui'
import { useBrands, usePlatforms } from '../hooks'
import { fmtDate, money } from '../labels'
import type { Opportunity, Page } from '../types'

export default function Opportunities() {
  const nav = useNavigate()
  const { canWrite } = useAuth()
  const { data: brands } = useBrands()
  const { data: platforms } = usePlatforms()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('open')
  const [brandId, setBrandId] = useState<string | null>(null)
  const [platformId, setPlatformId] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<Sort>({ key: 'updated_at', desc: true })
  const [debounced] = useDebouncedValue(q, 250)
  const th = { sort, onSort: (s: Sort) => { setSort(s); setPage(1) } }
  const params = {
    q: debounced,
    status: status === 'all' ? undefined : status,
    brand_id: brandId ?? undefined,
    referring_platform_id: platformId ?? undefined,
    sort: sort.key,
    desc: sort.desc,
    page,
    page_size: 50,
  }
  const { data } = useQuery({
    queryKey: ['opportunities', params],
    queryFn: () => api<Page<Opportunity>>('/opportunities', { params }),
    placeholderData: keepPreviousData,
  })

  return (
    <>
      <PageHeader
        title="Opportunities"
        help="opportunities"
        actions={
          <>
            <Button variant="default" leftSection={<IconDownload size={16} />} onClick={() => download('/export/opportunities', { q: debounced, status: params.status, brand_id: params.brand_id })}>
              Export
            </Button>
            {canWrite && (
              <Button component={Link} to="/opportunities/new" leftSection={<IconPlus size={16} />}>
                New opportunity
              </Button>
            )}
          </>
        }
      />
      <Card withBorder p={0}>
        <Group p="sm" gap="sm">
          <TextInput placeholder="Search title or account" leftSection={<IconSearch size={16} />} value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} w={260} />
          <SegmentedControl
            value={status}
            onChange={(v) => { setStatus(v); setPage(1) }}
            data={[
              { value: 'open', label: 'Open' },
              { value: 'won', label: 'Won' },
              { value: 'lost', label: 'Lost' },
              { value: 'all', label: 'All' },
            ]}
          />
          <Select placeholder="All brands" data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))} value={brandId} onChange={setBrandId} clearable w={180} />
          <Select placeholder="All platforms" data={(platforms?.items ?? []).map((a) => ({ value: String(a.id), label: a.name }))} value={platformId} onChange={setPlatformId} clearable w={220} />
        </Group>
        <Table.ScrollContainer minWidth={980}>
          <Table highlightOnHover verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <SortTh label="Title" sortKey="title" {...th} />
                <SortTh label="Account" sortKey="account" {...th} />
                <SortTh label="Brand" sortKey="brand" {...th} />
                <SortTh label="Stage" sortKey="stage" {...th} info="Sorts in pipeline order, from New to Lost." />
                <SortTh label="Platform" sortKey="platform" {...th} info="The observability platform (BMC Helix, Datadog…) that referred the deal." />
                <SortTh label="TCV" sortKey="amount" ta="right" firstDesc {...th} info="Total contract value: every line item over the whole contract term." />
                <SortTh
                  label="Weighted"
                  sortKey="weighted"
                  ta="right"
                  firstDesc
                  {...th}
                  info="TCV × the win probability: the deal's own probability when set, otherwise its stage's."
                />
                <SortTh label="Close" sortKey="close" {...th} info="Expected close date. Deals without one come last." />
                <SortTh label="Owner" sortKey="owner" {...th} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data?.items.map((o) => (
                <Table.Tr key={o.id} className="clickable-row" onClick={() => nav(`/opportunities/${o.id}`)}>
                  <Table.Td fw={500}>{o.title}</Table.Td>
                  <Table.Td>{o.account.name}</Table.Td>
                  <Table.Td>{o.brand.name}</Table.Td>
                  <Table.Td>
                    <Badge variant="light" color={o.stage.kind === 'won' ? 'green' : o.stage.kind === 'lost' ? 'gray' : 'violet'}>
                      {o.stage.name}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{o.referring_platform?.name}</Table.Td>
                  <Table.Td ta="right">{money(o.amount_tcv, o.currency)}</Table.Td>
                  <Table.Td ta="right">{money(o.weighted_amount, o.currency)}</Table.Td>
                  <Table.Td>{fmtDate(o.expected_close_date)}</Table.Td>
                  <Table.Td>{o.owner?.full_name}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Group px="sm" pb="sm" display="block">
          <Pager page={page} total={data?.total ?? 0} pageSize={50} onChange={setPage} />
        </Group>
      </Card>
    </>
  )
}
