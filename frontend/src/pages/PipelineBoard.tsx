import { DragDropContext, Draggable, Droppable, type DropResult } from '@hello-pangea/dnd'
import { Badge, Button, Card, Group, SegmentedControl, Stack, Text, Tooltip } from '@mantine/core'
import { IconClipboardText, IconPlus } from '@tabler/icons-react'
import { useDebouncedValue } from '@mantine/hooks'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { BmcQuoteImport } from '../components/BmcQuoteImport'
import { PageHeader } from '../components/common'
import { boardParams, DEFAULT_FILTERS, PipelineViewBar, type ViewFilters } from '../components/PipelineViews'
import { useApiMutation, usePipelines } from '../hooks'
import { fmtDate, money } from '../labels'
import type { Ref, UserRef } from '../types'

interface BoardItem {
  id: number
  title: string
  account: Ref
  brand: Ref
  owner: UserRef | null
  amount_tcv: string
  currency: string
  expected_close_date: string | null
  referring_platform: Ref | null
  effective_probability: number
  next_step: string | null
  contract_end: string | null
}
interface Board {
  pipeline: { id: number; name: string; kind: string }
  columns: { stage: { id: number; name: string; probability: number; kind: string }; count: number; total: string; weighted: string; items: BoardItem[] }[]
}

export default function PipelineBoard() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const { canWrite, user } = useAuth()
  const { data: pipelines } = usePipelines()
  const [filters, setFilters] = useState<ViewFilters>(DEFAULT_FILTERS)
  const [quoteOpen, setQuoteOpen] = useState(false)
  const [debouncedQ] = useDebouncedValue(filters.q, 250)
  const known = pipelines?.some((p) => p.id === filters.pipeline_id)
  const pid = known ? String(filters.pipeline_id) : pipelines?.[0] ? String(pipelines[0].id) : null
  const params = boardParams({ ...filters, q: debouncedQ }, user?.id, pid)
  const key = ['board', params]
  const { data } = useQuery({ queryKey: key, queryFn: () => api<Board>('/opportunities/board', { params }), enabled: !!pid, placeholderData: keepPreviousData })

  const move = useApiMutation(
    (v: { oppId: number; stageId: number }) => api(`/opportunities/${v.oppId}/stage`, { method: 'POST', body: { stage_id: v.stageId } }),
    { invalidate: [['board'], ['dashboard'], ['opportunities'], ['opportunity']] },
  )

  const onDragEnd = (r: DropResult) => {
    if (!r.destination || !data || r.destination.droppableId === r.source.droppableId) return
    const stageId = Number(r.destination.droppableId)
    const oppId = Number(r.draggableId)
    // optimistic move
    qc.setQueryData<Board>(key, (b) => {
      if (!b) return b
      const item = b.columns.flatMap((c) => c.items).find((i) => i.id === oppId)
      if (!item) return b
      return {
        ...b,
        columns: b.columns.map((c) => ({
          ...c,
          items: c.stage.id === stageId ? [item, ...c.items.filter((i) => i.id !== oppId)] : c.items.filter((i) => i.id !== oppId),
        })),
      }
    })
    move.mutate({ oppId, stageId })
  }

  return (
    <>
      <BmcQuoteImport opened={quoteOpen} onClose={() => setQuoteOpen(false)} />
      <PageHeader
        title="Pipeline"
        help="pipeline"
        actions={
          canWrite && (
            <>
              <Button variant="default" leftSection={<IconClipboardText size={16} />} onClick={() => setQuoteOpen(true)}>
                Paste BMC quote
              </Button>
              <Button component={Link} to="/opportunities/new" leftSection={<IconPlus size={16} />}>
                New opportunity
              </Button>
            </>
          )
        }
      />
      <Group mb="xs" gap="sm">
        <SegmentedControl
          data={(pipelines ?? []).map((p) => ({ value: String(p.id), label: p.name }))}
          value={pid ?? ''}
          onChange={(v) => setFilters((f) => ({ ...f, pipeline_id: Number(v) }))}
        />
      </Group>
      <PipelineViewBar filters={filters} onFilters={setFilters} />
      <DragDropContext onDragEnd={onDragEnd}>
        <div className="kanban">
          {data?.columns.map((col) => {
            const currencies = [...new Set(col.items.map((i) => i.currency))]
            return (
              <Droppable droppableId={String(col.stage.id)} key={col.stage.id} isDropDisabled={!canWrite}>
                {(prov, snap) => (
                  <div ref={prov.innerRef} {...prov.droppableProps} className={`kanban-col${snap.isDraggingOver ? ' dragging-over' : ''}`}>
                    <Stack gap={2} mb="xs" px={4}>
                      <Group justify="space-between">
                        <Text fw={700} size="sm">
                          {col.stage.name}
                        </Text>
                        <Tooltip label={`${col.count} deal${col.count === 1 ? '' : 's'} in this stage, with the filters applied`} withArrow>
                          <Badge size="sm" variant="light" color={col.stage.kind === 'won' ? 'green' : col.stage.kind === 'lost' ? 'gray' : 'violet'}>
                            {col.count}
                          </Badge>
                        </Tooltip>
                      </Group>
                      <Tooltip
                        multiline
                        w={260}
                        withArrow
                        label={
                          currencies.length > 1
                            ? 'Deals in several currencies: totals are not added across currencies.'
                            : `Total value ${money(col.total, currencies[0] ?? 'USD')}, weighted ${money(col.weighted, currencies[0] ?? 'USD')}. ${col.stage.probability}% is the stage's win probability: weighted = value × probability (or the deal's own probability when set).`
                        }
                      >
                        <Text size="xs" c="dimmed" style={{ cursor: 'help' }}>
                          {currencies.length > 1 ? 'mixed currencies' : money(col.total, currencies[0] ?? 'USD')} · {col.stage.probability}%
                        </Text>
                      </Tooltip>
                    </Stack>
                    <Stack gap={6}>
                      {col.items.map((o, i) => (
                        <Draggable draggableId={String(o.id)} index={i} key={o.id} isDragDisabled={!canWrite}>
                          {(p) => (
                            <Card
                              ref={p.innerRef}
                              {...p.draggableProps}
                              {...p.dragHandleProps}
                              withBorder
                              padding="xs"
                              shadow="xs"
                              onClick={() => nav(`/opportunities/${o.id}`)}
                              style={{ ...p.draggableProps.style, cursor: 'pointer' }}
                            >
                              <Text size="sm" fw={600} lineClamp={2}>
                                {o.title}
                              </Text>
                              <Text size="xs" c="dimmed">
                                {o.account.name}
                              </Text>
                              <Group justify="space-between" mt={4}>
                                <Text size="sm" fw={700}>
                                  {money(o.amount_tcv, o.currency)}
                                </Text>
                                <Text size="xs" c="dimmed">
                                  {fmtDate(o.expected_close_date)}
                                </Text>
                              </Group>
                              <Group gap={4} mt={4}>
                                <Badge size="xs" variant="light" color={o.brand.name.startsWith('Sentry') ? 'orange' : 'violet'}>
                                  {o.brand.name}
                                </Badge>
                                {o.referring_platform && (
                                  <Badge size="xs" variant="outline" color="gray">
                                    via {o.referring_platform.name}
                                  </Badge>
                                )}
                              </Group>
                            </Card>
                          )}
                        </Draggable>
                      ))}
                      {prov.placeholder}
                    </Stack>
                  </div>
                )}
              </Droppable>
            )
          })}
        </div>
      </DragDropContext>
    </>
  )
}
