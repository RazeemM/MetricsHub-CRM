import { DragDropContext, Draggable, Droppable, type DropResult } from '@hello-pangea/dnd'
import { Badge, Button, Card, Group, Modal, SegmentedControl, Select, Stack, Text, Textarea } from '@mantine/core'
import { IconPlus } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { PageHeader } from '../components/common'
import { useApiMutation, useBrands, usePipelines, usePlatforms, useUsers } from '../hooks'
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
  const { canWrite } = useAuth()
  const { data: pipelines } = usePipelines()
  const { data: brands } = useBrands()
  const { data: users } = useUsers()
  const { data: platforms } = usePlatforms()
  const [pipelineId, setPipelineId] = useState<string | null>(null)
  const [brandId, setBrandId] = useState<string | null>(null)
  const [ownerId, setOwnerId] = useState<string | null>(null)
  const [platformId, setPlatformId] = useState<string | null>(null)
  const [pendingLost, setPendingLost] = useState<{ oppId: number; stageId: number } | null>(null)
  const [reason, setReason] = useState('')
  const pid = pipelineId ?? (pipelines?.[0] ? String(pipelines[0].id) : null)
  const params = { pipeline_id: pid ?? undefined, brand_id: brandId ?? undefined, owner_id: ownerId ?? undefined, referring_platform_id: platformId ?? undefined }
  const key = ['board', params]
  const { data } = useQuery({ queryKey: key, queryFn: () => api<Board>('/opportunities/board', { params }), enabled: !!pid })

  const move = useApiMutation(
    (v: { oppId: number; stageId: number; lost_reason?: string }) =>
      api(`/opportunities/${v.oppId}/stage`, { method: 'POST', body: { stage_id: v.stageId, lost_reason: v.lost_reason } }),
    {
      invalidate: [['board'], ['dashboard'], ['opportunities'], ['opportunity']],
      onSuccess: () => {
        setPendingLost(null)
        setReason('')
      },
    },
  )

  const onDragEnd = (r: DropResult) => {
    if (!r.destination || !data || r.destination.droppableId === r.source.droppableId) return
    const stageId = Number(r.destination.droppableId)
    const oppId = Number(r.draggableId)
    const col = data.columns.find((c) => c.stage.id === stageId)
    if (col?.stage.kind === 'lost') {
      setPendingLost({ oppId, stageId })
      return
    }
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
      <PageHeader
        title="Pipeline"
        actions={
          canWrite && (
            <Button component={Link} to="/opportunities/new" leftSection={<IconPlus size={16} />}>
              New opportunity
            </Button>
          )
        }
      />
      <Group mb="md" gap="sm">
        <SegmentedControl data={(pipelines ?? []).map((p) => ({ value: String(p.id), label: p.name }))} value={pid ?? ''} onChange={setPipelineId} />
        <Select placeholder="All brands" data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))} value={brandId} onChange={setBrandId} clearable w={180} />
        <Select placeholder="All owners" data={(users ?? []).map((u) => ({ value: String(u.id), label: u.full_name }))} value={ownerId} onChange={setOwnerId} clearable searchable w={180} />
        <Select
          placeholder="All platforms"
          data={(platforms?.items ?? []).map((a) => ({ value: String(a.id), label: a.name }))}
          value={platformId}
          onChange={setPlatformId}
          clearable
          w={220}
        />
      </Group>
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
                        <Badge size="sm" variant="light" color={col.stage.kind === 'won' ? 'green' : col.stage.kind === 'lost' ? 'gray' : 'violet'}>
                          {col.count}
                        </Badge>
                      </Group>
                      <Text size="xs" c="dimmed">
                        {currencies.length > 1 ? 'mixed currencies' : money(col.total, currencies[0] ?? 'USD')} · {col.stage.probability}%
                      </Text>
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
      <Modal opened={!!pendingLost} onClose={() => setPendingLost(null)} title="Why was this deal lost?">
        <Stack>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Price, competitor, no budget, timing…" data-autofocus />
          <Group justify="flex-end">
            <Button
              disabled={!reason.trim()}
              loading={move.isPending}
              onClick={() => pendingLost && move.mutate({ ...pendingLost, lost_reason: reason })}
            >
              Mark lost
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  )
}
