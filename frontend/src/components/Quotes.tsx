import { ActionIcon, Badge, Button, Group, Modal, NumberInput, Select, Stack, Table, Text, Textarea, Tooltip } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconDownload, IconEye, IconFileInvoice, IconTrash } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, getToken } from '../api'
import { useAuth } from '../auth'
import { useApiMutation } from '../hooks'
import { fmtDate, money } from '../labels'

interface QuoteRow {
  id: number
  display_number: string
  version: number
  status: string
  issue_date: string
  valid_until: string
  currency: string
  amount_tcv: string
  created_by: string | null
  line_count: number
}

const STATUS = [
  { value: 'draft', label: 'Draft', color: 'gray' },
  { value: 'sent', label: 'Sent', color: 'blue' },
  { value: 'accepted', label: 'Accepted', color: 'green' },
  { value: 'rejected', label: 'Rejected', color: 'red' },
  { value: 'expired', label: 'Expired', color: 'orange' },
]

async function openPdf(id: number, downloadIt: boolean, name: string) {
  const res = await fetch(`/api/quotes/${id}/pdf`, { headers: { Authorization: `Bearer ${getToken()}` } })
  if (!res.ok) {
    notifications.show({ color: 'red', message: 'Could not render the PDF' })
    return
  }
  const url = URL.createObjectURL(await res.blob())
  if (downloadIt) {
    const a = document.createElement('a')
    a.href = url
    a.download = `${name.replace(' ', '-')}.pdf`
    a.click()
  } else window.open(url, '_blank')
}

export function Quotes({ opportunityId, hasLines, isAdmin }: { opportunityId: number; hasLines: boolean; isAdmin?: boolean }) {
  const { canWrite } = useAuth()
  const key = ['quotes', opportunityId]
  const { data } = useQuery({ queryKey: key, queryFn: () => api<QuoteRow[]>(`/opportunities/${opportunityId}/quotes`) })
  const [open, setOpen] = useState(false)
  const [validDays, setValidDays] = useState<number | ''>('')
  const [notes, setNotes] = useState('')

  const create = useApiMutation(
    () => api<QuoteRow>(`/opportunities/${opportunityId}/quotes`, { method: 'POST', body: { valid_days: validDays || null, notes: notes || null } }),
    {
      invalidate: [key],
      success: 'Quote generated',
      onSuccess: (q) => {
        setOpen(false)
        setNotes('')
        openPdf(q.id, false, q.display_number)
      },
    },
  )
  const status = useApiMutation((v: { id: number; status: string }) => api(`/quotes/${v.id}`, { method: 'PATCH', body: { status: v.status } }), {
    invalidate: [key],
  })
  const remove = useApiMutation((id: number) => api(`/quotes/${id}`, { method: 'DELETE' }), { invalidate: [key], success: 'Draft deleted' })

  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          Each quote freezes the products, prices and template at the time it is generated. A new quote on the same deal becomes the next version.
        </Text>
        {canWrite && (
          <Tooltip label="Add products first" disabled={hasLines}>
            <Button leftSection={<IconFileInvoice size={16} />} onClick={() => setOpen(true)} disabled={!hasLines}>
              Generate quote
            </Button>
          </Tooltip>
        )}
      </Group>
      {data?.length ? (
        <Table.ScrollContainer minWidth={640}>
          <Table verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Quote</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Issued</Table.Th>
                <Table.Th>Valid until</Table.Th>
                <Table.Th ta="right">Total</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.map((q) => {
                const expired = q.status !== 'accepted' && new Date(`${q.valid_until}T23:59:59`) < new Date()
                return (
                  <Table.Tr key={q.id}>
                    <Table.Td fw={600}>{q.display_number}</Table.Td>
                    <Table.Td>
                      {canWrite ? (
                        <Select
                          size="xs"
                          w={120}
                          data={STATUS}
                          value={q.status}
                          allowDeselect={false}
                          onChange={(v) => v && status.mutate({ id: q.id, status: v })}
                        />
                      ) : (
                        <Badge color={STATUS.find((s) => s.value === q.status)?.color}>{q.status}</Badge>
                      )}
                    </Table.Td>
                    <Table.Td>{fmtDate(q.issue_date)}</Table.Td>
                    <Table.Td c={expired ? 'red' : undefined}>{fmtDate(q.valid_until)}</Table.Td>
                    <Table.Td ta="right">{money(q.amount_tcv, q.currency)}</Table.Td>
                    <Table.Td>
                      <Group gap={4} justify="flex-end" wrap="nowrap">
                        <ActionIcon variant="subtle" onClick={() => openPdf(q.id, false, q.display_number)} aria-label="View PDF">
                          <IconEye size={16} />
                        </ActionIcon>
                        <ActionIcon variant="subtle" onClick={() => openPdf(q.id, true, q.display_number)} aria-label="Download PDF">
                          <IconDownload size={16} />
                        </ActionIcon>
                        {canWrite && q.status === 'draft' && (
                          <ActionIcon variant="subtle" color="red" onClick={() => remove.mutate(q.id)} aria-label="Delete draft">
                            <IconTrash size={16} />
                          </ActionIcon>
                        )}
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                )
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      ) : (
        <Text size="sm" c="dimmed">
          No quotes yet.
        </Text>
      )}
      <Modal opened={open} onClose={() => setOpen(false)} title="Generate quote">
        <Stack>
          <Text size="sm">
            Uses the products and prices currently on this opportunity, the primary contact and the brand's quote template
            {isAdmin && (
              <>
                {' '}
                (<Link to="/quote-templates">edit template</Link>)
              </>
            )}
            .
          </Text>
          <NumberInput label="Valid for (days)" placeholder="Template default" min={1} max={365} value={validDays} onChange={(v) => setValidDays(v === '' ? '' : Number(v))} />
          <Textarea label="Notes printed on this quote" autosize minRows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          <Group justify="flex-end">
            <Button loading={create.isPending} onClick={() => create.mutate(undefined)}>
              Generate PDF
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
