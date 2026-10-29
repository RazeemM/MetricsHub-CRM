import { Card, Group, ScrollArea, Table, Text, Tooltip, UnstyledButton } from '@mantine/core'
import { IconChevronDown, IconChevronUp, IconInfoCircle, IconSelector } from '@tabler/icons-react'
import { useMemo, useState, type ReactNode } from 'react'

/** A small (i) icon that explains a metric or a column on hover or keyboard focus. */
export function InfoTip({ info, size = 14 }: { info?: ReactNode; size?: number }) {
  if (!info) return null
  return (
    <Tooltip label={info} multiline w={280} withArrow openDelay={150} events={{ hover: true, focus: true, touch: true }}>
      <span
        tabIndex={0}
        aria-label="More information"
        onClick={(e) => e.stopPropagation()}
        style={{ display: 'inline-flex', verticalAlign: 'middle', color: 'var(--mantine-color-dimmed)', cursor: 'help' }}
      >
        <IconInfoCircle size={size} stroke={1.6} />
      </span>
    </Tooltip>
  )
}

/** A label followed by its info icon. */
export function Labeled({ children, info }: { children: ReactNode; info?: ReactNode }) {
  return (
    <Group gap={4} wrap="nowrap" component="span" style={{ display: 'inline-flex' }}>
      {children}
      <InfoTip info={info} size={13} />
    </Group>
  )
}

/** A metric tile: label (with an explanation on hover), value, and a line of context. */
export function Stat({ label, value, children, hint, info, tone }: {
  label: string
  value?: ReactNode
  children?: ReactNode
  hint?: ReactNode
  info?: ReactNode
  tone?: string
}) {
  return (
    <Card withBorder padding="sm">
      <Group gap={4} wrap="nowrap">
        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
          {label}
        </Text>
        <InfoTip info={info} size={13} />
      </Group>
      <Text fw={700} size="xl" mt={2} c={tone} component="div">
        {value ?? children}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      )}
    </Card>
  )
}

export interface Sort {
  key: string
  desc: boolean
}

/** Click to sort by this column; click again to reverse. Numbers and dates start with the largest/latest. */
export function SortTh({ label, sortKey, sort, onSort, info, ta, w, firstDesc = false }: {
  label: ReactNode
  sortKey?: string
  sort?: Sort | null
  onSort?: (s: Sort) => void
  info?: ReactNode
  ta?: 'left' | 'right' | 'center'
  w?: number | string
  firstDesc?: boolean
}) {
  const active = !!sortKey && sort?.key === sortKey
  const Icon = !active ? IconSelector : sort!.desc ? IconChevronDown : IconChevronUp
  const content = (
    <Group gap={4} wrap="nowrap" justify={ta === 'right' ? 'flex-end' : undefined}>
      <Text fw={active ? 700 : 600} size="sm" component="span" style={{ whiteSpace: 'nowrap' }}>
        {label}
      </Text>
      <InfoTip info={info} size={13} />
      {sortKey && <Icon size={14} stroke={1.6} style={{ opacity: active ? 1 : 0.4, flex: 'none' }} />}
    </Group>
  )
  return (
    <Table.Th
      ta={ta}
      w={w}
      aria-sort={active ? (sort!.desc ? 'descending' : 'ascending') : undefined}
      style={{ whiteSpace: 'nowrap' }}
    >
      {sortKey && onSort ? (
        <UnstyledButton
          onClick={() => onSort({ key: sortKey, desc: active ? !sort!.desc : firstDesc })}
          style={{ width: ta === 'right' ? '100%' : undefined }}
          title="Sort"
        >
          {content}
        </UnstyledButton>
      ) : (
        content
      )}
    </Table.Th>
  )
}

export interface Column<T> {
  key: string
  label: string
  render: (r: T) => ReactNode
  /** Value to sort by; columns without one are not sortable. */
  sort?: (r: T) => number | string | null | undefined
  align?: 'right'
  info?: ReactNode
}

export function sortRows<T>(rows: T[], cols: Column<T>[], sort: Sort | null): T[] {
  const col = cols.find((c) => c.key === sort?.key)
  if (!col?.sort || !sort) return rows
  const f = col.sort
  return [...rows].sort((a, b) => {
    const x = f(a)
    const y = f(b)
    if (x == null || x === '') return y == null || y === '' ? 0 : 1 // blanks last either way
    if (y == null || y === '') return -1
    const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: 'base' })
    return sort.desc ? -c : c
  })
}

/** A table sorted in the browser: click a column header to sort by it. */
export function DataTable<T>({ rows, cols, initial, initialDesc = true, maxHeight = 560, minWidth = 760, empty = 'Nothing to show.', rowKey, onRowClick }: {
  rows: T[]
  cols: Column<T>[]
  initial?: string
  initialDesc?: boolean
  maxHeight?: number
  minWidth?: number
  empty?: string
  rowKey?: (r: T, i: number) => string | number
  onRowClick?: (r: T) => void
}) {
  const [sort, setSort] = useState<Sort | null>(initial ? { key: initial, desc: initialDesc } : null)
  const sorted = useMemo(() => sortRows(rows, cols, sort), [rows, cols, sort])
  if (!rows.length)
    return (
      <Text size="sm" c="dimmed">
        {empty}
      </Text>
    )
  return (
    <ScrollArea.Autosize mah={maxHeight} type="auto" offsetScrollbars>
      <Table miw={minWidth} fz="sm" verticalSpacing={6} stickyHeader highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            {cols.map((c) => (
              <SortTh
                key={c.key}
                label={c.label}
                sortKey={c.sort ? c.key : undefined}
                sort={sort}
                onSort={setSort}
                info={c.info}
                ta={c.align}
                firstDesc={c.align === 'right'}
              />
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {sorted.map((r, i) => (
            <Table.Tr key={rowKey ? rowKey(r, i) : i} className={onRowClick ? 'clickable-row' : undefined} onClick={onRowClick ? () => onRowClick(r) : undefined}>
              {cols.map((c) => (
                <Table.Td key={c.key} ta={c.align}>
                  {c.render(r)}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollArea.Autosize>
  )
}
