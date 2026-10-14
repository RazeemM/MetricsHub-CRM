import { Anchor, Badge, Button, Card, Grid, Group, Modal, SimpleGrid, Stack, Text, Textarea, Title, Tooltip, UnstyledButton } from '@mantine/core'
import { modals } from '@mantine/modals'
import { IconCheck, IconEdit, IconTrash, IconX } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Activities } from '../components/Activities'
import { Quotes } from '../components/Quotes'
import { Field, PageHeader } from '../components/common'
import { fromLineItem, LineItemsEditor } from '../components/LineItemsEditor'
import { useApiMutation, usePipelines } from '../hooks'
import { DEAL_TYPES, fmtDate, LEAD_SOURCES, money, ROUTES } from '../labels'
import type { Opportunity, Stage } from '../types'

export function StageBar({ opp, onMove, disabled }: { opp: Opportunity; onMove: (s: Stage) => void; disabled?: boolean }) {
  const { data: pipelines } = usePipelines()
  const pipeline = pipelines?.find((p) => p.id === opp.pipeline_id)
  if (!pipeline) return null
  const open = pipeline.stages.filter((s) => s.kind === 'open')
  const current = pipeline.stages.find((s) => s.id === opp.stage_id)
  const idx = open.findIndex((s) => s.id === opp.stage_id)
  return (
    <Group gap={4} wrap="nowrap" style={{ overflowX: 'auto' }}>
      {open.map((s, i) => {
        const reached = current?.kind === 'won' || (idx >= 0 && i <= idx)
        return (
          <UnstyledButton
            key={s.id}
            disabled={disabled}
            onClick={() => onMove(s)}
            style={{
              flex: 1,
              minWidth: 110,
              padding: '8px 10px',
              textAlign: 'center',
              borderRadius: 6,
              fontSize: 13,
              fontWeight: s.id === opp.stage_id ? 700 : 500,
              background: reached ? 'var(--mantine-color-violet-filled)' : 'var(--mantine-color-default-hover)',
              color: reached ? 'white' : undefined,
            }}
          >
            {s.name}
          </UnstyledButton>
        )
      })}
      {current && current.kind !== 'open' && (
        <Badge size="xl" color={current.kind === 'won' ? 'green' : 'gray'} style={{ flex: '0 0 auto' }}>
          {current.name}
        </Badge>
      )}
    </Group>
  )
}

export default function OpportunityDetail() {
  const id = Number(useParams().id)
  const nav = useNavigate()
  const { canWrite, isAdmin } = useAuth()
  const { data: pipelines } = usePipelines()
  const { data: o } = useQuery({ queryKey: ['opportunity', id], queryFn: () => api<Opportunity>(`/opportunities/${id}`) })
  const [lostOpen, setLostOpen] = useState(false)
  const [lostReason, setLostReason] = useState('')
  const inv = [['opportunity'], ['opportunities'], ['board'], ['dashboard'], ['accounts'], ['account']]
  const move = useApiMutation(
    (body: { stage_id: number; lost_reason?: string }) => api<Opportunity>(`/opportunities/${id}/stage`, { method: 'POST', body }),
    { invalidate: inv, success: 'Stage updated', onSuccess: () => setLostOpen(false) },
  )
  const remove = useApiMutation(() => api(`/opportunities/${id}`, { method: 'DELETE' }), {
    invalidate: inv,
    success: 'Opportunity deleted',
    onSuccess: () => nav('/opportunities'),
  })
  if (!o) return null
  const pipeline = pipelines?.find((p) => p.id === o.pipeline_id)
  const won = pipeline?.stages.find((s) => s.kind === 'won')
  const lost = pipeline?.stages.find((s) => s.kind === 'lost')

  return (
    <>
      <PageHeader
        title={o.title}
        subtitle={
          <>
            <Anchor component={Link} to={`/accounts/${o.account.id}`} size="sm">
              {o.account.name}
            </Anchor>{' '}
            · {o.brand.name} · {DEAL_TYPES[o.deal_type]} deal · {pipeline?.name} pipeline
          </>
        }
        actions={
          canWrite && (
            <>
              {o.stage.kind === 'open' && won && (
                <Button color="green" leftSection={<IconCheck size={16} />} onClick={() => move.mutate({ stage_id: won.id })}>
                  Mark won
                </Button>
              )}
              {o.stage.kind === 'open' && lost && (
                <Button color="gray" variant="light" leftSection={<IconX size={16} />} onClick={() => setLostOpen(true)}>
                  Mark lost
                </Button>
              )}
              <Button component={Link} to={`/opportunities/${id}/edit`} variant="default" leftSection={<IconEdit size={16} />}>
                Edit
              </Button>
              <Button
                variant="subtle"
                color="red"
                onClick={() =>
                  modals.openConfirmModal({
                    title: 'Delete opportunity?',
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
      <Card withBorder mb="md" p="xs">
        <StageBar opp={o} disabled={!canWrite} onMove={(s) => move.mutate({ stage_id: s.id })} />
      </Card>
      <Grid>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Stack>
            <Card withBorder>
              <SimpleGrid cols={2} spacing="sm">
                <Field label="Deal value (TCV)">
                  <Text fw={700} size="lg">
                    {money(o.amount_tcv, o.currency)}
                  </Text>
                </Field>
                <Field label="ARR">
                  <Text fw={700} size="lg">
                    {money(o.amount_arr, o.currency)}
                  </Text>
                </Field>
                <Field label="Probability">
                  <Tooltip label={o.probability !== null ? 'Manual override' : 'From stage'}>
                    <span>{o.effective_probability}%</span>
                  </Tooltip>
                </Field>
                <Field label="Weighted">{money(o.weighted_amount, o.currency)}</Field>
                <Field label="Expected close">{fmtDate(o.expected_close_date)}</Field>
                <Field label="Owner">{o.owner?.full_name}</Field>
                <Field label="Contract">
                  {o.contract_start ? `${fmtDate(o.contract_start)} → ${fmtDate(o.contract_end)}` : null}
                </Field>
                <Field label="Term">{o.term_months} months</Field>
                <Field label="Primary contact">
                  {o.primary_contact && (
                    <Anchor component={Link} to={`/contacts/${o.primary_contact.id}`} size="sm">
                      {o.primary_contact.full_name}
                    </Anchor>
                  )}
                </Field>
                <Field label="Next step">{o.next_step}</Field>
              </SimpleGrid>
              {o.lost_reason && (
                <Text size="sm" c="red" mt="sm">
                  Lost reason: {o.lost_reason}
                </Text>
              )}
            </Card>
            <Card withBorder>
              <Title order={6} mb="xs">
                Source &amp; channel
              </Title>
              <SimpleGrid cols={2} spacing="sm">
                <Field label="Lead source">{o.lead_source ? LEAD_SOURCES[o.lead_source] : null}</Field>
                <Field label="Route to market">{ROUTES[o.route_to_market]}</Field>
                <Field label="Referring platform">
                  {o.referring_platform && (
                    <Anchor component={Link} to={`/accounts/${o.referring_platform.id}`} size="sm">
                      {o.referring_platform.name}
                    </Anchor>
                  )}
                </Field>
                <Field label="Platform account manager">
                  {o.partner_contact && (
                    <Anchor component={Link} to={`/contacts/${o.partner_contact.id}`} size="sm">
                      {o.partner_contact.full_name}
                    </Anchor>
                  )}
                </Field>
                {o.reseller && <Field label="Reseller">{o.reseller.name}</Field>}
              </SimpleGrid>
            </Card>
            {o.description && (
              <Card withBorder>
                <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                  {o.description}
                </Text>
              </Card>
            )}
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Stack>
            <Card withBorder>
              <Title order={5} mb="xs">
                Products
              </Title>
              {o.line_items.length ? (
                <LineItemsEditor lines={o.line_items.map(fromLineItem)} onChange={() => {}} products={[]} term={o.term_months} currency={o.currency} readOnly />
              ) : (
                <Text size="sm" c="dimmed">
                  No products yet. Edit the opportunity to add them.
                </Text>
              )}
            </Card>
            <Card withBorder>
              <Title order={5} mb="xs">
                Quotes
              </Title>
              <Quotes opportunityId={id} hasLines={o.line_items.length > 0} isAdmin={isAdmin} />
            </Card>
            <Card withBorder>
              <Title order={5} mb="xs">
                Activity
              </Title>
              <Activities link={{ opportunity_id: id }} />
            </Card>
          </Stack>
        </Grid.Col>
      </Grid>
      <Modal opened={lostOpen} onClose={() => setLostOpen(false)} title="Mark as lost">
        <Stack>
          <Textarea label="Lost reason" required value={lostReason} onChange={(e) => setLostReason(e.target.value)} placeholder="Price, competitor, no budget, timing…" />
          <Group justify="flex-end">
            <Button color="gray" disabled={!lostReason.trim()} loading={move.isPending} onClick={() => lost && move.mutate({ stage_id: lost.id, lost_reason: lostReason })}>
              Mark lost
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  )
}
