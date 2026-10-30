import { Alert, Anchor, Badge, Button, Checkbox, Group, Modal, ScrollArea, SegmentedControl, SimpleGrid, Stack, Table, Text, Textarea, TextInput } from '@mantine/core'
import { DateInput } from '@mantine/dates'
import { IconAlertTriangle, IconClipboardText } from '@tabler/icons-react'
import dayjs from 'dayjs'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApiMutation } from '../hooks'
import { DEAL_TYPES, fmtDate, money2 } from '../labels'
import type { Opportunity } from '../types'
import { AccountPicker } from './common'

interface QuoteLine {
  name: string
  quantity: string
  start: string
  end: string
  term_months: number
  total_charge: string
  discount_pct: string
  list_price: string | null
  effective_price: string | null
  status: string | null
  action: string
}

interface QuotePreview {
  quote_number: string | null
  customer: string | null
  account: { id: number; name: string } | null
  currency: string
  line_count: number
  quote_total: string
  sentry_total: string
  contract_start: string
  contract_end: string
  deal_type: string
  sales_rep: { name: string; contact_id: number | null } | null
  approvals: { step: string; status: string; date: string; assigned_to: string }[]
  existing: { id: number; title: string } | null
  lines: QuoteLine[]
}

/** Paste a BMC quote approval email: its Sentry product lines become a new Sentry opportunity sold through BMC. */
export function BmcQuoteImport({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const nav = useNavigate()
  const [text, setText] = useState('')
  const [p, setP] = useState<QuotePreview | null>(null)
  const [accountId, setAccountId] = useState<number | null>(null)
  const [accountName, setAccountName] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [dealType, setDealType] = useState('new')
  const [close, setClose] = useState<Date | null>(null)
  const [skip, setSkip] = useState<number[]>([])

  const reset = () => {
    setText('')
    setP(null)
    setAccountId(null)
    setAccountName(null)
    setTitle('')
    setSkip([])
  }
  const done = () => {
    reset()
    onClose()
  }
  const read = useApiMutation((t: string) => api<QuotePreview>('/opportunities/bmc-quote/preview', { method: 'POST', body: { text: t } }), {
    onSuccess: (r) => {
      setP(r)
      setAccountId(r.account?.id ?? null)
      setAccountName(r.account?.name ?? null)
      setDealType(r.deal_type)
      setClose(dayjs(r.contract_start).toDate())
      setSkip([])
    },
  })
  const create = useApiMutation(
    () =>
      api<Opportunity>('/opportunities/bmc-quote', {
        method: 'POST',
        body: { text, account_id: accountId, title: title.trim() || null, deal_type: dealType, expected_close_date: close ? dayjs(close).format('YYYY-MM-DD') : null, skip },
      }),
    {
      invalidate: [['opportunities'], ['board']],
      success: 'Opportunity created from the BMC quote',
      onSuccess: (o) => {
        done()
        nav(`/opportunities/${o.id}`)
      },
    },
  )

  const kept = p ? p.lines.filter((_, i) => !skip.includes(i)) : []
  const keptTotal = kept.reduce((s, l) => s + Number(l.total_charge), 0)
  const suffix = p?.quote_number ? ` ${p.quote_number}` : ''

  return (
    <Modal opened={opened} onClose={done} title="New opportunity from a BMC quote" size={p ? 'xl' : 'lg'}>
      {!p ? (
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            Open the quote approval email, select all of it (Ctrl+A), copy it and paste it here. The Sentry products are picked out of the quote; the BMC products are left out.
          </Text>
          <Textarea
            placeholder="Paste the quote: Approvals List, Product Details - General Information, Additional Pricing Information…"
            autosize
            minRows={10}
            maxRows={18}
            value={text}
            onChange={(e) => setText(e.target.value)}
            styles={{ input: { fontFamily: 'monospace', fontSize: 12 } }}
            data-autofocus
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={done}>
              Cancel
            </Button>
            <Button leftSection={<IconClipboardText size={16} />} disabled={!text.trim()} loading={read.isPending} onClick={() => read.mutate(text)}>
              Read quote
            </Button>
          </Group>
        </Stack>
      ) : (
        <Stack gap="sm">
          {p.existing && (
            <Alert color="orange" icon={<IconAlertTriangle size={18} />}>
              This quote was already imported as{' '}
              <Anchor component={Link} to={`/opportunities/${p.existing.id}`} onClick={done}>
                {p.existing.title}
              </Anchor>
              .
            </Alert>
          )}
          <Text size="sm">
            <b>{p.lines.length}</b> Sentry product{p.lines.length === 1 ? '' : 's'} out of the quote's {p.line_count} lines: {money2(p.sentry_total, p.currency)} of {money2(p.quote_total, p.currency)} in total charges.
            {p.quote_number && <> Quote {p.quote_number}.</>}
          </Text>
          <ScrollArea type="auto" offsetScrollbars>
            <Table withTableBorder fz="sm" verticalSpacing={6} miw={720}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w={36} />
                  <Table.Th>Product</Table.Th>
                  <Table.Th ta="right">Qty</Table.Th>
                  <Table.Th>Period</Table.Th>
                  <Table.Th ta="right">Discount</Table.Th>
                  <Table.Th ta="right">Total charge</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {p.lines.map((l, i) => (
                  <Table.Tr key={i} style={{ opacity: skip.includes(i) ? 0.45 : 1 }}>
                    <Table.Td>
                      <Checkbox
                        aria-label={`Keep ${l.name}`}
                        checked={!skip.includes(i)}
                        onChange={(e) => setSkip(e.currentTarget.checked ? skip.filter((x) => x !== i) : [...skip, i])}
                      />
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{l.name}</Text>
                      <Group gap={4} mt={2}>
                        {l.status && (
                          <Badge size="xs" variant="light" color={l.status === 'Generally Available' ? 'green' : 'orange'}>
                            {l.status}
                          </Badge>
                        )}
                        {l.action && (
                          <Badge size="xs" variant="outline" color="gray">
                            {l.action}
                          </Badge>
                        )}
                        {l.list_price && (
                          <Text size="xs" c="dimmed">
                            list {money2(l.list_price, p.currency)} · effective {money2(l.effective_price, p.currency)} per unit
                          </Text>
                        )}
                      </Group>
                    </Table.Td>
                    <Table.Td ta="right">{Number(l.quantity).toLocaleString('en-US')}</Table.Td>
                    <Table.Td style={{ whiteSpace: 'nowrap' }}>
                      {fmtDate(l.start)} – {fmtDate(l.end)}
                      <Text size="xs" c="dimmed">
                        {l.term_months} months
                      </Text>
                    </Table.Td>
                    <Table.Td ta="right">{Number(l.discount_pct)}%</Table.Td>
                    <Table.Td ta="right">{money2(l.total_charge, p.currency)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
          <Text size="sm" ta="right">
            Opportunity value: <b>{money2(keptTotal, p.currency)}</b>
          </Text>

          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <AccountPicker
              label="Customer account"
              description={p.customer && !p.account ? `The quote names “${p.customer}”, which isn't an account yet` : undefined}
              required
              allowCreate
              value={accountId}
              initialLabel={accountName}
              onChange={(id) => setAccountId(id)}
              placeholder="Search accounts"
            />
            <TextInput
              label="Title"
              placeholder={`<account> - Sentry via BMC${suffix}`}
              description="Empty: the account name followed by “Sentry via BMC”"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <div>
              <Text size="sm" fw={500} mb={4}>
                Deal type
              </Text>
              <SegmentedControl fullWidth value={dealType} onChange={setDealType} data={Object.entries(DEAL_TYPES).map(([value, label]) => ({ value, label }))} />
            </div>
            <DateInput label="Expected close" value={close} onChange={(d) => setClose(d ? dayjs(d as unknown as Date).toDate() : null)} valueFormat="DD MMM YYYY" clearable />
          </SimpleGrid>
          <Text size="xs" c="dimmed">
            Sentry Software brand, sold through BMC MarketZone, referred by BMC
            {p.sales_rep && (p.sales_rep.contact_id ? `, BMC sales rep ${p.sales_rep.name} as partner contact` : ` (BMC sales rep ${p.sales_rep.name} isn't a contact yet)`)}. Contract {fmtDate(p.contract_start)} – {fmtDate(p.contract_end)}. The approvals are kept in a note on the opportunity.
          </Text>
          <Group justify="space-between">
            <Button variant="subtle" onClick={() => setP(null)}>
              Back to the text
            </Button>
            <Group>
              <Button variant="default" onClick={done}>
                Cancel
              </Button>
              <Button disabled={!accountId || !kept.length || !!p.existing} loading={create.isPending} onClick={() => create.mutate()}>
                Create opportunity
              </Button>
            </Group>
          </Group>
        </Stack>
      )}
    </Modal>
  )
}
