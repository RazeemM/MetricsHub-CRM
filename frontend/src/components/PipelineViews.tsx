import { ActionIcon, Badge, Button, CloseButton, Divider, Drawer, Group, Menu, Modal, MultiSelect, NumberInput, Select, Stack, Switch, Text, TextInput, Tooltip } from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import { modals } from '@mantine/modals'
import { IconAdjustmentsHorizontal, IconDots, IconDeviceFloppy, IconPencil, IconSearch, IconShare, IconTrash, IconUsers } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { useApiMutation, useBrands, usePlatforms, useUsers } from '../hooks'
import { DEAL_TYPES, LEAD_SOURCES, ROUTES, money, toOptions } from '../labels'
import { InfoTip } from './ui'

export type ClosePreset = 'any' | 'overdue' | 'this_month' | 'next_month' | 'this_quarter' | 'next_90_days' | 'this_year' | 'none' | 'custom'

export interface ViewFilters {
  pipeline_id: number | null
  q: string
  mine: boolean
  owner_ids: number[]
  brand_ids: number[]
  platform_ids: number[]
  deal_types: string[]
  routes: string[]
  lead_sources: string[]
  close: ClosePreset
  close_from: string | null
  close_to: string | null
  min_amount: string | null
  max_amount: string | null
  hide_closed: boolean
  sort: 'close' | 'amount' | 'updated' | 'created' | 'title' | 'account'
}

export interface SavedView {
  id: number
  name: string
  shared: boolean
  filters: ViewFilters
  owner_id: number
  owner_name: string | null
  editable: boolean
}

export const DEFAULT_FILTERS: ViewFilters = {
  pipeline_id: null,
  q: '',
  mine: false,
  owner_ids: [],
  brand_ids: [],
  platform_ids: [],
  deal_types: [],
  routes: [],
  lead_sources: [],
  close: 'any',
  close_from: null,
  close_to: null,
  min_amount: null,
  max_amount: null,
  hide_closed: false,
  sort: 'close',
}

/** Views everyone has; they cannot be changed, but can be saved under a new name once adjusted. */
export const BUILT_IN: { key: string; name: string; filters: ViewFilters }[] = [
  { key: 'all', name: 'All deals', filters: DEFAULT_FILTERS },
  { key: 'mine', name: 'My deals', filters: { ...DEFAULT_FILTERS, mine: true } },
  { key: 'closing', name: 'Closing this quarter', filters: { ...DEFAULT_FILTERS, close: 'this_quarter', hide_closed: true } },
]

export const CLOSE_PRESETS: { value: ClosePreset; label: string }[] = [
  { value: 'any', label: 'Any date' },
  { value: 'overdue', label: 'Overdue (date passed)' },
  { value: 'this_month', label: 'This month' },
  { value: 'next_month', label: 'Next month' },
  { value: 'this_quarter', label: 'This quarter' },
  { value: 'next_90_days', label: 'Next 90 days' },
  { value: 'this_year', label: 'This year' },
  { value: 'none', label: 'No close date' },
  { value: 'custom', label: 'Between dates…' },
]

export const SORTS = [
  { value: 'close', label: 'Close date (soonest)' },
  { value: 'amount', label: 'Value (largest)' },
  { value: 'updated', label: 'Recently updated' },
  { value: 'created', label: 'Newest' },
  { value: 'title', label: 'Title (A–Z)' },
  { value: 'account', label: 'Account (A–Z)' },
]

/** Saved filters may predate a field: fill in the defaults. */
export const normalize = (f: Partial<ViewFilters> | undefined): ViewFilters => ({ ...DEFAULT_FILTERS, ...(f ?? {}) })

const fmt = (d: dayjs.Dayjs) => d.format('YYYY-MM-DD')

/** Relative presets resolve against today, so a saved "This quarter" view stays current. */
export function closeRange(f: ViewFilters, today = dayjs()): { close_from?: string; close_to?: string; no_close_date?: boolean } {
  const q0 = today.month(Math.floor(today.month() / 3) * 3).startOf('month')
  switch (f.close) {
    case 'overdue':
      return { close_to: fmt(today.subtract(1, 'day')) }
    case 'this_month':
      return { close_from: fmt(today.startOf('month')), close_to: fmt(today.endOf('month')) }
    case 'next_month': {
      const m = today.add(1, 'month')
      return { close_from: fmt(m.startOf('month')), close_to: fmt(m.endOf('month')) }
    }
    case 'this_quarter':
      return { close_from: fmt(q0), close_to: fmt(q0.add(2, 'month').endOf('month')) }
    case 'next_90_days':
      return { close_from: fmt(today), close_to: fmt(today.add(90, 'day')) }
    case 'this_year':
      return { close_from: fmt(today.startOf('year')), close_to: fmt(today.endOf('year')) }
    case 'none':
      return { no_close_date: true }
    case 'custom':
      return { close_from: f.close_from ?? undefined, close_to: f.close_to ?? undefined }
    default:
      return {}
  }
}

export function boardParams(f: ViewFilters, userId: number | undefined, pipelineId: string | null) {
  return {
    pipeline_id: pipelineId ?? undefined,
    q: f.q.trim() || undefined,
    owner_id: f.mine ? (userId ? [userId] : []) : f.owner_ids,
    brand_id: f.brand_ids,
    referring_platform_id: f.platform_ids,
    deal_type: f.deal_types,
    route_to_market: f.routes,
    lead_source: f.lead_sources,
    ...closeRange(f),
    min_amount: f.min_amount ?? undefined,
    max_amount: f.max_amount ?? undefined,
    hide_closed: f.hide_closed || undefined,
    sort: f.sort,
  }
}

/** Filters that differ from the defaults, as removable chips. The pipeline and the card order are not filters. */
export function activeChips(f: ViewFilters, names: { users: Map<number, string>; brands: Map<number, string>; platforms: Map<number, string> }) {
  const chips: { key: string; label: string; clear: Partial<ViewFilters> }[] = []
  const list = (ids: number[], m: Map<number, string>) => ids.map((i) => m.get(i) ?? `#${i}`).join(', ')
  if (f.q.trim()) chips.push({ key: 'q', label: `“${f.q.trim()}”`, clear: { q: '' } })
  if (f.mine) chips.push({ key: 'mine', label: 'My deals', clear: { mine: false } })
  else if (f.owner_ids.length) chips.push({ key: 'owners', label: `Owner: ${list(f.owner_ids, names.users)}`, clear: { owner_ids: [] } })
  if (f.brand_ids.length) chips.push({ key: 'brands', label: `Brand: ${list(f.brand_ids, names.brands)}`, clear: { brand_ids: [] } })
  if (f.platform_ids.length) chips.push({ key: 'platforms', label: `Platform: ${list(f.platform_ids, names.platforms)}`, clear: { platform_ids: [] } })
  if (f.deal_types.length) chips.push({ key: 'deal', label: `Type: ${f.deal_types.map((d) => DEAL_TYPES[d] ?? d).join(', ')}`, clear: { deal_types: [] } })
  if (f.routes.length) chips.push({ key: 'route', label: `Route: ${f.routes.map((d) => ROUTES[d] ?? d).join(', ')}`, clear: { routes: [] } })
  if (f.lead_sources.length) chips.push({ key: 'source', label: `Source: ${f.lead_sources.map((d) => LEAD_SOURCES[d] ?? d).join(', ')}`, clear: { lead_sources: [] } })
  if (f.close !== 'any') {
    const label =
      f.close === 'custom'
        ? `Close: ${f.close_from ? dayjs(f.close_from).format('D MMM YYYY') : '…'} – ${f.close_to ? dayjs(f.close_to).format('D MMM YYYY') : '…'}`
        : `Close: ${CLOSE_PRESETS.find((p) => p.value === f.close)?.label}`
    chips.push({ key: 'close', label, clear: { close: 'any', close_from: null, close_to: null } })
  }
  if (f.min_amount || f.max_amount)
    chips.push({
      key: 'amount',
      label: `Value: ${f.min_amount ? money(f.min_amount) : '0'} – ${f.max_amount ? money(f.max_amount) : 'any'}`,
      clear: { min_amount: null, max_amount: null },
    })
  if (f.hide_closed) chips.push({ key: 'closed', label: 'Won and lost hidden', clear: { hide_closed: false } })
  return chips
}

const same = (a: ViewFilters, b: ViewFilters) => JSON.stringify(normalize(a)) === JSON.stringify(normalize(b))

export const useSavedViews = () => useQuery({ queryKey: ['views', 'pipeline'], queryFn: () => api<SavedView[]>('/views', { params: { entity: 'pipeline' } }) })

function FiltersDrawer({ opened, onClose, filters, onChange }: { opened: boolean; onClose: () => void; filters: ViewFilters; onChange: (f: ViewFilters) => void }) {
  const { data: users } = useUsers()
  const { data: brands } = useBrands()
  const { data: platforms } = usePlatforms()
  const set = (patch: Partial<ViewFilters>) => onChange({ ...filters, ...patch })
  const ids = (v: string[]) => v.map(Number)
  const strs = (v: number[]) => v.map(String)
  const toDate = (s: string | null) => (s ? dayjs(s).toDate() : null)
  return (
    <Drawer opened={opened} onClose={onClose} title="Filters" position="right" size="sm">
      <Stack gap="sm">
        <Text size="xs" c="dimmed">
          Changes apply at once. Save them as a view to come back to them.
        </Text>
        <Switch label="Only my deals" description="Whoever opens the view sees their own deals" checked={filters.mine} onChange={(e) => set({ mine: e.currentTarget.checked })} />
        <MultiSelect
          label="Owners"
          placeholder={filters.mine ? 'Only my deals' : 'Anyone'}
          disabled={filters.mine}
          data={(users ?? []).map((u) => ({ value: String(u.id), label: u.full_name }))}
          value={strs(filters.owner_ids)}
          onChange={(v) => set({ owner_ids: ids(v) })}
          searchable
          clearable
        />
        <MultiSelect label="Brands" placeholder="Any" data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))} value={strs(filters.brand_ids)} onChange={(v) => set({ brand_ids: ids(v) })} clearable />
        <MultiSelect
          label="Referring platforms"
          placeholder="Any"
          data={(platforms?.items ?? []).map((a) => ({ value: String(a.id), label: a.name }))}
          value={strs(filters.platform_ids)}
          onChange={(v) => set({ platform_ids: ids(v) })}
          searchable
          clearable
        />
        <MultiSelect label="Deal type" placeholder="Any" data={toOptions(DEAL_TYPES)} value={filters.deal_types} onChange={(v) => set({ deal_types: v })} clearable />
        <MultiSelect label="Route to market" placeholder="Any" data={toOptions(ROUTES)} value={filters.routes} onChange={(v) => set({ routes: v })} clearable />
        <MultiSelect label="Lead source" placeholder="Any" data={toOptions(LEAD_SOURCES)} value={filters.lead_sources} onChange={(v) => set({ lead_sources: v })} searchable clearable />
        <Divider />
        <Select
          label={
            <Group gap={4} component="span">
              Expected close
              <InfoTip info="Relative periods move with time: a view saved as “This quarter” always shows the current quarter." />
            </Group>
          }
          data={CLOSE_PRESETS}
          value={filters.close}
          onChange={(v) => set({ close: (v ?? 'any') as ClosePreset })}
          allowDeselect={false}
        />
        {filters.close === 'custom' && (
          <DatePickerInput
            type="range"
            label="Between"
            placeholder="Pick dates"
            value={[toDate(filters.close_from), toDate(filters.close_to)]}
            onChange={([a, b]) => set({ close_from: a ? fmt(dayjs(a)) : null, close_to: b ? fmt(dayjs(b)) : null })}
            valueFormat="D MMM YYYY"
            allowSingleDateInRange
            clearable
          />
        )}
        <Group grow>
          <NumberInput label="Value from" placeholder="0" min={0} thousandSeparator="," value={filters.min_amount ?? ''} onChange={(v) => set({ min_amount: v === '' ? null : String(v) })} />
          <NumberInput label="to" placeholder="Any" min={0} thousandSeparator="," value={filters.max_amount ?? ''} onChange={(v) => set({ max_amount: v === '' ? null : String(v) })} />
        </Group>
        <Text size="xs" c="dimmed" mt={-6}>
          Total contract value, in the deal's currency
        </Text>
        <Switch label="Hide the Won and Lost columns" checked={filters.hide_closed} onChange={(e) => set({ hide_closed: e.currentTarget.checked })} />
        <Group justify="space-between" mt="sm">
          <Button variant="subtle" color="gray" onClick={() => onChange({ ...DEFAULT_FILTERS, pipeline_id: filters.pipeline_id, sort: filters.sort })}>
            Clear filters
          </Button>
          <Button onClick={onClose}>Done</Button>
        </Group>
      </Stack>
    </Drawer>
  )
}

function ViewModal({ opened, onClose, title, initial, onSave, saving }: {
  opened: boolean
  onClose: () => void
  title: string
  initial: { name: string; shared: boolean }
  onSave: (v: { name: string; shared: boolean }) => void
  saving: boolean
}) {
  const [v, setV] = useState(initial)
  useEffect(() => {
    if (opened) setV(initial)
  }, [opened]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Modal opened={opened} onClose={onClose} title={title}>
      <Stack>
        <TextInput label="Name" required data-autofocus value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} maxLength={120} />
        <Switch
          label="Share with everyone"
          description="Other users can open it; only you (and administrators) can change it"
          checked={v.shared}
          onChange={(e) => setV({ ...v, shared: e.currentTarget.checked })}
        />
        <Group justify="flex-end">
          <Button loading={saving} disabled={!v.name.trim()} onClick={() => onSave({ name: v.name.trim(), shared: v.shared })}>
            Save
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

const STORAGE_KEY = 'crm.pipeline.view'

function remembered(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? 'all'
  } catch {
    return 'all'
  }
}

/** The view picker, search, filters and save actions above the board. Calls onFilters with what to show. */
export function PipelineViewBar({ filters, onFilters }: { filters: ViewFilters; onFilters: (f: ViewFilters) => void }) {
  const { user } = useAuth()
  const { data: views } = useSavedViews()
  const { data: users } = useUsers()
  const { data: brands } = useBrands()
  const { data: platforms } = usePlatforms()
  const [viewKey, setViewKey] = useState<string>(remembered)
  const [drawer, setDrawer] = useState(false)
  const [modal, setModal] = useState<'new' | 'edit' | null>(null)

  const saved = (views ?? []).find((v) => `v:${v.id}` === viewKey)
  const builtIn = BUILT_IN.find((b) => b.key === viewKey)
  const base = saved ? normalize(saved.filters) : (builtIn ?? BUILT_IN[0]).filters
  const dirty = !same({ ...filters, pipeline_id: base.pipeline_id ?? filters.pipeline_id }, { ...base, pipeline_id: base.pipeline_id ?? filters.pipeline_id })

  const choose = (key: string, all = views) => {
    const v = (all ?? []).find((x) => `v:${x.id}` === key)
    const b = BUILT_IN.find((x) => x.key === key)
    if (!v && !b) return choose('all', all)
    setViewKey(key)
    try {
      localStorage.setItem(STORAGE_KEY, key)
    } catch {
      /* storage unavailable */
    }
    const f = v ? normalize(v.filters) : b!.filters
    onFilters({ ...f, pipeline_id: f.pipeline_id ?? filters.pipeline_id })
  }

  // Open the remembered view once the saved views are known (it may have been deleted or unshared since)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (!ready && views) {
      setReady(true)
      choose(viewKey, views)
    }
  }, [views]) // eslint-disable-line react-hooks/exhaustive-deps

  const create = useApiMutation((v: { name: string; shared: boolean }) => api<SavedView>('/views', { method: 'POST', params: { entity: 'pipeline' }, body: { ...v, filters } }), {
    invalidate: [['views']],
    success: 'View saved',
    onSuccess: (v) => {
      setModal(null)
      setViewKey(`v:${v.id}`)
      try {
        localStorage.setItem(STORAGE_KEY, `v:${v.id}`)
      } catch {
        /* storage unavailable */
      }
    },
  })
  const update = useApiMutation((body: Partial<{ name: string; shared: boolean; filters: ViewFilters }>) => api<SavedView>(`/views/${saved!.id}`, { method: 'PATCH', body }), {
    invalidate: [['views']],
    success: 'View updated',
    onSuccess: () => setModal(null),
  })
  const remove = useApiMutation(() => api(`/views/${saved!.id}`, { method: 'DELETE' }), {
    invalidate: [['views']],
    success: 'View deleted',
    onSuccess: () => choose('all'),
  })

  const mine = (views ?? []).filter((v) => v.owner_id === user?.id)
  const others = (views ?? []).filter((v) => v.owner_id !== user?.id)
  const data = [
    { group: 'Standard', items: BUILT_IN.map((b) => ({ value: b.key, label: b.name })) },
    ...(mine.length ? [{ group: 'My views', items: mine.map((v) => ({ value: `v:${v.id}`, label: v.shared ? `${v.name} (shared)` : v.name })) }] : []),
    ...(others.length ? [{ group: 'Shared with me', items: others.map((v) => ({ value: `v:${v.id}`, label: `${v.name} · ${v.owner_name ?? ''}` })) }] : []),
  ]
  const names = {
    users: new Map((users ?? []).map((u) => [u.id, u.full_name])),
    brands: new Map((brands ?? []).map((b) => [b.id, b.name])),
    platforms: new Map((platforms?.items ?? []).map((a) => [a.id, a.name])),
  }
  const chips = activeChips(filters, names)
  const set = (patch: Partial<ViewFilters>) => onFilters({ ...filters, ...patch })

  return (
    <Stack gap={6} mb="md">
      <Group gap="sm" wrap="wrap">
        <Group gap={4} wrap="nowrap">
          <Select
            aria-label="View"
            data={data}
            value={viewKey}
            onChange={(v) => v && choose(v)}
            allowDeselect={false}
            searchable
            w={240}
            leftSection={saved?.shared ? <IconUsers size={14} /> : undefined}
            styles={{ input: { fontWeight: 600 } }}
          />
          {saved?.editable && (
            <Menu position="bottom-start" withinPortal>
              <Menu.Target>
                <ActionIcon variant="default" size="lg" aria-label="View options">
                  <IconDots size={16} />
                </ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<IconPencil size={14} />} onClick={() => setModal('edit')}>
                  Rename or share…
                </Menu.Item>
                <Menu.Item leftSection={<IconShare size={14} />} onClick={() => update.mutate({ shared: !saved.shared })}>
                  {saved.shared ? 'Stop sharing' : 'Share with everyone'}
                </Menu.Item>
                <Menu.Divider />
                <Menu.Item
                  color="red"
                  leftSection={<IconTrash size={14} />}
                  onClick={() =>
                    modals.openConfirmModal({
                      title: `Delete “${saved.name}”?`,
                      children: <Text size="sm">{saved.shared ? 'Other users who use this shared view lose it too.' : 'Only the view is deleted, not the deals.'}</Text>,
                      labels: { confirm: 'Delete', cancel: 'Cancel' },
                      confirmProps: { color: 'red' },
                      onConfirm: () => remove.mutate(undefined),
                    })
                  }
                >
                  Delete view
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          )}
        </Group>
        <TextInput placeholder="Search title or account" leftSection={<IconSearch size={16} />} value={filters.q} onChange={(e) => set({ q: e.target.value })} w={220} />
        <Button
          variant={chips.length ? 'light' : 'default'}
          leftSection={<IconAdjustmentsHorizontal size={16} />}
          rightSection={chips.length ? <Badge size="xs" circle>{chips.length}</Badge> : undefined}
          onClick={() => setDrawer(true)}
        >
          Filters
        </Button>
        <Select aria-label="Card order" data={SORTS} value={filters.sort} onChange={(v) => v && set({ sort: v as ViewFilters['sort'] })} allowDeselect={false} w={200} />
        {dirty && (
          <Group gap={6}>
            {saved?.editable && (
              <Tooltip label={`Replace the filters saved in “${saved.name}”`}>
                <Button size="xs" leftSection={<IconDeviceFloppy size={14} />} loading={update.isPending} onClick={() => update.mutate({ filters })}>
                  Save view
                </Button>
              </Tooltip>
            )}
            <Button size="xs" variant={saved?.editable ? 'default' : 'filled'} onClick={() => setModal('new')}>
              Save as new view
            </Button>
            <Button size="xs" variant="subtle" color="gray" onClick={() => choose(viewKey)}>
              Reset
            </Button>
          </Group>
        )}
        {saved && !saved.editable && (
          <Text size="xs" c="dimmed">
            Shared by {saved.owner_name}
          </Text>
        )}
      </Group>
      {chips.length > 0 && (
        <Group gap={6}>
          {chips.map((c) => (
            <Badge key={c.key} variant="light" color="gray" tt="none" pr={3} rightSection={<CloseButton size="xs" aria-label={`Remove ${c.label}`} onClick={() => set(c.clear)} />}>
              {c.label}
            </Badge>
          ))}
        </Group>
      )}
      <FiltersDrawer opened={drawer} onClose={() => setDrawer(false)} filters={filters} onChange={onFilters} />
      <ViewModal
        opened={modal !== null}
        onClose={() => setModal(null)}
        title={modal === 'edit' ? 'Rename or share the view' : 'Save as a new view'}
        initial={modal === 'edit' && saved ? { name: saved.name, shared: saved.shared } : { name: '', shared: false }}
        saving={create.isPending || update.isPending}
        onSave={(v) => (modal === 'edit' ? update.mutate(v) : create.mutate(v))}
      />
    </Stack>
  )
}
